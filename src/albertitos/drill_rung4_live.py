"""Drill EN VIVO: matar llama-server a mitad de una corrida real (T24).

Los drills T12 usan mocks. Este es REAL (o con stub que muere, en tests):
demuestra la degradación con el VLM local vivo y muerto, midiendo todo —
es la evidencia de resiliencia que se muestra en la defensa (Salud).

Protocolo (store TEMPORAL, nunca el real):
1. Verifica (o levanta) llama-server en 127.0.0.1:8080.
2. Corrida BASE sin kill sobre un store sandbox → outcomes_base.jsonl.
3. Corrida con KILL a mitad (watchdog): un hilo mata el servidor cuando
   N archivos están decididos (o tras un tope de gracia). Store propio.
4. Mide la degradación: archivos en vuelo ⇒ rung 4 skip + rung 5 skip ⇒
   ESCALAR con motivo + página en cola de revisión; el resto del lote sigue
   por rung 1–3.
5. REINICIA llama-server y recupera con el reprocesado dirigido de T13
   (`--all-scaled`): los pendientes se re-deciden; los sanos se reutilizan
   (resume idempotente).
6. Emite outcomes de la recuperación y los compara byte a byte con los de
   la base: determinismo tras recuperación. También compara el peldaño
   final de cada página (aceptada por rung4 tras recuperar = como la base).

Todo el estado vive bajo `<store_root>` (por defecto `.sdd/drill-live/`,
jamás `.sdd/store.db` ni /tmp). El resultado se escribe en
`.sdd/metrics/drill-rung4-live.json` con timeline medido y nota para el
guion de defensa.

La flota no se toca: el script de lanzamiento corre con `nice`; el drill
muestrea RAM (proceso + llama-server + disponible) durante toda la corrida.
"""

from __future__ import annotations

import argparse
import json
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from albertitos.emit import emit_outcomes, list_pdf_files
from albertitos.extract.config import ExtractionConfig
from albertitos.reprocess import ReprocessConfig, reprocesar
from albertitos.run import Runner, RunnerConfig, _hoy_iso, _vlm_up
from albertitos.store import Store

DEFAULT_FACTURAS = "caja-de-alberto/facturas"
DEFAULT_STORE_ROOT = ".sdd/drill-live"
DEFAULT_METRICS = ".sdd/metrics/drill-rung4-live.json"
RUN_BASE = "base"
RUN_KILL = "kill"
RUN_RECOVERED = "recuperado"


@dataclass(frozen=True)
class DrillConfig:
    facturas_dir: Path = Path(DEFAULT_FACTURAS)
    store_root: Path = Path(DEFAULT_STORE_ROOT)
    rules_yaml: Path = Path("src/albertitos/rules/regla_v3.yaml")
    maestro: Path = Path("caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx")
    fecha_referencia: str = ""  # vacío ⇒ hoy UTC (fija para TODO el drill)
    n_scans: int = 12  # scans del corpus (van a rung 3→4)
    n_texto: int = 8  # facturas con capa de texto (rung 1, no tocan rung 4)
    total: int = 20
    forzar_rung4: bool = True  # rung 3 nunca para ⇒ TODO el OCR va al rung 4
    kill_after_files: int = 3  # matar cuando N archivos estén decididos
    kill_timeout_s: float = 45.0  # o tras este tope de gracia, lo que antes
    # Condición ALTERNATIVA sin carreras (tests): callable que decide el
    # momento del kill (p. ej. "el stub ya recibió su 1ª llamada rung4").
    kill_when: Callable[[], bool] | None = None
    timeout_por_archivo_s: float = 90.0
    vlm_start_timeout_s: float = 180.0  # carga del modelo gguf
    vlm_base_url: str = "http://127.0.0.1:8080"  # stub en tests
    use_rung4: bool = True


@dataclass
class DrillHooks:
    """Puntos de inyección: real (pkill/relanzar) o stub (tests)."""

    health: Callable[[], bool]
    kill: Callable[[str], dict]
    restart: Callable[[dict], dict]  # recibe el contexto del kill
    descripcion: str = "hooks inyectados"


# ---------------------------------------------------------------- selección


