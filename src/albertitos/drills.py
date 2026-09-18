"""Drills de resiliencia automatizados — ensayan y MIDEN (T12, AGENTS §3/§5).

Cada drill usa mocks/adapters y NO depende de red real. La salida es
`.sdd/metrics/drills.json` con resultado POR drill (pass/fail y el
comportamiento MEDIDO) — el informe y la defensa se alimentan de aquí.

    uv run python -m albertitos.drills [--root .sdd] [--destino .sdd/metrics/drills.json]

Drills:
  1. rung5-provider-caido  — el proveedor cloud no responde ⇒ la página entra
     en cola de revisión (ESCALAR) con motivo en evidencia; el lote sigue.
  2. backoff-429           — Retry-After respetado (con cap) + backoff
     exponencial; ninguna llamada extra tras el éxito.
  3. crash-reanudacion     — crash del runner a mitad de lote ⇒ reanudación
     completa sin duplicados (runner real `pipeline.run_batch` + store T4).
  4. ledger-corrupto       — líneas corruptas del ledger se toleran (lector
     de UI y métricas); ninguna se inventa.

Estado de trabajo bajo `<root>/drills/` (.sdd), jamás en /tmp.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from albertitos.extract.cloud import CloudConfig, read_page
from albertitos.extract.config import ExtractionConfig
from albertitos.extract.ladder import ExtractionLadder
from albertitos.pipeline import PipelineDeps, run_batch
from albertitos.rules import load_config, load_master
from albertitos.store import Store
from albertitos.ui.ledger import build_view, load_ledger

DRILLS_JSON_DEFECTO = Path(".sdd/metrics/drills.json")


# ------------------------------------------------------------------ drills


def _transport_caido(contador: list[int]) -> httpx.BaseTransport:
    """Proveedor caído: toda conexión falla; cuenta los intentos."""

    def handler(request: httpx.Request) -> httpx.Response:
        contador.append(1)
        raise httpx.ConnectError("drill:proveedor-caido")

    return httpx.MockTransport(handler)


def drill_rung5_provider_caido(root: Path) -> dict[str, Any]:
    """Página ilegible + proveedor cloud caído ⇒ ESCALAR con motivo, sin abortar."""
    base = root / "drills" / "rung5"
    if base.exists():
        shutil.rmtree(base)
    cfg = ExtractionConfig(vlm_base_url="http://127.0.0.1:1", tesseract_bin="/nonexistent/t")
    cloud = CloudConfig(
        base_url="http://drill.invalid",
        model="drill-model",
        api_key="drill-key",
        max_retries=2,
        backoff_initial_s=0.001,
        retry_after_cap_s=0.001,
        timeout_s=1.0,
    )
    intentos: list[int] = []
    ladder = ExtractionLadder(
        cfg=cfg,
        cache_root=base / "cache",
        evidence_path=base / "ledger" / "extract.jsonl",
        review_dir=base / "review",
        cloud=cloud,
        http_transport=_transport_caido(intentos),
    )
    fixture = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "scan_001.pdf"
    if not fixture.is_file():  # ejecutado fuera del repo: fixture alternativa
        fixture = Path("tests/fixtures/scan_001.pdf")
    paginas = ladder.extract_file(fixture, invoice_id="drill-rung5", file_id="scan_001.pdf")
    page = paginas[0]
    evidencia_rung5 = [
        e for e in page.evidence if e.stage == "extract:rung5_cloud_vlm" and e.outcome == "error"
    ]
    motivo = next((e.detail for e in evidencia_rung5 if "provider-failed" in e.detail), "")
    mediciones = {
        "intentos_cloud": len(intentos),  # max_retries + 1
        "error_en_evidencia": bool(evidencia_rung5),
        "motivo_evidencia": motivo[:120],
        "pagina_en_cola_revision": page.escalated,
        "lote_continua": len(paginas) == 1 and len(page.features) > 0,
    }
    ok = (
        mediciones["error_en_evidencia"]
        and "provider-failed" in mediciones["motivo_evidencia"]
        and mediciones["pagina_en_cola_revision"]
        and mediciones["lote_continua"]
    )
    return {
        "drill": "rung5-provider-caido",
        "pass": ok,
        "mediciones": mediciones,
        "detalle": (
            f"El proveedor no responde tras {len(intentos)} intentos; la página queda en "
            "cola de revisión (ESCALAR) con motivo en evidencia y el proceso sigue."
        ),
    }


def drill_backoff_429(root: Path) -> dict[str, Any]:
    """429 con Retry-After ⇒ backoff respetado (cap incluido) y cero llamadas extra."""
    base = root / "drills" / "backoff"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    respuestas = [
        ("429", "2.0"),  # Retry-After: 2.0 s — debe respetarse con cap
        ("429", None),  # sin Retry-After — backoff exponencial
        ("200", None),  # éxito en el 3er intento
    ]
    llamadas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        idx = len(llamadas)
        estado, retry_after = respuestas[idx] if idx < len(respuestas) else ("500", None)
        llamadas.append(estado)
        headers = {"Retry-After": retry_after} if retry_after else {}
        if estado == "200":
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"nif": "B46102331", "total": "121.00"}'}}]},
                headers=headers,
            )
        return httpx.Response(int(estado), json={"error": "drill"}, headers=headers)

    cfg = CloudConfig(
        base_url="http://drill.invalid",
        model="drill-model",
        api_key="drill-key",
        max_retries=3,
        backoff_initial_s=0.01,
        retry_after_cap_s=0.05,
        timeout_s=1.0,
    )
    dormidas: list[float] = []
    import albertitos.extract.cloud as cloud_mod

    # Patch acotado al módulo cloud (no al time global): solo este drill mide.
    class _RelojFalso:
        @staticmethod
        def sleep(seg: float) -> None:
            dormidas.append(float(seg))

        @staticmethod
        def monotonic() -> float:
            return time.monotonic()

        @staticmethod
        def time() -> float:
            return time.time()

    reloj_original = cloud_mod.time
    cloud_mod.time = _RelojFalso  # type: ignore[assignment]
    try:
        contenido = read_page(
            cfg,
            b"png-drill",
            transport=httpx.MockTransport(handler),
        )
    finally:
        cloud_mod.time = reloj_original  # type: ignore[assignment]
    esperado_delays = [
        min(2.0, cfg.retry_after_cap_s),  # Retry-After 2.0, capped
        min(cfg.backoff_initial_s * (2**1), cfg.retry_after_cap_s),  # exponencial
    ]
    mediciones = {
        "n_llamadas": len(llamadas),  # 3: dos 429 + un 200; ninguna extra
        "secuencia_estados": llamadas,
        "delays_aplicados": dormidas,
        "delays_esperados": esperado_delays,
        "backoff_respetado": dormidas == esperado_delays,
        "exito": contenido.startswith('{"nif"'),
    }
    ok = (
        mediciones["n_llamadas"] == 3
        and mediciones["backoff_respetado"]
        and mediciones["exito"]
    )
    return {
        "drill": "backoff-429",
        "pass": ok,
        "mediciones": mediciones,
        "detalle": "429×2 con Retry-After y luego éxito: 3 llamadas exactas, delays según Retry-After (cap) + exponencial.",
    }


def drill_crash_reanudacion(root: Path) -> dict[str, Any]:
    """Crash del runner a mitad de lote ⇒ reanudación completa sin duplicados."""
    base = root / "drills" / "crash"
    if base.exists():
        shutil.rmtree(base)
    pdfs = base / "facturas"
    pdfs.mkdir(parents=True)
    fixture_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "facturas"
    nombres = sorted(p.name for p in fixture_dir.glob("*.pdf"))
    for nombre in nombres[:4]:
        shutil.copy(fixture_dir / nombre, pdfs / nombre)
    n_total = len(list(pdfs.glob("*.pdf")))

    def _deps(injector=None) -> PipelineDeps:
        rules_yaml = Path(__file__).parent / "rules" / "regla_v3.yaml"
        cfg = load_config(rules_yaml, fecha_referencia="2026-09-19")
        master_xlsx = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "maestro_fixture.xlsx"
        master = load_master(master_xlsx, hojas_ignoradas=cfg.hojas_ignoradas)
        return PipelineDeps(master=master, config=cfg, fail_injector=injector)

    store = Store(base / "sdd")
    crash_en = 2

    def injector(file_id: str, index: int) -> None:
        if index == crash_en:
            raise RuntimeError("drill:crash-simulado-a-mitad-de-lote")

    try:
        run_batch(pdfs, store, _deps(injector))
        n_tras_crash = len(store.all_decisions())
    except RuntimeError:
        n_tras_crash = len(store.all_decisions())
    report2 = run_batch(pdfs, store, _deps(None))
    decisiones = store.all_decisions()
    store.close()
    por_file = Counter(d.file_id for d in decisiones)
    resultados = report2.resultados
    mediciones = {
        "n_archivos": n_total,
        "crash_simulado_en_index": crash_en,
        "decididos_tras_crash": n_tras_crash,
        "decididos_tras_reanudar": len(decisiones),
        "resultados_unicos": len(set(resultados)),
        "duplicados_en_store": sum(1 for v in por_file.values() if v > 1),
        "reutilizados_por_cache": report2.reutilizados,
        "reanudacion_completa": len(decisiones) == n_total,
        "sin_duplicados": all(v == 1 for v in por_file.values()) and len(set(resultados)) == len(resultados),
    }
    ok = mediciones["reanudacion_completa"] and mediciones["sin_duplicados"]
    return {
        "drill": "crash-reanudacion",
        "pass": ok,
        "mediciones": mediciones,
        "detalle": f"Crash en el ítem {crash_en}: {n_tras_crash} decididos; reanudar completa el lote sin duplicados.",
    }


def drill_ledger_corrupto(root: Path) -> dict[str, Any]:
    """Evidencia corrupta en el ledger ⇒ el lector la tolera sin inventar nada."""
    base = root / "drills" / "corrupto"
    if base.exists():
        shutil.rmtree(base)
    ledger = base / "ledger"
    ledger.mkdir(parents=True)
    validas = [
        (
            '{"kind": "decision", "invoice_id": "A", "file_id": "a.pdf", "result": "PAGAR",'
            ' "rule_verdicts": [], "config_snapshot": {}}'
        ),
        (
            '{"kind": "evidence", "invoice_id": "A", "stage": "decide", "extractor":'
            ' "rule-engine", "extractor_version": "1", "config_version": "c", "sha256":'
            ' "' + "0" * 64 + '", "latency_ms": 10, "confidence": null, "outcome": "ok", "detail": "d"}'
        ),
    ]
    corruptas = ["{json roto", "", '{"kind": "evidence", "truncado":']
    contenido = "\n".join(validas + corruptas) + "\n"
    (ledger / "ledger.jsonl").write_text(contenido, encoding="utf-8")
    registros = load_ledger(ledger)
    vista = build_view(registros)
    mediciones = {
        "lineas_totales": len([x for x in contenido.splitlines() if x.strip()]),
        "registros_validos": len(registros),
        "lineas_corruptas_ignoradas": len(corruptas),
        "decisiones_cargadas": len(vista.decisions),
        "evidencia_cargada": len(vista.evidence),
        "sin_datos_inventados": len(vista.decisions) == 1 and len(vista.evidence) == 1,
    }
    ok = (
        mediciones["registros_validos"] == 2
        and mediciones["decisiones_cargadas"] == 1
        and mediciones["evidencia_cargada"] == 1
    )
    return {
        "drill": "ledger-corrupto",
        "pass": ok,
        "mediciones": mediciones,
        "detalle": "El lector ignora las líneas corruptas y usa solo las válidas: degradación, no aborte.",
    }


# ------------------------------------------------------------------ orquestación


def ejecutar_drills(root: Path | str = ".sdd", destino: Path | None = None) -> dict[str, Any]:
    """Ejecuta todos los drills y escribe el JSON. Devuelve el reporte."""
    root_path = Path(root)
    resultados = [
        drill_rung5_provider_caido(root_path),
        drill_backoff_429(root_path),
        drill_crash_reanudacion(root_path),
        drill_ledger_corrupto(root_path),
    ]
    import datetime

    reporte = {
        "generado": datetime.datetime.now(tz=datetime.UTC).isoformat(timespec="seconds"),
        "drills": resultados,
        "resumen": {
            "pass": sum(1 for r in resultados if r["pass"]),
            "fail": sum(1 for r in resultados if not r["pass"]),
        },
    }
    destino_final = Path(destino) if destino is not None else DRILLS_JSON_DEFECTO
    destino_final.parent.mkdir(parents=True, exist_ok=True)
    destino_final.write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return reporte


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m albertitos.drills",
        description="Ensayos de fallo automatizados (mocks, sin red real).",
    )
    parser.add_argument("--root", default=".sdd", help="raíz de estado de trabajo")
    parser.add_argument("--destino", default=None, help="ruta del drills.json")
    args = parser.parse_args(argv)
    reporte = ejecutar_drills(args.root, args.destino)
    for r in reporte["drills"]:
        estado = "PASS" if r["pass"] else "FAIL"
        print(f"[{estado}] {r['drill']}: {r['detalle']}")
    resumen = reporte["resumen"]
    print(f"Resumen: {resumen['pass']} pass / {resumen['fail']} fail")
    return 0 if resumen["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
