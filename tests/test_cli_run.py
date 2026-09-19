from __future__ import annotations

from unittest.mock import MagicMock, patch

from filemaid.run import main
from filemaid.types import Decision, Result


def test_cli_run_prints_metrics_summary(capsys, tmp_path):
    lote_dir = tmp_path / "lote"
    lote_dir.mkdir()

    d1 = Decision(
        invoice_id="inv-1",
        file_id="factura_1.pdf",
        result=Result.PAGAR,
        extraction_ms=120,
        parser_ms=30,
        evaluation_ms=10,
        total_ms=160,
    )
    d2 = Decision(
        invoice_id="inv-2",
        file_id="factura_2.pdf",
        result=Result.NO_PAGAR,
        extraction_ms=200,
        parser_ms=50,
        evaluation_ms=20,
        total_ms=270,
    )

    mock_pipeline = MagicMock()
    mock_pipeline.run_lote.return_value = [d1, d2]
    mock_pipeline.rule_config.version = "v1"

    with patch("filemaid.run.Pipeline", return_value=mock_pipeline):
        ret = main(["run", "--lote", str(lote_dir), "--no-report"])

    assert ret == 0
    captured = capsys.readouterr().out
    assert "PAGAR: 1" in captured
    assert "NO_PAGAR: 1" in captured
    assert "ESCALAR: 0" in captured
    assert "tiempo: 430 ms total · 215.0 ms/factura" in captured
    assert "(extracción: 320 ms · parser: 80 ms · reglas: 30 ms)" in captured
