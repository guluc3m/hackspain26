"""Perfil de carga del sistema completo, MEDIDO en la caja (T23).

Mide el régimen completo — UI (uvicorn, store real del lote 1) + N runners
concurrentes sobre stores temporales + llama-server — y produce
`.sdd/metrics/perfil-carga.json`:

    uv run python -m albertitos.perfil [--ui-port 8130] [--runners 2]
                                       [--limit 50] [--ui-requests 20]

Todo lo medible es «medido» (RSS por proceso vía /proc, latencias p50/p95/max
de las 5 pantallas con httpx, RAM del sistema); las extrapolaciones van como
«estimado». Si la UI supera 2 s/p95 con el lote completo es un ROJO con causa
— se documenta, no se disimula. Estado de trabajo bajo `.sdd/drills/perfil/`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

JSON_DEFECTO = Path(".sdd/metrics/perfil-carga.json")
REPO = Path(__file__).parents[2]
ROJO_P95_MS = 2000.0  # umbral del ticket: UI > 2 s/página ⇒ ROJO
CLK_TCK = os.sysconf("SC_CLK_TCK")


# ------------------------------------------------------------ medición /proc


def _rss_mb(pid: int) -> float | None:
    """RSS residente en MB desde /proc/<pid>/status (Linux)."""
    try:
        for linea in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if linea.startswith("VmRSS:"):
                return round(int(linea.split()[1]) / 1024, 1)
    except OSError:
        return None
    return None


def _cpu_seconds(pid: int) -> float | None:
    """CPU consumida (user+sys) en segundos desde /proc/<pid>/stat."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        return (int(stat[13]) + int(stat[14])) / CLK_TCK
    except (OSError, IndexError, ValueError):
        return None


def _cpu_pct(pid: int, ventana_s: float = 2.0) -> float | None:
    """% de CPU de un proceso muestreado durante una ventana."""
    a = _cpu_seconds(pid)
    if a is None:
        return None
    time.sleep(ventana_s)
    b = _cpu_seconds(pid)
    if b is None:
        return None
    return round(100 * (b - a) / ventana_s, 1)


