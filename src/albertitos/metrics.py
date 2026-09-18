"""Métricas de escalabilidad y coste, medidas desde el ledger (T9).

Solo lectura del store/ledger; salida en dos sitios:
  - JSON en `.sdd/metrics/metrics.json` (estado de trabajo, regenerable)
  - `docs/report/escalabilidad_datos.typ` (bindings #let que la plantilla
    del informe incluye — los números del informe salen de aquí, jamás
    hardcodeados)

Fórmula de coste explícita (cada término separado, medido vs estimado):
    coste_lote = extracción CPU (horas × €/h, estimado)
               + llamadas cloud (nº llamadas × €/llamada)
               + tokens de agentes (€/1k tokens × tokens usados)

Los precios unitarios viven en PRECIOS (config, no código de decisión); cada
precio lleva su etiqueta. Lo que no esté medido se declara «sin datos».
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from albertitos.ui.ledger import load_ledger

JSON_DEFECTO = Path(".sdd/metrics/metrics.json")
TYP_DEFECTO = Path("docs/report/escalabilidad_datos.typ")
LOTE_REFERENCIA = 500

# Precios unitarios (config — cada precio lleva su etiqueta de origen).
# rung5/cloud: nº de llamadas × €/llamada. CPU: tiempo × €/h (amortización).
# Agentes: 1k tokens × € (sin telemetría de tokens aún ⇒ «sin datos»).
PRECIOS: dict[str, dict[str, Any]] = {
    "cpu": {"eur_por_hora": 0.12, "etiqueta_precio": "estimado"},
    "cloud": {"eur_por_llamada": 0.004, "etiqueta_precio": "estimado"},
    "agentes": {"eur_por_1k_tokens": 0.0, "etiqueta_precio": "sin datos"},
}


def _rung_de(stage: str, extractor: str) -> str:
    """Rung normal: 'extract:rung3_tesseract' -> 'rung3'; si no, el extractor."""
    m = re.search(r"rung(\d+)", stage)
    if m:
        return f"rung{m.group(1)}"
    return extractor or "desconocido"


def _p95(valores: list[int]) -> int:
    """Percentil 95 discreto: elemento en la posición ceil(0.95·n)."""
    if not valores:
        return 0
    ordenados = sorted(valores)
    import math

    idx = max(0, math.ceil(0.95 * len(ordenados)) - 1)
    return ordenados[idx]


def _hardware() -> dict[str, Any]:
    núcleos = os.cpu_count()
    ram_gb: str | None = None
    try:
        for linea in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if linea.startswith("MemTotal:"):
                ram_gb = f"{int(linea.split()[1]) / 1024 / 1024:.1f} GB"
                break
    except OSError:
        pass
    fuera = {"nucleos": núcleos is not None, "ram": ram_gb is not None}
    return {
        "nucleos": (
            (str(núcleos), "medido") if núcleos is not None else ("desconocido", "sin datos")
        ),
        "ram": (ram_gb, "medido") if ram_gb else ("desconocido", "sin datos"),
        "_todo_medido": all(fuera.values()),
    }


def metricas_escalabilidad(
    store_dir: Path | None = None, precios: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Extrae métricas medidas del ledger. Todo lo posible es «medido»; lo que
    falte se declara «sin datos» y las proyecciones se marcan «estimado»."""
    base = Path(store_dir) if store_dir else Path(".sdd") / "ledger"
    p = precios if precios is not None else PRECIOS
    registros = load_ledger(base)
    evidencia = [r for r in registros if r.get("kind") == "evidence"]
    decisiones = [r for r in registros if r.get("kind") == "decision"]

    # ---- latencia media y p95 por rung (solo filas con éxito: outcome ok) ----
    latencias: dict[str, list[int]] = defaultdict(list)
    llamadas: Counter[str] = Counter()
    errores: Counter[str] = Counter()
    omitidos: Counter[str] = Counter()
    for e in evidencia:
        rung = _rung_de(str(e.get("stage", "")), str(e.get("extractor", "")))
        outcome = str(e.get("outcome", ""))
        if outcome.startswith("skipped"):
            omitidos[rung] += 1
            continue
        llamadas[rung] += 1
        if outcome == "error":
            errores[rung] += 1
        elif isinstance(e.get("latency_ms"), int) and e["latency_ms"] > 0:
            latencias[rung].append(int(e["latency_ms"]))
    por_rung: dict[str, dict[str, Any]] = {}
    for rung in sorted(set(latencias) | set(llamadas) | set(omitidos)):
        ls = latencias.get(rung, [])
        por_rung[rung] = {
            "n_llamadas": llamadas.get(rung, 0),
            "errores": errores.get(rung, 0),
            "omitidos": omitidos.get(rung, 0),
            "latencia_media_ms": round(sum(ls) / len(ls)) if ls else None,
            "latencia_p95_ms": _p95(ls) if ls else None,
            "etiqueta": "medido" if ls else "sin datos",
        }

    # ---- archivos/s medidos: archivos con decisión ÷ tiempo total invertido
    lat_por_invoice: dict[str, int] = defaultdict(int)
    for e in evidencia:
        if isinstance(e.get("latency_ms"), int):
            lat_por_invoice[str(e.get("invoice_id"))] += int(e["latency_ms"])
    decididas = {str(d.get("invoice_id")) for d in decisiones} & set(lat_por_invoice)
    tiempo_total_s = sum(lat_por_invoice[i] for i in decididas) / 1000
    if decididas and tiempo_total_s > 0:
        archivos_s = ({"valor": round(len(decididas) / tiempo_total_s, 4), "etiqueta": "medido"})
        archivos_s["nota"] = "suma de latencias por archivo (sin paralelismo)"
    else:
        archivos_s = {"valor": None, "etiqueta": "sin datos", "nota": ""}

    # ---- límite de throughput: rung más lento manda (secuencial, estimado)
    lentos = {
        r: m["latencia_media_ms"]
        for r, m in por_rung.items()
        if m["latencia_media_ms"] is not None
    }
    if lentos:
        rung_lento = max(lentos, key=lambda k: lentos[k])  # type: ignore[arg-type]
        limite = round(1000 / lentos[rung_lento], 4)
        limite_max = {
            "valor": limite,
            "etiqueta": "estimado",
            "rung_mas_lento": rung_lento,
            "nota": f"1 / latencia media de {rung_lento} (secuencial)",
        }
    else:
        rung_lento, limite_max = None, {"valor": None, "etiqueta": "sin datos", "nota": ""}

    # ---- coste por archivo y fórmula de coste del lote
    cpu_ms = sum(
        lat
        for rung, ls in latencias.items()
        if rung != "rung5" and rung != "cloud_vlm"
        for lat in ls
    )
    cpu_h = cpu_ms / 3.6e6
    precio_cpu = float(p["cpu"]["eur_por_hora"])
    llamadas_cloud = llamadas.get("rung5", 0) + llamadas.get("cloud_vlm", 0)
    precio_cloud = float(p["cloud"]["eur_por_llamada"])
    coste_cpu_eur = cpu_h * precio_cpu
    coste_cloud_eur = llamadas_cloud * precio_cloud
    n_archivos = len(decididas) if decididas else len(lat_por_invoice)
    coste_total = coste_cpu_eur + coste_cloud_eur
    coste_archivo = (
        {"valor_eur": round(coste_total / n_archivos, 6), "etiqueta": "medido×precio estimado"}
        if n_archivos and (cpu_ms or llamadas_cloud)
        else {"valor_eur": None, "etiqueta": "sin datos"}
    )
    coste_lote = {
        "lote": LOTE_REFERENCIA,
        "formula": "extraccion_CPU(horas×EUR/h) + llamadas_cloud(nº×EUR/llamada) + tokens_agentes(1k×EUR)",
        "terminos": {
            "extraccion_cpu": {
                "horas": round(cpu_h, 6),
                "eur_por_hora": precio_cpu,
                "valor_eur": round(coste_cpu_eur, 6),
                "etiqueta": "estimado",  # latencias medidas × precio estimado
            },
            "llamadas_cloud": {
                "n_llamadas": llamadas_cloud,
                "eur_por_llamada": precio_cloud,
                "valor_eur": round(coste_cloud_eur, 6),
                "etiqueta": "medido×precio estimado",
            },
            "tokens_agentes": {
                "valor_eur": None,
                "etiqueta": "sin datos",
                "nota": "sin telemetría de tokens de agentes en la evidencia",
            },
        },
        "total_eur": round(coste_total, 6),
        "etiqueta_total": "estimado" if (cpu_ms or llamadas_cloud) else "sin datos",
        "coste_por_archivo": coste_archivo,
        "precios": p,
    }
    hardware = _hardware()

    return {
        "n_archivos_con_evidencia": len(lat_por_invoice),
        "n_decisiones": len(decisiones),
        "archivos_por_segundo": archivos_s,
        "por_rung": por_rung,
        "rung_mas_lento": rung_lento,
        "limite_throughput_secuencial": limite_max,
        "coste_lote": coste_lote,
        "hardware": hardware,
        "etiquetas": {
            "medido": "calculado desde filas de evidencia del ledger",
            "estimado": "proyección sobre datos medidos (precio o paralelismo)",
            "sin datos": "no hay evidencia suficiente; no se inventa cifra",
        },
    }


