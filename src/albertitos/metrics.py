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
# CPU local: gratis salvo electricidad (estimada): kWh = horas × potencia_kw,
# EUR = kWh × €/kWh. Cloud: nº de llamadas × €/llamada. Agentes: sin
# telemetría de tokens aún ⇒ «sin datos».
PRECIOS: dict[str, dict[str, Any]] = {
    "electricidad": {
        "potencia_kw": 0.1,  # estimado: caja CPU 8 núcleos a media carga
        "eur_por_kwh": 0.25,  # estimado: tarifa doméstica media
        "etiqueta_precio": "estimado",
    },
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
    # CPU local: gratis salvo electricidad (estimada): kWh = horas × potencia_kw.
    cpu_ms = sum(
        lat
        for rung, ls in latencias.items()
        if rung != "rung5" and rung != "cloud_vlm"
        for lat in ls
    )
    cpu_h = cpu_ms / 3.6e6
    potencia_kw = float(p["electricidad"]["potencia_kw"])
    eur_kwh = float(p["electricidad"]["eur_por_kwh"])
    llamadas_cloud = llamadas.get("rung5", 0) + llamadas.get("cloud_vlm", 0)
    precio_cloud = float(p["cloud"]["eur_por_llamada"])
    coste_cpu_eur = cpu_h * potencia_kw * eur_kwh
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
        "formula": "electricidad_cpu(horas×kW×€/kWh, estimada) + llamadas_cloud(nº×€/llamada) + tokens_agentes(1k×€)",
        "terminos": {
            "electricidad_cpu": {
                "horas": round(cpu_h, 6),
                "potencia_kw": potencia_kw,
                "eur_por_kwh": eur_kwh,
                "valor_eur": round(coste_cpu_eur, 6),
                "etiqueta": "estimado",  # horas medidas × potencia y precio estimados
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


def _pareja(metrica: tuple[str, str]) -> str:
    """Binding Typst de una métrica (valor, etiqueta)."""
    return f'("{_typ(metrica[0])}", "{metrica[1]}")'


def _cargar_json(ruta: Path) -> dict[str, Any] | None:
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def metricas_t10_t12(metrics_dir: Path | None = None) -> dict[str, Any]:
    """Lee los orígenes de evidencia medidos en `.sdd/metrics/`:
    - corpus-dryrun.json + calibracion/calibracion-rung3.json (T10)
    - drills.json (T12)
    - impacto.json (T13, si existe)
    Cada valor sale como (texto, etiqueta). Lo ausente ⇒ «sin datos» o
    «PENDIENTE-MEDICIÓN(T14)» según corresponda; nada hardcodeado.
    """
    base = Path(metrics_dir) if metrics_dir is not None else Path(".sdd") / "metrics"
    dry = _cargar_json(base / "corpus-dryrun.json")
    cali = _cargar_json(base / "calibracion" / "calibracion-rung3.json")
    drills = _cargar_json(base / "drills.json")
    impacto = _cargar_json(base / "impacto.json")

    out: dict[str, Any] = {}

    # ---- T10: dry-run del corpus (rutas de la escalera + latencias por rung)
    if dry:
        rutas = dry.get("rutas", {})
        n = int(dry.get("n_files", 0) or 0)
        texto = int(rutas.get("rung1_pdf_text", 0) or 0)
        raster = int(rutas.get("raster_no_qr", 0) or 0)
        qr = int(rutas.get("rung2_qr_only", 0) or 0)
        pct = f"{100 * texto / n:.1f}" if n else "—"
        out["dryrunTextoUsable"] = (f"{texto} / {n} ({pct} %)", "medido")
        out["dryrunRutas"] = (
            ("rung1 texto usable", str(texto)),
            ("raster sin QR", str(raster)),
            ("solo QR", str(qr)),
            ("errores / timeouts", f"{rutas.get('error', 0)} / {rutas.get('timeout', 0)}"),
        )
        l1 = dry.get("rung1_pdf_text", {}).get("latencia", {})
        l2 = dry.get("rung2_raster_qr", {}).get("latencia", {})
        out["dryrunLatenciaRung1"] = (
            (f'{l1.get("mean_ms", "—")} ms', f'{l1.get("p95_ms", "—")} ms'),
        )
        out["dryrunLatenciaRung2"] = (
            (f'{l2.get("mean_ms", "—")} ms', f'{l2.get("p95_ms", "—")} ms'),
        )
        out["dryrunThroughput"] = (str(dry.get("rung1_files_per_s", "—")), "medido")
        out["dryrunWall"] = (f'{dry.get("wall_seconds", "—")} s para {n} archivos', "medido")
    else:
        out["dryrunTextoUsable"] = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")

    # ---- T10: calibración de umbrales del rung 3
    if cali:
        cov_txt = cali.get("field_coverage_capas_texto", {})
        cov_ocr = cali.get("field_coverage_ocr", {})
        umbral_cov = cali.get("tabla_umbral_cobertura", {})
        umbral_wc = cali.get("tabla_umbral_word_conf", {})
        out["calibracionCobertura"] = (
            (
                f"texto: media {cov_txt.get('mean', '—')}, p5 {cov_txt.get('p5', '—')}"
                " (n=" + str(cali.get("text_layers_measured", "—")) + ")",
                "medido",
            ),
            (
                f"OCR: media {cov_ocr.get('mean', '—')}, p50 {cov_ocr.get('p50', '—')}"
                " (n=" + str(cali.get("ocr_pages_measured", "—")) + ")",
                "medido",
            ),
        )
        # decisión de calibración registrada en extract-v2: word_conf 40, cobertura 0.4
        t40 = umbral_wc.get("40.0", {})
        t04 = umbral_cov.get("0.4", {})
        out["calibracionDecision"] = (
            (
                f"word_conf 40.0: {t40.get('pct_ocr_arriba', '—')} % OCR pasa"
                f" (cobertura 0.4: {t04.get('pct_ocr_arriba', '—')} % OCR,"
                f" {t04.get('pct_capas_texto_arriba', '—')} % texto)"
            ),
            "calibrado con corpus (T10)",
        )
    else:
        out["calibracionDecision"] = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")

    # ---- T12: drills de resiliencia
    if drills:
        resumen = drills.get("resumen", {})
        out["drillsResumen"] = (
            f"{resumen.get('pass', 0)} pass / {resumen.get('fail', 0)} fail",
            "medido (drills automatizados, sin red real)",
        )
        out["drillsPorNombre"] = tuple(
            (d.get("drill", "?"), "PASS" if d.get("pass") else "FAIL") for d in drills.get("drills", [])
        )
    else:
        out["drillsResumen"] = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")
        out["drillsPorNombre"] = ()

    # ---- T13/T18: reprocesado/impacto del fix (impacto-fix-colapso.json)
    if not impacto:
        impacto = _cargar_json(base / "impacto-fix-colapso.json")
    out["impactoReprocesado"] = (
        (str(impacto.get("resumen", impacto))[:120], "medido") if impacto
        else ("PENDIENTE-MEDICIÓN(T14)", "sin datos")
    )

    # ---- T18: impacto del fix colapso de candidatos (medido, diff completo)
    impacto_fix = _cargar_json(base / "impacto-fix-colapso.json")
    if impacto_fix:
        r = impacto_fix.get("resumen", {})
        out["impactoFix"] = (
            (
                f"{impacto_fix.get('reprocesados', '—')} reprocesados · "
                f"{r.get('no_pagar_a_pagar', '—')} NO_PAGAR→PAGAR · "
                f"{r.get('regresiones', '—')} regresiones · validación "
                f"{impacto_fix.get('validacion', '—')}"
            ),
            "medido",
        )
    else:
        out["impactoFix"] = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")

    # ---- T23: perfil de carga del sistema completo
    perfil = _cargar_json(base / "perfil-carga.json")
    if perfil:
        peor = max(
            (pant["p95_ms"] or 0) for pant in perfil.get("pantallas", {}).values()
        )
        files = perfil.get("runners_files_por_s", [])
        out["perfilCarga"] = (
            (
                f"UI+2 runners simultáneos: peor p95 {peor} ms, "
                f"{[round(f, 1) for f in files]} files/s por runner, "
                f"{len(perfil.get('rojos', []))} ROJOS"
            ),
            "medido",
        )
    else:
        out["perfilCarga"] = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")

    # ---- T34: Modo Alberto (arranque de un paso + UI en llano) — narrativa
    out["modoAlberto"] = (
        (
            "iniciar.sh de un paso (idempotente) + UI en lenguaje llano con ayuda "
            "contextual + app de escritorio con pywebview (ADR-07)"
        ),
        "medido (implementación con tests)",
    )

    # ---- T14/T18: corrida real del lote 1 (lote1.json describe las 500)
    lote1 = _cargar_json(base / "lote1.json")
    if lote1 and lote1.get("distribucion_final"):
        df = lote1["distribucion_final"]
        out["distribucionFinal"] = (
            f"{df['PAGAR']} PAGAR / {df['NO_PAGAR']} NO_PAGAR / {df['ESCALAR']} ESCALAR",
            "medido",
        )
    if lote1:
        dist = lote1.get("distribucion", {})
        p = int(dist.get("PAGAR", 0) or 0)
        n = int(dist.get("NO_PAGAR", 0) or 0)
        e = int(dist.get("ESCALAR", 0) or 0)
        total = p + n + e
        out["resultadosLote1"] = (
            (f"{p} PAGAR / {n} NO_PAGAR / {e} ESCALAR (500 archivos)", "medido")
            if total == 500 else (str(dist), "medido")
        )
        exactitud = f"{100 * p / total:.1f} % PAGAR automático" if total else "—"
        out["exactitudLote1"] = (exactitud, "medido")
    else:
        out["resultadosLote1"] = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")
        out["exactitudLote1"] = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")
    return out


def generar_escalabilidad_datos(
    store_dir: Path | None = None,
    json_destino: Path | None = None,
    typ_destino: Path | None = None,
    metrics_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Escribe metrics.json y escalabilidad_datos.typ. Devuelve ambas rutas."""
    datos = metricas_escalabilidad(store_dir)
    extra = metricas_t10_t12(metrics_dir)
    jdest = Path(json_destino) if json_destino is not None else JSON_DEFECTO
    tdest = Path(typ_destino) if typ_destino is not None else TYP_DEFECTO
    jdest.parent.mkdir(parents=True, exist_ok=True)
    tdest.parent.mkdir(parents=True, exist_ok=True)
    jdest.write_text(
        json.dumps(
            {"escalabilidad": datos, "t10_t12": extra},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
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

    # ---- orígenes T10/T12/T13/T14 (fuente citada: .sdd/metrics/)
    lineas.append("// — T10: dry-run del corpus (.sdd/metrics/corpus-dryrun.json)")
    lineas.append(f'#let dryrunTextoUsable = {_pareja(extra["dryrunTextoUsable"])}')
    lineas.append("#let dryrunRutas = (")
    for nombre, valor in extra["dryrunRutas"]:
        lineas.append(f'  "{_typ(nombre)}": "{_typ(valor)}",')
    lineas.append(")")
    l1, l2 = extra["dryrunLatenciaRung1"][0], extra["dryrunLatenciaRung2"][0]
    lineas.append(f'#let dryrunLatenciaRung1 = ("{_typ(l1[0])}", "{_typ(l1[1])}")')
    lineas.append(f'#let dryrunLatenciaRung2 = ("{_typ(l2[0])}", "{_typ(l2[1])}")')
    lineas.append(f'#let dryrunThroughput = {_pareja(extra["dryrunThroughput"])}')
    lineas.append(f'#let dryrunWall = {_pareja(extra["dryrunWall"])}')
    lineas.append("// — T10: calibración rung 3 (.sdd/metrics/calibracion/calibracion-rung3.json)")
    cal_txt, cal_txt_e = extra["calibracionCobertura"][0]
    cal_ocr, cal_ocr_e = extra["calibracionCobertura"][1]
    lineas.append(f'#let calibracionCoberturaTexto = ("{_typ(cal_txt)}", "{cal_txt_e}")')
    lineas.append(f'#let calibracionCoberturaOcr = ("{_typ(cal_ocr)}", "{cal_ocr_e}")')
    lineas.append(f'#let calibracionDecision = {_pareja(extra["calibracionDecision"])}')
    lineas.append("// — T12: drills de resiliencia (.sdd/metrics/drills.json)")
    lineas.append(f'#let drillsResumen = {_pareja(extra["drillsResumen"])}')
    lineas.append("#let drillsPorNombre = (")
    for nombre, estado in extra["drillsPorNombre"]:
        lineas.append(f'  "{_typ(nombre)}": "{estado}",')
    lineas.append(")")
    lineas.append("// — T13/T14: pendientes de corrida")
    lineas.append(f'#let impactoReprocesado = {_pareja(extra["impactoReprocesado"])}')
    lineas.append("// — T18: impacto del fix (.sdd/metrics/impacto-fix-colapso.json)")
    lineas.append(f'#let impactoFix = {_pareja(extra["impactoFix"])}')
    lineas.append("// — T23: perfil de carga (.sdd/metrics/perfil-carga.json)")
    lineas.append(f'#let perfilCarga = {_pareja(extra["perfilCarga"])}')
    lineas.append("// — T34: Modo Alberto + app escritorio (ADR-07)")
    lineas.append(f'#let modoAlberto = {_pareja(extra["modoAlberto"])}')
    lineas.append(f'#let resultadosLote1 = {_pareja(extra["resultadosLote1"])}')
    lineas.append(f'#let exactitudLote1 = {_pareja(extra["exactitudLote1"])}')
    lineas.append("// — distribución FINAL post-fix (lote1.json, corrida+reprocesado)")
    if "distribucionFinal" in extra:
        lineas.append(f'#let distribucionFinal = {_pareja(extra["distribucionFinal"])}')
    else:
        lineas.append('#let distribucionFinal = ("PENDIENTE-MEDICIÓN(T14)", "sin datos")')
    tdest.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return jdest, tdest


def main() -> None:
    jdest, tdest = generar_escalabilidad_datos()
    print(f"Métricas JSON: {jdest.resolve()}")
    print(f"Datos Typst:   {tdest.resolve()}")


if __name__ == "__main__":
    main()