def _ram_sistema() -> dict[str, Any]:
    total = disponible = None
    try:
        for linea in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if linea.startswith("MemTotal:"):
                total = round(int(linea.split()[1]) / 1024 / 1024, 1)
            elif linea.startswith("MemAvailable:"):
                disponible = round(int(linea.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    return {
        "total_gb": total,
        "disponible_gb": disponible,
        "etiqueta": "medido" if total is not None else "sin datos",
    }


def _p95(valores: list[float]) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    import math

    return ordenados[max(0, math.ceil(0.95 * len(ordenados)) - 1)]


def _llama_server() -> dict[str, Any]:
    """Health del sidecar llama-server (rung 4) — medido, sin inventar."""
    try:
        r = httpx.get("http://127.0.0.1:8080/health", timeout=2.0)
        if r.status_code == 200:
            return {"estado": ("up", "medido"), "url": "http://127.0.0.1:8080/health"}
    except httpx.HTTPError:
        pass
    return {"estado": ("down", "medido"), "url": "http://127.0.0.1:8080/health"}


# ------------------------------------------------------------- escenario


def _facturas_rapidas(destino: Path, origen_dir: Path, n: int) -> Path:
    """Copia n PDFs CON capa de texto (los 471 medidos en T10) para que los
    runners hagan trabajo real sin colgarse en rung 4 (15 s/página serial)."""
    from pypdf import PdfReader

    destino.mkdir(parents=True, exist_ok=True)
    copiados = 0
    for pdf in sorted(origen_dir.glob("*.pdf")):
        if copiados >= n:
            break
        try:
            if (PdfReader(pdf).pages[0].extract_text() or "").strip():
                shutil.copy(pdf, destino / pdf.name)
                copiados += 1
        except Exception as exc:  # noqa: BLE001 — un PDF roto se salta, se registra
            print(f"perfil: PDF ilegible omitido ({pdf.name}): {exc}", file=sys.stderr)
            continue
    return destino
    return destino


def rojos_de(resumen_pantallas: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """UI > 2 s/página con el lote completo ⇒ ROJO con causa (documentado,
    no parcheado a mano — regla del ticket T23)."""
    peor = max((s["p95_ms"] or 0) for s in resumen_pantallas.values())
    if peor > ROJO_P95_MS:
        return [
            {
                "componente": "ui",
                "causa": f"p95 {peor} ms > 2000 ms con el lote completo cargado "
                "(causa típica: render sin paginación — pendiente, no parcheado a mano)",
            }
        ]
    return []


def _maestro_de(facturas_dir: Path) -> Path:
    """Maestro real junto al directorio de facturas (caja SOLO LECTURA)."""
    candidato = facturas_dir.parent / "FINAL_v7_DEFINITIVO_ahorasi.xlsx"
    if candidato.is_file():
        return candidato
    return REPO / "caja-de-alberto" / "FINAL_v7_DEFINITIVO_ahorasi.xlsx"


def perfilar_carga(
    store_ledger: Path | str = ".sdd/lote1/ledger",
    facturas_dir: Path | str = "/home/deploy/hackspain26/caja-de-alberto/facturas",
    ui_port: int = 8130,
    ui_requests: int = 10,
    runner_limit: int = 50,
    n_runners: int = 2,
    root: Path | str | None = None,
    json_destino: Path | None = None,
) -> dict[str, Any]:
    """Mide el régimen completo y escribe el JSON. Devuelve el reporte."""
    root_path = Path(root) if root is not None else Path(".sdd") / "drills" / "perfil"
    if root_path.exists():
        shutil.rmtree(root_path)
    root_path.mkdir(parents=True)
    jdest = Path(json_destino) if json_destino is not None else JSON_DEFECTO

    facturas_origen = Path(facturas_dir)
    hay_pdf = facturas_origen.is_dir() and any(facturas_origen.glob("*.pdf"))
    pdfs = _facturas_rapidas(root_path / "facturas", facturas_origen, runner_limit) if hay_pdf else None

    # ---- 1) UI en vivo sobre el store real (subproceso, store SOLO LECTURA)
    env = {**os.environ, "ALBERTITOS_STORE": str(store_ledger)}
    ui = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "albertitos.ui.app:app", "--port", str(ui_port)],
        cwd=str(REPO), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    pantallas = ("/", "/facturas", "/revision", "/reglas", "/salud")
    latencias: dict[str, list[float]] = {p: [] for p in pantallas}
    ui_lista = False
    runners: list[dict[str, Any]] = []
    rss: dict[str, float | None] = {"ui": None}
    cpu_pct: dict[str, Any] = {}
    try:
        base = f"http://127.0.0.1:{ui_port}"
        with httpx.Client(timeout=10.0) as cliente:
            for _ in range(60):
                try:
                    if cliente.get(f"{base}/salud").status_code == 200:
                        ui_lista = True
                        break
                except httpx.HTTPError:
                    time.sleep(0.3)

            # ---- 2) runners concurrentes sobre stores TEMPORALES (jamás el real)
            if pdfs is not None:
                for i in range(1, n_runners + 1):
                    p = subprocess.Popen(
                        [
                            sys.executable, "-m", "albertitos.run",
                            "--facturas", str(pdfs),
                            "--store-root", str(root_path / f"runner{i}"),
                            "--outcomes", str(root_path / f"runner{i}" / "outcomes.jsonl"),
                            "--rules", str(REPO / "src/albertitos/rules/regla_v3.yaml"),
                            "--maestro", str(_maestro_de(facturas_origen)),
                            "--limit", str(runner_limit),
                            "--max-in-flight", "2",
                            "--timeout", "60",
                        ],
                        cwd=str(REPO),
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                    )
                    runners.append({"proc": p, "salida": ""})
                    # muestreo inmediato (los runners cortos pueden acabar antes
                    # del primer muestreo de la ventana): RSS pico = máx de muestras
                    rss[f"runner_{p.pid}"] = _rss_mb(p.pid)

            # ---- 3) carga de las 5 pantallas mientras los runners compiten
            for _ in range(ui_requests):
                for p in pantallas:
                    t0 = time.monotonic()
                    try:
                        cliente.get(f"{base}{p}")
                        latencias[p].append((time.monotonic() - t0) * 1000)
                    except httpx.HTTPError:
                        latencias[p].append(10000.0)
            if not ui_lista:
                # UI no arrancable ⇒ degradación total medida (ROJO, no excepción)
                for p in pantallas:
                    latencias[p] = [10000.0] * max(1, ui_requests)
            for r in runners:
                pid = r["proc"].pid
                mb = _rss_mb(pid)
                clave = f"runner_{pid}"
                if mb is not None and (rss.get(clave) is None or mb > rss[clave]):
                    rss[clave] = mb  # pico observado

            # ---- CPU por componente mientras el sistema está en carga
            muestreo_cpu: dict[str, float | None] = {"ui": _cpu_seconds(ui.pid)}
            for r in runners:
                muestreo_cpu[f"runner_{r['proc'].pid}"] = _cpu_seconds(r["proc"].pid)
            time.sleep(2.0)
            cpu_pct: dict[str, Any] = {}
            for nombre, c0 in muestreo_cpu.items():
                pid = ui.pid if nombre == "ui" else int(nombre.split("_")[1])
                c1 = _cpu_seconds(pid)
                cpu_pct[nombre] = (
                    {"cpu_pct": round(100 * (c1 - c0) / 2.0, 1), "etiqueta": "medido"}
                    if c0 is not None and c1 is not None
                    else {"cpu_pct": None, "etiqueta": "sin datos"}
                )
            rss["ui"] = _rss_mb(ui.pid)
            for r in runners:
                pid = r["proc"].pid
                mb = _rss_mb(pid)
                clave = f"runner_{pid}"
                if mb is not None and (rss.get(clave) is None or mb > rss[clave]):
                    rss[clave] = mb  # pico observado

            for r in runners:
                r["proc"].wait(timeout=180)
                r["salida"] = r["proc"].stdout.read() if r["proc"].stdout else ""
        files_por_s = [
            float(x.split("medido ")[1].split(" files/s")[0])
            for r in runners
            for x in [r["salida"]]
            if "medido " in x
        ]
        componentes: dict[str, Any] = {}
        for nombre, mb in rss.items():
            componentes[nombre] = {
                "rss_mb": mb,
                "etiqueta": "medido",
                "cpu_pct": cpu_pct.get(nombre, {"cpu_pct": None, "etiqueta": "sin datos"}),
            }
    finally:
        ui.terminate()
        try:
            ui.wait(timeout=10)
        except subprocess.TimeoutExpired:
            ui.kill()

    # ---- resultados y conclusión
    resumen_pantallas = {
        p: {
            "n": len(v),
            "p50_ms": round(sorted(v)[len(v) // 2], 1) if v else None,
            "p95_ms": round(_p95(v), 1) if v else None,
            "max_ms": round(max(v), 1) if v else None,
            "etiqueta": "medido",
        }
        for p, v in latencias.items()
    }
    rojos = rojos_de(resumen_pantallas)
    ram = _ram_sistema()
    perfil = {
        "generado": time.strftime("%Y-%m-%d %H:%M:%S"),
        "regimen": {
            "n_runners": n_runners,
            "runner_limit": runner_limit,
            "ui_requests": ui_requests,
            "ui_arrancada": ui_lista,
            "etiqueta": "medido",
        },
        "componentes": componentes,
        "llama_server": _llama_server(),
        "pantallas": resumen_pantallas,
        "ram_sistema": ram,
        "runners_files_por_s": files_por_s,
        "concurrencia": {
            "regimen_medido": (
                f"{n_runners} runners (limit {runner_limit}) + UI con el lote completo "
                "simultáneos en esta caja"
            ),
            "soportada": not rojos,
            "etiqueta": "medido",
            "limite_estimado": (
                "con 8 núcleos y rung 4 serializado (≈1 core por runner), el régimen "
                "cómodo estimado es ~4-6 runners + UI; el límite real lo marcaría el "
                "contencioso de CPU en rung 3/4, no la RAM"
            ),
            "nota_mas_ram": (
                f"con {ram['total_gb']} GB y RSS medidos de ~{round(max((m or 0) for m in rss.values()), 1)} MB "
                "por componente, la RAM NO es el cuello (sobran GB): con más RAM el "
                "régimen no cambia; el límite es CPU en rung 3/4 (estimado)"
            ),
        },
        "rojos": rojos,
        "fuentes": {
            "rss": "/proc/<pid>/status VmRSS",
            "cpu": "/proc/<pid>/stat utime+stime",
            "latencias": "httpx contra 127.0.0.1 (loopback)",
            "ram": "/proc/meminfo",
        },
    }
    jdest.parent.mkdir(parents=True, exist_ok=True)
    jdest.write_text(json.dumps(perfil, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return perfil


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="albertitos.perfil", description="Perfil de carga del sistema completo (T23)."
    )
    parser.add_argument("--store", default=".sdd/lote1/ledger")
    parser.add_argument("--facturas", default="/home/deploy/hackspain26/caja-de-alberto/facturas")
    parser.add_argument("--ui-port", type=int, default=8130)
    parser.add_argument("--ui-requests", type=int, default=10)
    parser.add_argument("--runners", type=int, default=2)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--destino", default=None)
    args = parser.parse_args(argv)
    perfil = perfilar_carga(
        store_ledger=args.store,
        facturas_dir=args.facturas,
        ui_port=args.ui_port,
        ui_requests=args.ui_requests,
        runner_limit=args.limit,
        n_runners=args.runners,
        json_destino=Path(args.destino) if args.destino else None,
    )
    print(f"Componentes medidos: {len(perfil['componentes'])}")
    for pantalla, m in perfil["pantallas"].items():
        print(f"  {pantalla}: p50 {m['p50_ms']} ms · p95 {m['p95_ms']} ms · máx {m['max_ms']} ms")
    for nombre, c in perfil["componentes"].items():
        print(f"  RSS {nombre}: {c['rss_mb']} MB · CPU {c['cpu_pct']['cpu_pct']} %")
    print(f"ROJO: {len(perfil['rojos'])}")
    print(f"JSON: {Path(args.destino).resolve() if args.destino else JSON_DEFECTO.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
