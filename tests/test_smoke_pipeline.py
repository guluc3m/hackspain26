from __future__ import annotations

from pathlib import Path

from filemaid.config import AppConfig
from filemaid.pipeline import Pipeline


def _make_text_pdf(path: Path, text: str) -> None:
    stream = f"BT /F1 10 Tf 50 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    path.write_bytes(bytes(out))


def test_pipeline_smoke_end_to_end(tmp_path: Path, monkeypatch) -> None:
    """Verifica el flujo completo de ingestión, extracción, parser, reglas y métricas."""
    data_dir = tmp_path / "data"
    lote = tmp_path / "lote"
    lote.mkdir(parents=True, exist_ok=True)
    outcomes_path = data_dir / "outcomes.jsonl"

    monkeypatch.setenv("FILEMAID_DATA", str(data_dir))

    _make_text_pdf(
        lote / "factura_ok.pdf",
        "FACTURA 2026/001 - Suministros Garcia SL - NIF B12345678 - IBAN ES91 2100 0418 4502 0005 1332"
        " - Pedido P-2026-001 - Fecha: 15/01/2026 - Base: 100,00 EUR - IVA 21% - Cuota IVA: 21,00 EUR - TOTAL : 121,00 EUR",
    )
    _make_text_pdf(
        lote / "factura_nif_raro.pdf",
        "FACTURA 2026/002 - NIF Z99999999 - Pedido P-2026-002 - Fecha: 15/01/2026 - TOTAL : 847,00 EUR",
    )

    cfg = AppConfig.load()
    pipeline = Pipeline(cfg)
    decisions = pipeline.run_lote(lote, outcomes_path)

    assert len(decisions) == 2

    for d in decisions:
        assert d.extraction_ms >= 0
        assert d.parser_ms >= 0
        assert d.evaluation_ms >= 0
        assert d.total_ms >= 0
        assert isinstance(d.timings, dict)
        assert "extraction_ms" in d.timings
        assert "parser_ms" in d.timings
        assert "evaluation_ms" in d.timings
        assert "total_ms" in d.timings

    assert outcomes_path.exists()
    outcomes_lines = [
        line.strip() for line in outcomes_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(outcomes_lines) == len(decisions)

    db_rows = pipeline.store.decision_rows_for_run(pipeline.rule_config.version)
    assert len(db_rows) == len(decisions)
    db_rows_by_file = {r["file_id"]: r for r in db_rows}

    for d in decisions:
        assert d.file_id in db_rows_by_file
        row = db_rows_by_file[d.file_id]
        assert row["result"] == d.result.value
        assert row["extraction_ms"] == d.extraction_ms
        assert row["parser_ms"] == d.parser_ms
        assert row["evaluation_ms"] == d.evaluation_ms
        assert row["total_ms"] == d.total_ms
