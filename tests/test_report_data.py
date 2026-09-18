"""T6 — flujo de datos del informe desde el store (el binario typst NO va en tests).

Los ficheros de prueba se siembran bajo `.sdd/` (estado de trabajo jamás en /tmp).
"""

import shutil
from pathlib import Path

import pytest

from albertitos.report_data import datos_informe, generar_datos_typ


@pytest.fixture()
def ledger_sembrado() -> Path:
    base = Path(".sdd") / "pytest-tmp" / "ledger-report"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    (base / "evidencia.jsonl").write_text(
        '{"kind": "evidence", "invoice_id": "X1", "stage": "decide",'
        ' "extractor": "rule-engine", "extractor_version": "v4",'
        ' "config_version": "c1", "sha256": "' + "0" * 64 + '", "latency_ms": 120,'
        ' "confidence": null, "outcome": "ok", "detail": "ok", "cost_eur": 0.5}\n'
        '{"kind": "evidence", "invoice_id": "X1", "stage": "decide",'
        ' "extractor": "rule-engine", "extractor_version": "v4",'
        ' "config_version": "c1", "sha256": "' + "0" * 64 + '", "latency_ms": 80,'
        ' "confidence": null, "outcome": "ok", "detail": "reintento", "cost_eur": 0.0}\n'
        '{"kind": "evidence", "invoice_id": "X2", "stage": "extract",'
        ' "extractor": "cloud_vlm", "extractor_version": "g", "config_version": "c1",'
        ' "sha256": "' + "1" * 64 + '", "latency_ms": 900, "confidence": null,'
        ' "outcome": "error", "detail": "HTTP 429"}\n'
        '{"kind": "evidence", "invoice_id": "X3", "stage": "extract",'
        ' "extractor": "pypdf", "extractor_version": "5", "config_version": "c1",'
        ' "sha256": "' + "2" * 64 + '", "latency_ms": 100, "confidence": null,'
        ' "outcome": "skipped:sin_capa_de_texto", "detail": "escaneo"}\n',
        encoding="utf-8",
    )
    (base / "decisiones.jsonl").write_text(
        '{"kind": "decision", "invoice_id": "X1", "file_id": "a.pdf", "result":'
        ' "PAGAR", "rule_verdicts": [], "config_snapshot": {"rule_set_version": "v4"}}\n'
        '{"kind": "decision", "invoice_id": "X2", "file_id": "b.pdf", "result":'
        ' "ESCALAR", "rule_verdicts": [], "config_snapshot": {"rule_set_version": "v4"}}\n',
        encoding="utf-8",
    )
    yield base
    shutil.rmtree(base.parent)


def test_metricas_desde_ledger(ledger_sembrado: Path):
    d = datos_informe(ledger_sembrado)
    assert d["facturasDecididas"] == ("2", "medido")
    assert d["conteoResultados"]["PAGAR"] == ("1", "medido")
    assert d["conteoResultados"]["ESCALAR"] == ("1", "medido")
    assert d["conteoResultados"]["NO_PAGAR"] == ("0", "medido")
    assert d["latenciaMedia"][0].endswith("ms")
    assert d["costeAcumulado"] == ("0.50 EUR", "medido")
    assert d["versionReglas"] == ("v4", "medido")
    assert d["reintentos"][0] == "1"  # X1/decide/rule-engine x2
    assert d["erroresProveedor"][0] == "1"
    assert d["omisiones"][0] == "1"


def test_sin_datos_no_inventa(ledger_sembrado: Path):
    """Sin ledger: las métricas se declaran 'sin datos', nunca cifras inventadas."""
    vacio = Path(".sdd") / "pytest-tmp" / "ledger-report-vacio"
    vacio.mkdir(parents=True, exist_ok=True)
    try:
        d = datos_informe(vacio)
        assert d["facturasDecididas"] == ("0", "medido")
        assert d["costeAcumulado"][1] == "sin datos"
        assert d["versionReglas"][1] == "sin datos"
    finally:
        shutil.rmtree(vacio)


def test_generar_datos_typ(ledger_sembrado: Path):
    destino = Path(".sdd") / "pytest-tmp" / "datos.typ"
    try:
        generar_datos_typ(ledger_sembrado, destino)
        texto = destino.read_text(encoding="utf-8")
        assert "#let facturasDecididas = (\"2\", \"medido\")" in texto
        assert '"PAGAR": ("1", "medido")' in texto
        # las métricas aún no medidas aparecen con su marcador honesto
        assert '("sin datos medidos todavía", "sin datos")' in texto
    finally:
        destino.unlink(missing_ok=True)


def test_generar_datos_typ_vacio():
    destino = Path(".sdd") / "pytest-tmp" / "datos_vacio.typ"
    vacio = Path(".sdd") / "pytest-tmp" / "ledger-typ-vacio"
    vacio.mkdir(parents=True, exist_ok=True)
    try:
        generar_datos_typ(vacio, destino)
        texto = destino.read_text(encoding="utf-8")
        assert '("sin datos medidos todavía", "sin datos")' in texto
    finally:
        destino.unlink(missing_ok=True)
        shutil.rmtree(vacio)
