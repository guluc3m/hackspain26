"""T9 — métricas de escalabilidad desde ledger sembrado (esperado calculado a mano).

Ficheros de prueba bajo `.sdd/` (estado de trabajo jamás en /tmp).
"""

import json
import shutil
from pathlib import Path

import pytest

from albertitos.metrics import generar_escalabilidad_datos, metricas_escalabilidad


def _ev(iid: str, stage: str, ex: str, lat: int, out: str) -> str:
    sha = "0" * 64
    return (
        '{"kind": "evidence", "invoice_id": "' + iid + '", "stage": "' + stage + '",'
        ' "extractor": "' + ex + '", "extractor_version": "v", "config_version": "c",'
        ' "sha256": "' + sha + '", "latency_ms": ' + str(lat) + ', "confidence": null,'
        ' "outcome": "' + out + '", "detail": "d"}\n'
    )


@pytest.fixture()
def ledger_sembrado() -> Path:
    """2 archivos decididos:
    - A: rung1 100 ms + rung3 200 ms + rung5 (cloud) 500 ms
    - B: rung1 150 ms + rung3 300 ms + rung5 (cloud) 400 ms (error)
    """
    base = Path(".sdd") / "pytest-tmp" / "ledger-metrics"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    lineas = (
        _ev("A", "extract:rung1_pdf_text", "pypdf", 100, "ok")
        + _ev("A", "extract:rung3_tesseract", "tesseract", 200, "ok")
        + _ev("A", "extract:rung5_cloud", "cloud_vlm", 500, "ok")
        + _ev("B", "extract:rung1_pdf_text", "pypdf", 150, "ok")
        + _ev("B", "extract:rung3_tesseract", "tesseract", 300, "ok")
        + _ev("B", "extract:rung5_cloud", "cloud_vlm", 400, "error")
        + _ev("B", "extract:rung2_raster_qr", "pypdfium2", 0, "skipped:sin_imagen")
    )
    (base / "evidencia.jsonl").write_text(lineas, encoding="utf-8")
    (base / "decisiones.jsonl").write_text(
        '{"kind": "decision", "invoice_id": "A", "file_id": "a.pdf", "result": "PAGAR",'
        ' "rule_verdicts": [], "config_snapshot": {"rule_set_version": "v4"}}\n'
        '{"kind": "decision", "invoice_id": "B", "file_id": "b.pdf", "result": "ESCALAR",'
        ' "rule_verdicts": [], "config_snapshot": {"rule_set_version": "v4"}}\n',
        encoding="utf-8",
    )
    yield base
    shutil.rmtree(base.parent)


def test_latencias_por_rung(ledger_sembrado: Path):
    m = metricas_escalabilidad(ledger_sembrado)
    r1 = m["por_rung"]["rung1"]
    assert r1["latencia_media_ms"] == 125  # (100 + 150) / 2
    assert r1["latencia_p95_ms"] == 150  # p95 de 2 valores = el mayor
    assert r1["n_llamadas"] == 2 and r1["errores"] == 0 and r1["etiqueta"] == "medido"
    r3 = m["por_rung"]["rung3"]
    assert r3["latencia_media_ms"] == 250 and r3["latencia_p95_ms"] == 300
    r2 = m["por_rung"]["rung2"]
    assert r2["omitidos"] == 1 and r2["n_llamadas"] == 0  # skipped no cuenta como llamada
    assert r2["etiqueta"] == "sin datos"  # sin latencias válidas


def test_coste_formula_explicita(ledger_sembrado: Path):
    m = metricas_escalabilidad(ledger_sembrado)
    terminos = m["coste_lote"]["terminos"]
    # cloud: 2 llamadas emitidas (1 ok + 1 error) × 0.004 = 0.008
    assert terminos["llamadas_cloud"]["n_llamadas"] == 2
    assert terminos["llamadas_cloud"]["valor_eur"] == 0.008
    # cpu: rungs locales (100+200+150+300) ms = 750 ms = 750/3.6e6 h × 0.12 €/h
    # (las latencias del rung cloud no son tiempo de CPU)
    esperado_cpu = (750 / 3.6e6) * 0.12
    assert terminos["extraccion_cpu"]["valor_eur"] == round(esperado_cpu, 6)
    # agentes: sin telemetría ⇒ sin datos, jamás cifra inventada
    assert terminos["tokens_agentes"]["etiqueta"] == "sin datos"
    assert terminos["tokens_agentes"]["valor_eur"] is None
    # total = cpu + cloud, por archivo repartido entre 2 decisiones
    total = round(esperado_cpu + 0.008, 6)
    assert m["coste_lote"]["total_eur"] == total
    assert m["coste_lote"]["coste_por_archivo"]["valor_eur"] == round(
        (esperado_cpu + 0.008) / 2, 6
    )
    # cada precio de la config lleva su etiqueta
    assert m["coste_lote"]["precios"]["cloud"]["etiqueta_precio"] == "estimado"


def test_throughput_y_limite(ledger_sembrado: Path):
    m = metricas_escalabilidad(ledger_sembrado)
    # archivos con decisión: A y B; tiempo = suma de TODAS sus latencias
    # (A: 800 ms, B: 850 ms — la llamada fallida también consume tiempo)
    assert m["archivos_por_segundo"]["etiqueta"] == "medido"
    assert m["archivos_por_segundo"]["valor"] == round(2 / 1.65, 4)
    # el rung más lento es rung5 (media 500 ms) → límite secuencial 2 archivos/s
    assert m["rung_mas_lento"] == "rung5"
    assert m["limite_throughput_secuencial"]["valor"] == 2.0
    assert m["limite_throughput_secuencial"]["etiqueta"] == "estimado"


def test_hardware_medido(ledger_sembrado: Path):
    m = metricas_escalabilidad(ledger_sembrado)
    hw = m["hardware"]
    n, etiqueta_n = hw["nucleos"]
    assert n.isdigit() and etiqueta_n == "medido"
    assert hw["ram"][1] in ("medido", "sin datos")


def test_sin_datos_no_inventa():
    vacio = Path(".sdd") / "pytest-tmp" / "ledger-metrics-vacio"
    vacio.mkdir(parents=True, exist_ok=True)
    try:
        m = metricas_escalabilidad(vacio)
        assert m["archivos_por_segundo"]["etiqueta"] == "sin datos"
        assert m["limite_throughput_secuencial"]["etiqueta"] == "sin datos"
        assert m["coste_lote"]["etiqueta_total"] == "sin datos"
    finally:
        shutil.rmtree(vacio)


def test_salidas_json_y_typ(ledger_sembrado: Path):
    jdest = Path(".sdd") / "pytest-tmp" / "metrics.json"
    tdest = Path(".sdd") / "pytest-tmp" / "escalabilidad_datos.typ"
    try:
        jdest2, tdest2 = generar_escalabilidad_datos(ledger_sembrado, jdest, tdest)
        datos = json.loads(jdest2.read_text(encoding="utf-8"))
        assert datos["n_decisiones"] == 2
        texto = tdest2.read_text(encoding="utf-8")
        assert '#let latenciasPorRung = (' in texto
        assert '"rung5": ("500 ms", "500 ms", "medido"' in texto
        assert '#let costePorLote = (' in texto
        assert "medido" in texto
    finally:
        jdest.unlink(missing_ok=True)
        tdest.unlink(missing_ok=True)