def _typ(valor: Any) -> str:
    return str(valor).replace("\\", "\\\\").replace('"', '\\"')


def generar_escalabilidad_datos(
    store_dir: Path | None = None,
    json_destino: Path | None = None,
    typ_destino: Path | None = None,
) -> tuple[Path, Path]:
    """Escribe metrics.json y escalabilidad_datos.typ. Devuelve ambas rutas."""
    datos = metricas_escalabilidad(store_dir)
    jdest = Path(json_destino) if json_destino is not None else JSON_DEFECTO
    tdest = Path(typ_destino) if typ_destino is not None else TYP_DEFECTO
    jdest.parent.mkdir(parents=True, exist_ok=True)
    tdest.parent.mkdir(parents=True, exist_ok=True)
    jdest.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lineas = [
        "// Generado por albertitos.metrics — NO editar a mano.",
        "// Números medidos desde el ledger; cada valor lleva su etiqueta.",
        "#let latenciasPorRung = (:)" if not datos["por_rung"] else "#let latenciasPorRung = (",
    ]
    for rung, m in datos["por_rung"].items():
        media = "—" if m["latencia_media_ms"] is None else f'{m["latencia_media_ms"]} ms'
        p95 = "—" if m["latencia_p95_ms"] is None else f'{m["latencia_p95_ms"]} ms'
        lineas.append(
            f'  "{rung}": ("{_typ(media)}", "{_typ(p95)}", "{m["etiqueta"]}",'
            f' "{m["n_llamadas"]} llamadas, {m["errores"]} errores"),'
        )
    if datos["por_rung"]:
        lineas.append(")")
    aps = datos["archivos_por_segundo"]
    v = "—" if aps["valor"] is None else str(aps["valor"])
    lineas.append(f'#let archivosPorSegundo = ("{_typ(v)}", "{aps["etiqueta"]}")')
    lim = datos["limite_throughput_secuencial"]
    vlim = "—" if lim["valor"] is None else str(lim["valor"])
    lineas.append(f'#let limiteThroughput = ("{_typ(vlim)}", "{lim["etiqueta"]}")')
    lineas.append(
        f'#let rungMasLento = ("{_typ(datos["rung_mas_lento"] or "—")}", "medido")'
    )
    formula = datos["coste_lote"]
    lineas.append("#let formulaCoste = (")
    for nombre, t in formula["terminos"].items():
        valor = "sin datos" if t["valor_eur"] is None else f'{t["valor_eur"]:.4f} EUR'
        lineas.append(f'  "{nombre}": ("{_typ(valor)}", "{t["etiqueta"]}"),')
    lineas.append(")")
    ca = formula["coste_por_archivo"]
    va = "sin datos" if ca["valor_eur"] is None else f'{ca["valor_eur"]:.4f} EUR'
    lineas.append(f'#let costePorArchivo = ("{_typ(va)}", "{ca["etiqueta"]}")')
    total = formula["total_eur"]
    lineas.append(
        f'#let costePorLote = ("{_typ(f"{total:.4f} EUR por lote de {formula["lote"]}")}",'
        f' "{formula["etiqueta_total"]}")'
    )
    hw = datos["hardware"]
    n = hw["nucleos"]
    lineas.append(
        f'#let hardware = ("{_typ(n[0] if isinstance(n, tuple) else n)} núcleos",'
        f' "{n[1] if isinstance(n, tuple) else "medido"}")'
    )
    lineas.append(f'#let hardwareRam = ("{_typ(hw["ram"][0])}", "{hw["ram"][1]}")')
    tdest.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return jdest, tdest


def main() -> None:
    jdest, tdest = generar_escalabilidad_datos()
    print(f"Métricas JSON: {jdest.resolve()}")
    print(f"Datos Typst:   {tdest.resolve()}")


if __name__ == "__main__":
    main()
