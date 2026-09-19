"""Datos del informe (`albertitos_plan.pdf`) generados desde el store (T6).

Regla dura del ticket: los números del informe salen de evidencia MEDIDA del
ledger en `.sdd/ledger/`; lo que no esté medido se declara «sin datos medidos»,
nunca se inventa. Uso:

    uv run python -m albertitos.report_data   # escribe docs/report/datos.typ

`docs/report/escalabilidad.typ` importa ese fichero, de modo que el PDF se
compila (`typst compile`) siempre con cifras reales o con el marcador honesto
de ausencia de datos.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

DESTINO_DEFECTO = Path("docs/report/datos.typ")
RESULTADOS = ("PAGAR", "NO_PAGAR", "ESCALAR")
SIN_DATOS = ("sin datos medidos todavía", "sin datos")


def datos_informe(store_dir: Path | None = None) -> dict[str, Any]:
    """Extrae las métricas del informe desde el ledger.

    Cada métrica es una tupla (valor, etiqueta) con etiqueta 'medido' o
    'sin datos', salvo las que son dict de métricas.
    """
    if store_dir is None:
        # Fuente real: el store SQLite del runner (T8). El ledger solo queda
        # como ruta explícita (tests / formatos legacy).
        return _datos_desde_store(Path(".sdd") / "store.db")
    base = Path(store_dir)
    if base.is_dir() and not base.is_file() and base.name != ".sdd":
        return _datos_desde_ledger(base)
    if base.is_dir():
        return _datos_desde_ledger(base / "ledger")
    return _datos_desde_store(base if base.suffix == ".db" else base / "store.db")


def _datos_desde_ledger(base: Path) -> dict[str, Any]:
    decisiones: list[dict[str, Any]] = []
    evidencia: list[dict[str, Any]] = []
    if base.is_dir():
        for ruta in sorted(base.glob("*.jsonl")):
            try:
                lineas = ruta.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for linea in lineas:
                try:
                    rec = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if rec.get("kind") == "decision":
                    decisiones.append(rec)
                elif rec.get("kind") == "evidence":
                    evidencia.append(rec)

    conteo = Counter(d.get("result", "?") for d in decisiones)
    paginas = {(e.get("invoice_id"), e.get("page")) for e in evidencia if e.get("page")}
    latencias = [e["latency_ms"] for e in evidencia if isinstance(e.get("latency_ms"), int)]
    costes = [e["cost_eur"] for e in evidencia if isinstance(e.get("cost_eur"), (int, float))]
    repeticiones = Counter(
        (e.get("invoice_id"), e.get("stage"), e.get("extractor")) for e in evidencia
    )
    version = next(
        (
            d.get("config_snapshot", {}).get("rule_set_version")
            for d in reversed(decisiones)
            if d.get("config_snapshot", {}).get("rule_set_version")
        ),
        None,
    )
    extractores = Counter(str(e.get("extractor")) for e in evidencia)

    def m(valor: str) -> tuple[str, str]:
        return valor, "medido"

    return {
        "facturasDecididas": m(str(len(decisiones))),
        "conteoResultados": {r: m(str(conteo.get(r, 0))) for r in RESULTADOS},
        "paginasExtraccion": m(str(len(paginas))),
        "latenciaMedia": (
            m(f"{round(sum(latencias) / len(latencias))} ms") if latencias else SIN_DATOS
        ),
        "costeAcumulado": m(f"{sum(costes):.2f} EUR") if costes else SIN_DATOS,
        "versionReglas": m(str(version)) if version else SIN_DATOS,
        # Se medirán con lotes reales; mientras tanto, marcador honesto.
        "facturasPorSegundo": SIN_DATOS,
        "costePorFactura": SIN_DATOS,
        "extractores": {k: m(str(v)) for k, v in sorted(extractores.items())},
        "reintentos": m(str(sum(1 for v in repeticiones.values() if v > 1))),
        "omisiones": m(
            str(sum(1 for e in evidencia if str(e.get("outcome", "")).startswith("skipped")))
        ),
        "erroresProveedor": m(
            str(sum(1 for e in evidencia if e.get("outcome") == "error"))
        ),
    }


def _datos_desde_store(db_path: Path) -> dict[str, Any]:
    """Métricas desde el store real (SQLite: invoices + evidence, T4/T8).

    Mismas claves que el lector de ledger; cifras MEDIDAS o 'sin datos'.
    """
    import sqlite3

    if not db_path.exists():
        return _datos_desde_ledger(Path("/no/existe"))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        decisiones = conn.execute(
            "SELECT file_id, result, config_version FROM invoices"
        ).fetchall()
        evidencia = conn.execute(
            "SELECT file_id, stage, extractor, extractor_version, "
            "config_version, latency_ms, outcome, detail FROM evidence"
        ).fetchall()
    finally:
        conn.close()

    conteo = Counter(str(r["result"]) for r in decisiones)
    version = next(
        (str(r["config_version"]) for r in reversed(decisiones)
         if r["config_version"]),
        None,
    )
    latencias = [int(r["latency_ms"]) for r in evidencia
                 if r["latency_ms"] is not None]
    paginas = sum(
        1 for r in evidencia
        if str(r["stage"]).startswith("extract:")
    )  # una fila de extract:rungN por página (T1)
    repeticiones = Counter(
        (r["file_id"], r["stage"], r["extractor"]) for r in evidencia
    )
    extractores = Counter(str(r["extractor"]) for r in evidencia)

    def m(valor: str) -> tuple[str, str]:
        return valor, "medido"

    # throughput medido por el runner (estado de la última corrida)
    fps = SIN_DATOS
    estado = Path(".sdd") / "state" / "runner.json"
    try:
        rj = json.loads(estado.read_text(encoding="utf-8"))
        if rj.get("files_per_second"):
            fps = m(f"{rj['files_per_second']} archivos/s")
    except (OSError, json.JSONDecodeError, KeyError):
        pass

    return {
        "facturasDecididas": m(str(len(decisiones))),
        "conteoResultados": {r: m(str(conteo.get(r, 0))) for r in RESULTADOS},
        "paginasExtraccion": m(str(paginas)),
        "latenciaMedia": (
            m(f"{round(sum(latencias) / len(latencias))} ms") if latencias else SIN_DATOS
        ),
        "costeAcumulado": SIN_DATOS,  # el store no factura coste: honesto
        "versionReglas": m(version) if version else SIN_DATOS,
        "facturasPorSegundo": fps,
        "costePorFactura": SIN_DATOS,
        "extractores": {k: m(str(v)) for k, v in sorted(extractores.items())},
        "reintentos": m(str(sum(1 for v in repeticiones.values() if v > 1))),
        "omisiones": m(
            str(sum(1 for r in evidencia
                    if str(r["outcome"] or "").startswith("skipped")))
        ),
        "erroresProveedor": m(
            str(sum(1 for r in evidencia if r["outcome"] == "error"))
        ),
    }


def _typ(valor: str) -> str:
    return valor.replace("\\", "\\\\").replace('"', '\\"')


def _pareja(metrica: tuple[str, str]) -> str:
    return f'("{_typ(metrica[0])}", "{metrica[1]}")'


def generar_datos_typ(store_dir: Path | None = None, destino: Path | None = None) -> Path:
    """Escribe `datos.typ` con bindings #let para importar desde la plantilla."""
    d = datos_informe(store_dir)
    lineas = [
        "// Generado por albertitos.report_data — NO editar a mano.",
        "// Cada métrica es (valor, etiqueta) con etiqueta 'medido' o 'sin datos'.",
        f"#let facturasDecididas = {_pareja(d['facturasDecididas'])}",
        "#let conteoResultados = (",
    ]
    for r in RESULTADOS:
        lineas.append(f'  "{r}": {_pareja(d["conteoResultados"][r])},')
    lineas.append(")")
    for clave in (
        "paginasExtraccion",
        "latenciaMedia",
        "costeAcumulado",
        "versionReglas",
        "facturasPorSegundo",
        "costePorFactura",
    ):
        lineas.append(f"#let {clave[0].lower() + clave[1:]} = {_pareja(d[clave])}")
    lineas.append("#let extractores = (:)" if not d["extractores"] else "#let extractores = (")
    for nombre, pareja in d["extractores"].items():
        lineas.append(f'  "{_typ(nombre)}": {_pareja(pareja)},')
    if d["extractores"]:
        lineas.append(")")
    for clave in ("reintentos", "omisiones", "erroresProveedor"):
        lineas.append(f"#let {clave[0].lower() + clave[1:]} = {_pareja(d[clave])}")

    destino_final = Path(destino) if destino is not None else DESTINO_DEFECTO
    destino_final.parent.mkdir(parents=True, exist_ok=True)
    destino_final.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return destino_final


def main() -> None:
    destino = generar_datos_typ()
    print(f"Datos del informe generados: {destino.resolve()}")


if __name__ == "__main__":
    main()