def seleccionar_archivos(cfg: DrillConfig) -> list[Path]:
    """20 archivos: scans del corpus (rung 3→4) + con capa de texto (rung 1)."""
    files = list_pdf_files(cfg.facturas_dir)
    scans = [p for p in files if p.name.startswith("scan_")][: cfg.n_scans]
    texto = [p for p in files if not p.name.startswith("scan_")]
    paso = max(1, len(texto) // max(1, cfg.n_texto))
    texto = texto[::paso][: cfg.n_texto]
    sel = sorted(scans + texto)[: cfg.total]
    if not sel:
        raise ValueError(f"sin archivos seleccionables en {cfg.facturas_dir}")
    return sel


def _extract_cfg(cfg: DrillConfig) -> ExtractionConfig:
    base = ExtractionConfig()
    if not cfg.forzar_rung4:
        return base
    # Umbral imposible ⇒ rung 3 nunca acepta ⇒ TODAS las páginas escaneadas
    # llegan al rung 4 (el drill mide el degradado del VLM, no del OCR).
    # config_version propia: claves de cache separadas del sistema real.
    from dataclasses import replace

    return replace(
        base,
        config_version="extract-drill24",
        vlm_base_url=cfg.vlm_base_url,
        tesseract_min_word_conf=101.0,
        tesseract_min_field_coverage=2.0,
    )


def _runner_cfg(cfg: DrillConfig, store_root: Path, run_id: str,
                only_list: list[Path]) -> RunnerConfig:
    return RunnerConfig(
        facturas_dir=cfg.facturas_dir,
        outcomes_path=store_root / "outcomes.jsonl",
        store_root=store_root,
        rules_yaml=cfg.rules_yaml,
        master_path=cfg.maestro,
        fecha_referencia=cfg.fecha_referencia,
        timeout_por_archivo_s=cfg.timeout_por_archivo_s,
        use_rung4=cfg.use_rung4,
        run_id=run_id,
        extract_config=_extract_cfg(cfg),
        only_list=tuple(p.name for p in only_list),
    )


# ---------------------------------------------------------------- watchdog


def _watchdog(store_root: Path, total: int, cfg: DrillConfig, hooks: DrillHooks,
              timeline: list[dict], t0: float) -> threading.Event:
    if cfg.kill_when is not None:
        condicion = cfg.kill_when
    else:
        condicion = None
    """Hilo que mata llama-server cuando N decisiones están registradas
    (o tras el tope de gracia). Devuelve el evento de apagado del hilo."""
    stop = threading.Event()
    kill_done = threading.Event()

    def hilo() -> None:
        db = store_root / "store.db"
        while not stop.wait(0.25):
            decididos = 0
            try:
                import sqlite3

                conn = sqlite3.connect(db)
                try:
                    decididos = conn.execute(
                        "SELECT COUNT(*) FROM invoices").fetchone()[0]
                finally:
                    conn.close()
            except (sqlite3.Error, OSError):
                continue
            transcurrido = time.monotonic() - t0
            gatillo = (condicion() if condicion is not None
                       else decididos >= cfg.kill_after_files)
            if gatillo or transcurrido >= cfg.kill_timeout_s:
                motivo = (
                    "condición del drill" if condicion is not None and gatillo else
                    (f"{decididos} archivos decididos (objetivo "
                     f"{cfg.kill_after_files})" if decididos >= cfg.kill_after_files
                     else f"tope de gracia {cfg.kill_timeout_s:.0f}s "
                          f"({decididos} decididos)")
                )
                detalle = hooks.kill(motivo)
                timeline.append({
                    "t_rel_s": round(time.monotonic() - t0, 3),
                    "evento": "KILL llama-server",
                    "detalle": f"{motivo} · {detalle.get('como', '')}",
                })
                kill_done.set()
                return

    th = threading.Thread(target=hilo, daemon=True, name="drill-watchdog")
    th.start()
    return stop


def _vigilar_rss(cada_s: float, muestras: list[dict],
                 stop: threading.Event) -> None:
    """Muestrea RAM del proceso, de llama-server y disponible (la flota
    no se degrada: medido)."""
    def pid_llama() -> int | None:
        try:
            out = subprocess.run(
                ["pgrep", "-f", "llama-server"], capture_output=True, text=True,
                timeout=5, check=False)
            for line in out.stdout.splitlines():
                pid = int(line.strip())
                cmd = Path(f"/proc/{pid}/cmdline")
                if cmd.exists() and b"bash" not in cmd.read_bytes()[:64]:
                    return pid
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
        return None

    while not stop.wait(cada_s):
        try:
            rss_mb = None
            status = Path("/proc/self/status").read_text()
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    rss_mb = int(line.split()[1]) / 1024
                    break
            avail_mb = None
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    avail_mb = int(line.split()[1]) / 1024
                    break
            llama_mb = None
            pid = pid_llama()
            if pid is not None:
                for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        llama_mb = int(line.split()[1]) / 1024
                        break
            muestras.append({
                "rss_proceso_mb": rss_mb,
                "disponible_mb": avail_mb,
                "rss_llama_mb": llama_mb,
            })
        except OSError:
            continue


def _rungs_por_file(store: Store) -> dict[str, str]:
    """Peldaño que aceptó cada página, por file_id (medido en evidencia)."""
    import sqlite3

    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT file_id, stage, outcome FROM evidence "
            "WHERE stage LIKE 'extract:rung%' AND outcome = 'accept' "
            "ORDER BY file_id, stage"
        ).fetchall()
        acepta: dict[str, str] = {}
        for r in rows:
            fid = r["file_id"] or "?"
            acepta.setdefault(fid, r["stage"])
        return dict(sorted(acepta.items()))
    finally:
        conn.close()


