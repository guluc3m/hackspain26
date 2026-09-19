from __future__ import annotations

from pathlib import Path

from filemaid.config import AppConfig
from filemaid.pipeline import Pipeline


def make_text_pdf(path: Path, text: str) -> None:
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


def main() -> None:
    lote = Path("data/smoke/lote1")
    lote.mkdir(parents=True, exist_ok=True)
    make_text_pdf(
        lote / "factura_ok.pdf",
        "FACTURA 2026/001 - Suministros Garcia SL - NIF B12345678 - IBAN ES91 2100 0418 4502 0005 1332"
        " - Pedido P-2026-001 - Fecha: 15/01/2026 - Base: 100,00 EUR - IVA 21% - Cuota IVA: 21,00 EUR - TOTAL : 121,00 EUR",
    )
    make_text_pdf(
        lote / "factura_nif_raro.pdf",
        "FACTURA 2026/002 - NIF Z99999999 - Pedido P-2026-002 - Fecha: 15/01/2026 - TOTAL : 847,00 EUR",
    )

    cfg = AppConfig.load()
    pipeline = Pipeline(cfg)
    outcomes_path = Path("data/smoke/outcomes.jsonl")
    decisions = pipeline.run_lote(lote, outcomes_path)

    assert len(decisions) >= 2, f"Esperadas al menos 2 decisiones, obtenidas {len(decisions)}"
    for d in decisions:
        for e in d.rule_evaluations:
            print(f"  {e.code:26} {e.verdict.value:8} {e.reason}")
        print(
            f"{d.file_id}: {d.result.value} "
            f"(extraction={d.extraction_ms}ms, parser={d.parser_ms}ms, eval={d.evaluation_ms}ms, total={d.total_ms}ms)"
        )

        # Assert in code that decisions contain stage metrics
        assert d.extraction_ms >= 0, f"extraction_ms inválido: {d.extraction_ms}"
        assert d.parser_ms >= 0, f"parser_ms inválido: {d.parser_ms}"
        assert d.evaluation_ms >= 0, f"evaluation_ms inválido: {d.evaluation_ms}"
        assert d.total_ms >= 0, f"total_ms inválido: {d.total_ms}"
        assert isinstance(d.timings, dict), f"timings no es dict: {d.timings}"
        assert "extraction_ms" in d.timings
        assert "parser_ms" in d.timings
        assert "evaluation_ms" in d.timings
        assert "total_ms" in d.timings

    # 3. Verify outcomes.jsonl and database rows in SQLite
    assert outcomes_path.exists(), f"outcomes_path no existe: {outcomes_path}"
    outcomes_lines = [
        line.strip() for line in outcomes_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(outcomes_lines) == len(decisions)

    db_rows = pipeline.store.decision_rows_for_run(pipeline.rule_config.version)
    assert len(db_rows) >= len(decisions), f"Filas en DB ({len(db_rows)}) < decisiones ({len(decisions)})"
    db_rows_by_file = {r["file_id"]: r for r in db_rows}

    for d in decisions:
        assert d.file_id in db_rows_by_file, f"Fila en DB no encontrada para {d.file_id}"
        row = db_rows_by_file[d.file_id]
        assert row["result"] == d.result.value
        assert row["extraction_ms"] == d.extraction_ms
        assert row["parser_ms"] == d.parser_ms
        assert row["evaluation_ms"] == d.evaluation_ms
        assert row["total_ms"] == d.total_ms

    print("Smoke skeleton verification PASSED: all stage metrics verified in decisions, outcomes.jsonl, and SQLite.")


if __name__ == "__main__":
    main()
