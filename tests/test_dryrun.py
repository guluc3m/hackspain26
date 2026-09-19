"""T10 · Dry-run sobre corpus + calibración (rungs 1–2, sin VLM).

Idempotencia byte a byte en re-run (0 re-procesos), rutas que cuadran con el
total, fallos registrados sin abortar, y concurrencia ≤ 2.
"""

from __future__ import annotations

import json
from pathlib import Path

from albertitos.extract.dryrun import DryRunOptions, run_dryrun

FIXTURES = Path(__file__).parent / "fixtures"


def make_opts(tmp_path: Path, **kw) -> DryRunOptions:
    base = {
        "corpus_dir": FIXTURES,
        "out_path": tmp_path / "metrics" / "corpus-dryrun.json",
        "evidence_path": tmp_path / "metrics" / "evidence.jsonl",
        "cache_root": tmp_path / "cache" / "dryrun",
    }
    base.update(kw)
    return DryRunOptions(**base)


class TestIdempotencia:
    def test_rerun_byte_identico_y_cero_reprocesos(self, tmp_path):
        opts = make_opts(tmp_path)
        first = run_dryrun(opts)
        n_evidence_1 = len(opts.evidence_path.read_text().splitlines())

        second = run_dryrun(opts)
        n_evidence_2 = len(opts.evidence_path.read_text().splitlines())

        # métricas idénticas (salvo el tiempo de pared, que es de la corrida)
        a = json.loads(json.dumps(first))
        b = json.loads(json.dumps(second))
        a.pop("wall_seconds"), b.pop("wall_seconds")
        assert a == b

        # 0 re-procesos: la 2ª corrida solo añade filas cache_hit… más los
        # REINTENTOS del rung 4 (T24): un skip TRANSIENTE de proveedor no se
        # cachea, así el re-run lo reintenta (recuperación posible). Ese
        # reintento es gratis (local, sin billing) y determinista.
        fresh_second = [
            json.loads(line)
            for line in opts.evidence_path.read_text().splitlines()[n_evidence_1:]
            if json.loads(line)["outcome"] != "cache_hit"
        ]
        assert all(
            ev["stage"] == "extract:rung4_vlm" and ev["outcome"] == "skipped"
            for ev in fresh_second
        ), fresh_second
        assert n_evidence_2 > n_evidence_1  # se registran los cache_hit (traza)

    def test_metrics_file_generated_and_valid(self, tmp_path):
        opts = make_opts(tmp_path)
        run_dryrun(opts)
        data = json.loads(opts.out_path.read_text())
        assert data["kind"] == "corpus-dryrun"
        assert data["n_files"] == 6  # 3 texto + 2 scans + qr_only
        assert data["rutas"]["rung1_pdf_text"] == 3
        assert data["rutas"]["raster_no_qr"] == 2
        assert data["rutas"]["rung2_qr_only"] == 1

    def test_rutas_cuadran_con_total(self, tmp_path):
        opts = make_opts(tmp_path)
        metrics = run_dryrun(opts)
        assert sum(metrics["rutas"].values()) == metrics["n_files"]
        assert metrics["n_files"] == 6


class TestLimitOnly:
    def test_limit_reduces_corpus(self, tmp_path):
        metrics = run_dryrun(make_opts(tmp_path, limit=2))
        assert metrics["n_files"] == 2
        assert sum(metrics["rutas"].values()) == 2

    def test_only_glob_filters(self, tmp_path):
        metrics = run_dryrun(make_opts(tmp_path, only="scan_*.pdf"))
        assert metrics["n_files"] == 2
        assert metrics["rutas"]["raster_no_qr"] == 2
        assert metrics["rutas"]["rung1_pdf_text"] == 0

    def test_workers_capped_at_two(self, tmp_path):
        metrics = run_dryrun(make_opts(tmp_path, max_workers=16))
        assert metrics["concurrencia_max"] == 2  # regla dura T10


class TestFallos:
    def test_corrupt_pdf_recorded_and_batch_continues(self, tmp_path):
        corrupt = tmp_path / "corpus"
        corrupt.mkdir()
        (corrupt / "roto.pdf").write_bytes(b"%PDF-roto no es un pdf")
        import shutil

        for f in FIXTURES.glob("*.pdf"):
            shutil.copy(f, corrupt / f.name)
        metrics = run_dryrun(make_opts(tmp_path, corpus_dir=corrupt))
        assert metrics["rutas"]["error"] == 1
        assert metrics["rutas"]["rung1_pdf_text"] == 3  # el lote siguió
        assert metrics["rutas"]["raster_no_qr"] == 2
        assert any(f["file_id"] == "roto.pdf" for f in metrics["fallos"])
        assert sum(metrics["rutas"].values()) == metrics["n_files"]

    def test_missing_corpus_raises(self, tmp_path):
        import pytest

        with pytest.raises(FileNotFoundError):
            run_dryrun(make_opts(tmp_path, corpus_dir=tmp_path / "no-existe"))


class TestDryRunNoDecide:
    def test_metrics_contain_no_payment_results(self, tmp_path):
        """El dry-run NO decide: PAGAR/NO_PAGAR/ESCALAR no aparecen."""
        metrics = run_dryrun(make_opts(tmp_path))
        blob = json.dumps(metrics)
        for banned in ("PAGAR", "NO_PAGAR", "ESCALAR"):
            assert banned not in blob

    def test_latencies_measured_from_cache_survive_rerun(self, tmp_path):
        """Las latencias no se re-miden: re-run conserva la medida original."""
        opts = make_opts(tmp_path)
        first = run_dryrun(opts)
        second = run_dryrun(opts)
        assert first["rung1_pdf_text"]["latencia"] == second["rung1_pdf_text"]["latencia"]
        assert first["rung1_files_per_s"] == second["rung1_files_per_s"]