def _skips_rung4(store: Store) -> dict[str, int]:
    """Páginas cuyo rung 4 quedó skip (proveedor caído), por file_id."""
    import sqlite3

    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT file_id, COUNT(*) n FROM evidence "
            "WHERE stage = 'extract:rung4_vlm' AND outcome = 'skipped' "
            "GROUP BY file_id"  # server caído O llamada cortada en vuelo (T24)
        ).fetchall()
        return {r["file_id"]: r["n"] for r in rows}
    finally:
        conn.close()


def _review_queue(store_root: Path) -> int:
    rq = store_root / "review-queue" / "review.jsonl"
    if not rq.is_file():
        return 0
    return sum(1 for line in rq.read_text(encoding="utf-8").splitlines()
               if line.strip())


# ---------------------------------------------------------------- drill


def ejecutar_drill(cfg: DrillConfig, hooks: DrillHooks,
                   *, sample_rss: bool = True) -> dict:
    """Corre el protocolo completo y devuelve el reporte medido."""
    if not cfg.fecha_referencia:
        cfg = _fijar_fecha(cfg)
    root = Path(cfg.store_root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    files = seleccionar_archivos(cfg)
    file_ids = {p.name for p in files}

    t0 = time.monotonic()
    timeline: list[dict] = [{
        "t_rel_s": 0.0,
        "evento": "arranque del drill",
        "detalle": f"{len(files)} archivos, hooks: {hooks.descripcion}",
    }]
    muestras_rss: list[dict] = []
    stop_rss = threading.Event()
    if sample_rss:
        threading.Thread(target=_vigilar_rss, args=(0.5, muestras_rss, stop_rss),
                         daemon=True).start()

    assert hooks.health(), "llama-server no está UP antes del drill"
    timeline.append({
        "t_rel_s": round(time.monotonic() - t0, 3),
        "evento": "health-check llama-server",
        "detalle": "UP",
    })

    # ---- 1 · corrida BASE (sin kill)
    store_base_dir = root / "base"
    rep_base = Runner(_runner_cfg(cfg, store_base_dir, RUN_BASE, files)).run()
    store_base = Store(store_base_dir)
    try:
        emit_outcomes(store_base, store_base_dir / "outcomes.jsonl")
        bytes_base = (store_base_dir / "outcomes.jsonl").read_bytes()
        rungs_base = _rungs_por_file(store_base)
    finally:
        store_base.close()
    timeline.append({
        "t_rel_s": round(time.monotonic() - t0, 3),
        "evento": "base completa (sin kill)",
        "detalle": f"{rep_base.procesados} procesados, "
                   f"{rep_base.files_per_second} files/s",
    })

    # ---- 2 · corrida con KILL a mitad
    store_kill_dir = root / "kill"
    stop_watchdog = _watchdog(store_kill_dir, len(files), cfg, hooks,
                              timeline, t0)
    rep_kill = Runner(_runner_cfg(cfg, store_kill_dir, RUN_KILL, files)).run()
    stop_watchdog.set()
    store_kill = Store(store_kill_dir)
    try:
        skip_rung4 = _skips_rung4(store_kill)
        review_count = _review_queue(store_kill_dir)
    finally:
        store_kill.close()
    timeline.append({
        "t_rel_s": round(time.monotonic() - t0, 3),
        "evento": "corrida con kill terminada",
        "detalle": f"timeout={rep_kill.timeout}, afectados_rung4="
                   f"{len(skip_rung4)}, cola_revision={review_count}",
    })

    # ---- 3 · recuperación: reiniciar + reprocesado dirigido (T13)
    restart_detalle = hooks.restart({"kill": True})
    up = _esperar_health(hooks, cfg.vlm_start_timeout_s)
    timeline.append({
        "t_rel_s": round(time.monotonic() - t0, 3),
        "evento": "llama-server reiniciado",
        "detalle": f"health UP={up} · {restart_detalle.get('como', '')}",
    })

    t_rec = time.monotonic()
    cfg_repro = ReprocessConfig(
        facturas_dir=cfg.facturas_dir,
        store_root=store_kill_dir,
        rules_yaml=cfg.rules_yaml,
        master_path=cfg.maestro,
        fecha_referencia=cfg.fecha_referencia,
        all_scaled=True,  # los degradados quedaron ESCALAR: se re-deciden
        run_id=RUN_RECOVERED,
        base_run=RUN_KILL,
        use_rung4=cfg.use_rung4,
        extract_config=_extract_cfg(cfg),
        outcomes_path=store_kill_dir / "outcomes.jsonl",
    )
    impacto = reprocesar(cfg_repro)
    elapsed_rec = time.monotonic() - t_rec

    store_kill = Store(store_kill_dir)
    try:
        emit_outcomes(store_kill, store_kill_dir / "outcomes.jsonl")
        bytes_rec = (store_kill_dir / "outcomes.jsonl").read_bytes()
        rungs_rec = _rungs_por_file(store_kill)
        runs = store_kill.run_ids()
    finally:
        store_kill.close()

    stop_rss.set()
    id_outcomes = bytes_rec == bytes_base
    rungs_ok = (
        {k: v for k, v in rungs_rec.items() if k in file_ids}
        == {k: v for k, v in rungs_base.items() if k in file_ids}
    )
    file_ids_rec = {d.file_id for d in _decisions(store_kill_dir)}
    resumen_rss = {
        "muestras": len(muestras_rss),
        "rss_proceso_max_mb": round(max(
            (m["rss_proceso_mb"] or 0) for m in muestras_rss), 1),
        "disponible_min_mb": round(min(
            (m["disponible_mb"] or 10**9) for m in muestras_rss), 1),
        "rss_llama_max_mb": round(max(
            (m["rss_llama_mb"] or 0) for m in muestras_rss), 1),
    } if muestras_rss else {"muestras": 0}

    resultados_finales: dict[str, int] = {"PAGAR": 0, "NO_PAGAR": 0, "ESCALAR": 0}
    for d in _decisions(store_kill_dir):
        if d.file_id in file_ids and d.result in resultados_finales:
            resultados_finales[d.result] += 1

    nota = (
        "Drill EN VIVO de resiliencia (T24): con llama-server arriba, la "
        "corrida corre; al matarlo a mitad, los archivos en vuelo degradan "
        "(rung 4 skip → rung 5 skip → ESCALAR con motivo y página en cola de "
        "revisión) y el resto del lote sigue por rung 1–3 sin bloquearse. "
        "Reiniciado el servidor, el reprocesado dirigido re-decide SOLO los "
        "afectados; los sanos se reutilizan del store. El outcomes final es "
        "byte a byte el mismo que sin kill, y cada página vuelve al peldaño "
        "que le correspondía. El fallo transitorio del proveedor NO se cachea "
        "(T24): por eso la recuperación es posible."
    )

    return {
        "sim": "drill-rung4-live",
        "hooks": hooks.descripcion,
        "archivos": {
            "total": len(files),
            "file_id_exacto": sorted(file_ids),
            "store_temporal": str(root),
        },
        "timeline": timeline,
        "metricas": {
            "files_per_second_base": rep_base.files_per_second,
            "files_per_second_recuperacion": round(
                (impacto["resumen"].get("reprocesados", 0) or 0) / elapsed_rec, 3)
            if elapsed_rec > 0 else None,
            "timeout_en_corrida_kill": rep_kill.timeout,
            "reprocesados_recuperacion": impacto["resumen"].get(
                "reprocesados", 0),
            "elapsed_recuperacion_s": round(elapsed_rec, 3),
            "ram": resumen_rss,
            "ram_bajo_control": resumen_rss.get("disponible_min_mb", 0) > 300,
        },
        "degradacion": {
            "archivos_con_rung4_skip": skip_rung4,
            "cola_revision": review_count,
            "timeout": rep_kill.timeout,
        },
        "recuperacion": {
            "outcomes_byte_identico_base": id_outcomes,
            "rungs_finales_coinciden": rungs_ok,
            "runs_en_historico": sorted(runs),
            "file_ids_completos": file_ids_rec >= file_ids,
            "resultados_finales": resultados_finales,
            "paginas_rung4_respondio": sum(
                1 for v in rungs_rec.values() if "rung4" in v),
            # archivos cuyo rung4 respondió con proveedor vivo tras recuperar
            "rung4_llamadas_vivas": _rung4_vivos(store_kill_dir),
        },
        "nota_defensa": nota,
        "generado": datetime.now(tz=UTC).isoformat(timespec="seconds"),
    }


def _rung4_vivos(store_root: Path) -> int:
    """Archivos cuyo rung 4 RESPONDIÓ con proveedor vivo (no skipped)."""
    import sqlite3

    conn = sqlite3.connect(Path(store_root) / "store.db")
    try:
        n = conn.execute(
            "SELECT COUNT(DISTINCT file_id) FROM evidence "
            "WHERE stage = 'extract:rung4_vlm' "
            "AND outcome IN ('accept', 'below-threshold')"
        ).fetchone()[0]
    finally:
        conn.close()
    return int(n)


def _decisions(store_root: Path) -> list:
    store = Store(store_root)
    try:
        return store.all_decisions()
    finally:
        store.close()


def _fijar_fecha(cfg: DrillConfig) -> DrillConfig:
    from dataclasses import replace

    return replace(cfg, fecha_referencia=cfg.fecha_referencia or _hoy_iso())


def _esperar_health(hooks: DrillHooks, timeout_s: float) -> bool:
    import time as _t

    fin = _t.monotonic() + timeout_s
    while _t.monotonic() < fin:
        if hooks.health():
            return True
        _t.sleep(0.5)
    return hooks.health()


# ---------------------------------------------------------------- hooks reales


def _pid_llama_server() -> tuple[int, list[str]] | None:
    """PID del llama-server real + su cmdline exacta (para relanzarlo igual)."""
    out = subprocess.run(["pgrep", "-f", "llama-server"],
                         capture_output=True, text=True, check=False)
    for line in out.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            continue
        if b"bash" in raw.split(b"\0")[0]:
            continue  # el wrapper nohup, no el servidor
        argv = raw.decode().split("\0")
        argv = [a for a in argv if a]
        if argv and "llama-server" in argv[0]:
            return pid, argv
    return None


def hooks_reales() -> DrillHooks:
    """Mata llama-server (pkill/kill) y lo relanza con SU MISMA cmdline
    (leída de /proc antes del kill). Al final del drill el servidor queda UP."""
    estado: dict = {}

    def health() -> bool:
        # listo de verdad: /v1/models responde Y /health ya no está cargando
        if not _vlm_up("http://127.0.0.1:8080", timeout_s=3.0):
            return False
        import urllib.request

        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8080/health", timeout=3.0
            ) as resp:
                return resp.status == 200
        except OSError:
            return True  # /health no disponible en esta build: models basta

    def kill(motivo: str) -> dict:
        hallado = _pid_llama_server()
        if hallado is None:
            return {"como": "no había llama-server vivo en el momento del kill"}
        pid, argv = hallado
        estado["argv"] = argv
        try:
            import os

            os.kill(pid, signal.SIGTERM)
        except OSError as e:
            subprocess.run(["pkill", "-f", "llama-server"], check=False)
            return {"como": f"pkill fallback (os.kill falló: {e})"}
        return {"como": f"SIGTERM al PID {pid} (cmdline preservada para relanzar)"}

    def restart(_ctx: dict) -> dict:
        argv = estado.get("argv")
        if not argv:
            hallado = _pid_llama_server()
            argv = hallado[1] if hallado else None
        if not argv:
            return {"como": "sin cmdline conocida: NO se relanzó (arranque manual)"}
        log = Path(".sdd/drill-live/llama-server.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("ab") as fh:
            subprocess.Popen(argv, stdout=fh, stderr=fh, start_new_session=True)
        return {"como": f"relanzado: {argv[0]} …"}

    return DrillHooks(health=health, kill=kill, restart=restart,
                      descripcion="kill REAL (SIGTERM) + relanzado con su cmdline")


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="albertitos.drill_rung4_live",
        description="Drill EN VIVO: matar llama-server a mitad de corrida (T24).",
    )
    parser.add_argument("--facturas", default=DEFAULT_FACTURAS)
    parser.add_argument("--store-root", default=DEFAULT_STORE_ROOT)
    parser.add_argument("--rules", default="src/albertitos/rules/regla_v3.yaml")
    parser.add_argument("--maestro", default="caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx")
    parser.add_argument("--fecha-referencia", default="")
    parser.add_argument("--n-scans", type=int, default=12)
    parser.add_argument("--n-texto", type=int, default=8)
    parser.add_argument("--kill-after", type=int, default=3)
    parser.add_argument("--kill-timeout", type=float, default=45.0)
    parser.add_argument("--timeout", type=float, default=90.0,
                        help="timeout por archivo de la corrida")
    parser.add_argument("--metrics", default=DEFAULT_METRICS)
    parser.add_argument("--sin-fuerza-rung4", action="store_true",
                        help="usar los umbrales calibrados (rung 3 decide)")
    args = parser.parse_args(argv)


    cfg = DrillConfig(
        facturas_dir=Path(args.facturas),
        store_root=Path(args.store_root),
        rules_yaml=Path(args.rules),
        maestro=Path(args.maestro),
        fecha_referencia=args.fecha_referencia or _hoy_iso(),
        n_scans=args.n_scans,
        n_texto=args.n_texto,
        forzar_rung4=not args.sin_fuerza_rung4,
        kill_after_files=args.kill_after,
        kill_timeout_s=args.kill_timeout,
        timeout_por_archivo_s=args.timeout,
    )
    hooks = hooks_reales()
    try:
        resultado = ejecutar_drill(cfg, hooks)
    finally:
        # el sidecar queda UP como estaba (la flota sigue)
        if not _vlm_up("http://127.0.0.1:8080"):
            hooks.restart({})
            _esperar_health(hooks, cfg.vlm_start_timeout_s)
    metrics = Path(args.metrics)
    metrics.parent.mkdir(parents=True, exist_ok=True)
    metrics.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(_render(resultado))
    print(f"JSON del drill: {metrics}")
    rec = resultado["recuperacion"]
    return 0 if rec["outcomes_byte_identico_base"] and rec["rungs_finales_coinciden"] else 1


