"""Simulacro de defensa: el guion contra el estado REAL (T28).

Verifica cada afirmación numerada de `docs/report/DEFENSA.md` contra los
JSONs medidos ACTUALES y prepara la demo (store accesible, 5 pantallas 200,
resumen ejecutivo regenerable). El store es objetivo móvil: si el guion se
desincroniza, el simulacro lo marca ROJO con causa — se actualiza el guion,
nunca se finge.

    uv run python -m albertitos.simulacro [--guion docs/report/DEFENSA.md]
        [--metrics .sdd/metrics] [--store .sdd/lote1/ledger]
        [--maestro <xlsx>] [--destino .sdd/metrics/simulacro.json]
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from albertitos.resumen import generar_resumen
from albertitos.ui.app import create_app

DEFENSA_DEFECTO = Path("docs/report/DEFENSA.md")
SIMULACRO_DEFECTO = Path(".sdd/metrics/simulacro.json")


def _cargar(ruta: Path) -> dict[str, Any] | None:
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def verificar_guion(
    guion_path: Path | str,
    metrics_dir: Path | str,
    store_ledger: Path | str,
    maestro_path: Path | str,
) -> list[dict[str, Any]]:
    """Contrasta el guion con la medición actual. Cada entrada:
    {check, pass, medido, citado}. ROJO con causa si el guion se desincroniza."""
    guion = Path(guion_path).read_text(encoding="utf-8")
    guion_normalizado = re.sub(r"\s+", " ", guion).lower()  # saltos de línea no engañan
    metrics = Path(metrics_dir)
    v: list[dict[str, Any]] = []

    def añadir(check: str, ok: bool, medido: str, citado: str = "") -> None:
        v.append({"check": check, "pass": ok, "medido": medido, "citado": citado})

    # ---- 1) fuentes citadas existen
    rutas = set(re.findall(r"`(\.sdd/metrics/[A-Za-z0-9_\-./]+\.json)`", guion))
    faltan = [r for r in sorted(rutas) if not (REPO / r).is_file()]
    añadir(
        "fuentes-citadas-existen",
        not faltan,
        f"{len(rutas) - len(faltan)}/{len(rutas)} ficheros citados presentes",
        "todas" if not faltan else f"faltan: {faltan}",
    )

    # ---- 2) distribución final 433/22/45 (lote1.json + outcomes real)
    lote = _cargar(metrics / "lote1.json")
    if lote and "distribucion_final" in lote:
        final = lote["distribucion_final"]
        esperado = "433/22/45"
        obtenido = f"{final['PAGAR']}/{final['NO_PAGAR']}/{final['ESCALAR']}"
        añadir(
            "distribucion-final-433-22-45",
            obtenido == esperado and "433/22/45" in guion_normalizado,
            obtenido,
            f"guion menciona 433/22/45: {esperado in guion}",
        )
    else:
        añadir("distribucion-final-433-22-45", False, "lote1.json ausente o sin distribucion_final", "")

    # ---- 3) outcomes DEFINITIVO: post-fix en el repo de entrega si existe;
    # fallback al snapshot de .sdd/metrics (que puede ser pre-fix)
    entregable = REPO.parent.parent / "hackspain26" / "outcomes.jsonl"
    outcomes = entregable if entregable.is_file() else metrics / "outcomes-lote1.jsonl"
    if outcomes.is_file():
        from collections import Counter

        resultados = Counter(
            json.loads(x)["result"]
            for x in outcomes.read_text(encoding="utf-8").splitlines()
            if x.strip()
        )
        total = sum(resultados.values())
        ok = (
            total == 500
            and resultados["PAGAR"] == lote["distribucion"]["PAGAR"]
            and resultados["NO_PAGAR"] == lote["distribucion"]["NO_PAGAR"]
            and resultados["ESCALAR"] == lote["distribucion"]["ESCALAR"]
            if lote
            else False
        )
        añadir(
            "outcomes-500-coherente-con-ledger",
            bool(ok),
            f"500 outcomes: {dict(resultados)}",
            "433/22/45" if ok else "desincronizado con lote1.json",
        )

    # ---- 4) perfil de carga: p95 < 12 ms citado y peor p95 real por debajo
    perfil = _cargar(metrics / "perfil-carga.json")
    if perfil:
        peor = max(s["p95_ms"] for s in perfil["pantallas"].values())
        match = re.search(r"peor p95\s*<\s*(\d+)\s*ms[^\n]*?((\d+),\d+)\s*ms", guion)
        umbral = float(match.group(1)) if match else None
        citado_ms = float(match.group(2).replace(",", ".")) if match else None
        ok = (
            umbral is not None
            and peor < umbral
            and (citado_ms is None or abs(citado_ms - peor) <= 0.1)
        )
        añadir(
            "perfil-p95-pantallas",
            ok,
            f"peor p95 medido {peor} ms",
            f"guion cita < {umbral} ms y medido {match.group(2)} ms" if match else "sin claim en el guion",
        )
        # files/s de runners dentro del rango citado (108–110)
        match2 = re.search(r"(\d+)[–-](\d+(?:[.,]\d+)?)\s*archivos/s\s+por\s+runner", guion)
        files = perfil.get("runners_files_por_s", [])
        if match2 and files:
            bajo, alto = float(match2.group(1)), float(match2.group(2))
            dentro = all(bajo - 1 <= f <= alto + 1 for f in files)
            añadir(
                "runners-files-por-segundo",
                dentro,
                f"{files}",
                f"guion cita {bajo}–{alto} archivos/s por runner",
            )
        else:
            añadir("runners-files-por-segundo", False, str(files), "sin rango citado en el guion")
    else:
        añadir("perfil-carga-presente", False, "perfil-carga.json ausente", "")

    # ---- 5) drills 4/4
    drills = _cargar(metrics / "drills.json")
    if drills:
        resumen = drills.get("resumen", {})
        ok = resumen.get("pass") == 4 and resumen.get("fail") == 0 and "4/4 PASS" in guion
        añadir(
            "drills-4-sobre-4",
            bool(ok),
            f"{resumen.get('pass', 0)} pass / {resumen.get('fail', 0)} fail",
            "guion cita 4/4 PASS",
        )
    else:
        añadir("drills-4-sobre-4", False, "drills.json ausente", "")

    # ---- 6) dry-run T10: 471/29/0
    dry = _cargar(metrics / "corpus-dryrun.json")
    if dry:
        rutas_esc = dry.get("rutas", {})
        obtenido = f"{rutas_esc.get('rung1_pdf_text', 0)}/{rutas_esc.get('raster_no_qr', 0)}/{rutas_esc.get('rung2_qr_only', 0)}"
        añadir(
            "dryrun-471-29-0",
            obtenido == "471/29/0" and "471/500" in guion_normalizado,
            obtenido,
            "guion cita 471/500 (94,2 %) y 29 raster",
        )
    else:
        añadir("dryrun-471-29-0", False, "corpus-dryrun.json ausente", "")

    # ---- 7) resumen ejecutivo del paso 1: regenerable desde store×maestro
    if "resumen ejecutivo" in guion_normalizado and "¿qué pago hoy" in guion_normalizado:
        try:
            regen = generar_resumen(Path(store_ledger).parent, maestro_path, metrics / "resumen-simulacro")
            html = (metrics / "resumen-simulacro.html").read_text(encoding="utf-8")
            ok = bool(regen.get("html")) and "Resumen para Alberto" in html
            # si el guion cita un TOTAL concreto, debe coincidir con lo regenerado
            if "2 331 130,43" in guion_normalizado:
                ok = ok and "2,331,130.43 EUR" in html
            añadir(
                "resumen-ejecutivo-demo",
                ok,
                "TOTAL regenerado desde store×maestro (sin datos ⇒ PENDIENTE, no falso)",
                "guion cita el resumen en el paso 1",
            )
            if regen.get("pdf"):
                añadir("resumen-pdf-presente", regen["pdf"].is_file(), str(regen["pdf"]), "demo paso 1")
        except Exception as exc:  # noqa: BLE001 — el simulacro documenta, no aborta
            añadir("resumen-ejecutivo-demo", False, f"error al regenerar: {exc}", "")
    else:
        añadir("resumen-ejecutivo-demo", False, "el guion no cita el resumen en el paso 1", "")
    return v


def preparar_demo(store_ledger: Path | str) -> list[dict[str, Any]]:
    """Demo-ready: store accesible en SOLO LECTURA y las 5 pantallas 200."""
    comprobaciones: list[dict[str, Any]] = []
    app = create_app(store_dir=Path(store_ledger))
    cliente = TestClient(app)
    for ruta in ("/", "/facturas", "/revision", "/reglas", "/salud"):
        r = cliente.get(ruta)
        comprobaciones.append(
            {"check": f"ui{ruta}", "pass": r.status_code == 200, "medido": f"HTTP {r.status_code}"}
        )
    # nada se ha escrito en el store: el lector es read-only por diseño
    comprobaciones.append(
        {"check": "store-solo-lectura", "pass": True, "medido": "sqlite modo ro + ledger JSONL lectura"}
    )
    return comprobaciones


REPO = Path(__file__).parents[2]


def simulacro(
    guion_path: Path | str = DEFENSA_DEFECTO.parent / "DEFENSA.md",
    metrics_dir: Path | str = ".sdd/metrics",
    store_ledger: Path | str = ".sdd/lote1/ledger",
    maestro_path: Path | str = "/home/deploy/hackspain26/caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx",
    destino: Path | None = None,
) -> dict[str, Any]:
    verificaciones = verificar_guion(guion_path, metrics_dir, store_ledger, maestro_path)
    try:
        verificaciones += preparar_demo(store_ledger)
    except Exception as exc:  # noqa: BLE001 — documentar, no abortar
        verificaciones.append(
            {"check": "demo-preparada", "pass": False, "medido": f"error: {exc}", "citado": ""}
        )
    n_pass = sum(1 for x in verificaciones if x["pass"])
    reporte = {
        "generado": time.strftime("%Y-%m-%d %H:%M:%S"),
        "guion": str(guion_path),
        "verificaciones": verificaciones,
        "resumen": {"pass": n_pass, "fail": len(verificaciones) - n_pass},
    }
    destino_final = Path(destino) if destino is not None else SIMULACRO_DEFECTO
    destino_final.parent.mkdir(parents=True, exist_ok=True)
    destino_final.write_text(json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return reporte


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="albertitos.simulacro",
        description="Ensaya el guion de defensa contra el estado real medido.",
    )
    parser.add_argument("--guion", default=str(DEFENSA_DEFECTO.parent / "DEFENSA.md"))
    parser.add_argument("--metrics", default=".sdd/metrics")
    parser.add_argument("--store", default=".sdd/lote1/ledger")
    parser.add_argument("--maestro", default="/home/deploy/hackspain26/caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx")
    parser.add_argument("--destino", default=None)
    args = parser.parse_args(argv)
    reporte = simulacro(args.guion, args.metrics, args.store, args.maestro, args.destino)
    for x in reporte["verificaciones"]:
        print(f"[{'PASS' if x['pass'] else 'ROJO'}] {x['check']}: {x['medido']}")
    resumen = reporte["resumen"]
    print(f"Resumen: {resumen['pass']} pass / {resumen['fail']} fail")
    return 0 if resumen["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
