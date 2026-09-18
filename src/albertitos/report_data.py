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
    base = Path(store_dir) if store_dir else Path(".sdd") / "ledger"
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
