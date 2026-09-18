"""T11 — el informe se alimenta de datos generados, jamás hardcodeados.

El binario typst NO participa en tests: aquí se valida que la plantilla
importa los ficheros de datos generados desde el store y que estos se
regeneran desde un ledger sembrado.
"""

from pathlib import Path

DOCS = Path(__file__).parent.parent / "docs" / "report"


def test_plantilla_importa_datos_generados():
    """escalabilidad.typ toma sus números de los .typ generados, no de constantes."""
    fuente = (DOCS / "escalabilidad.typ").read_text(encoding="utf-8")
    assert '#import "datos.typ": *' in fuente
    assert '#import "escalabilidad_datos.typ": *' in fuente


def test_datos_tip_regenerables_desde_ledger_sembrado(tmp_path: Path):
    """El flujo store → datos .typ funciona con ledger sembrado (T6+T9)."""
    from albertitos.metrics import generar_escalabilidad_datos
    from albertitos.report_data import generar_datos_typ

    base = DOCS.parent.parent / ".sdd" / "pytest-tmp" / "ledger-t11"
    base.mkdir(parents=True, exist_ok=True)
    (base / "decisiones.jsonl").write_text(
        '{"kind": "decision", "invoice_id": "X", "file_id": "x.pdf", "result":'
        ' "PAGAR", "rule_verdicts": [], "config_snapshot": {"rule_set_version": "v4"}}\n',
        encoding="utf-8",
    )
    try:
        d1 = Path(".sdd") / "pytest-tmp" / "datos_t11.typ"
        d2 = Path(".sdd") / "pytest-tmp" / "escal_t11.typ"
        try:
            generar_datos_typ(base, d1)
            generar_escalabilidad_datos(base, d2.parent / "metrics-t11.json", d2)
            assert "v4" in d1.read_text(encoding="utf-8")
            assert "#let archivosPorSegundo" in d2.read_text(encoding="utf-8")
        finally:
            d1.unlink(missing_ok=True)
            (d2.parent / "metrics-t11.json").unlink(missing_ok=True)
            d2.unlink(missing_ok=True)
    finally:
        shutil_rmtree(base)


def shutil_rmtree(base: Path) -> None:
    import shutil

    shutil.rmtree(base.parent)