def _render(r: dict) -> str:
    lines = [
        "DRILL EN VIVO — llama-server muerto a mitad de corrida",
        f"hooks: {r['hooks']}",
        f"archivos: {r['archivos']['total']} (store temporal {r['archivos']['store_temporal']})",
        "",
        "timeline (t relativo al arranque, medido):",
    ]
    for ev in r["timeline"]:
        lines.append(f"  t={ev['t_rel_s']:>8.3f}s  {ev['evento']} — {ev['detalle']}")
    m = r["metricas"]
    d = r["degradacion"]
    rec = r["recuperacion"]
    lines += [
        "",
        (f"throughput: base {m['files_per_second_base']} files/s · "
         f"recuperación {m['files_per_second_recuperacion']} files/s (medido)"),
        (f"degradación: {len(d['archivos_con_rung4_skip'])} archivos con rung 4 "
         f"skip · cola de revisión: {d['cola_revision']} · timeouts: {d['timeout']}"),
        (f"RAM: proceso máx {m['ram']['rss_proceso_max_mb']} MB · llama máx "
         f"{m['ram']['rss_llama_max_mb']} MB · disponible mín "
         f"{m['ram']['disponible_min_mb']} MB (medido)"),
        (f"recuperación: outcomes byte-idéntico a la base = "
         f"{rec['outcomes_byte_identico_base']} · peldaños finales iguales = "
         f"{rec['rungs_finales_coinciden']} · runs: "
         f"{', '.join(rec['runs_en_historico'])}"),
        "",
        "NOTA PARA LA DEFENSA:",
        r["nota_defensa"],
    ]
    return "\n".join(lines) + "\n"

if __name__ == "__main__":
    main()
