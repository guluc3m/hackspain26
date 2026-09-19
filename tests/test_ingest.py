"""Ingesta asíncrona: cola durable, reanudación, limpieza y rutas HTTP."""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from pathlib import Path, PurePosixPath

import pytest

from filemaid.config import AppConfig
from filemaid.extract.cache import sha256_file
from filemaid.ingest import (
    IngestionService,
    UploadTooLarge,
    _JobClaim,
    safe_file_id,
    safe_rel_path,
    stream_uploads,
)
from filemaid.store.pouch import file_key


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
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    path.write_bytes(bytes(out))


_OK_TEXT = (
    "FACTURA 2026/001 - Suministros Garcia SL - NIF B12345678 - IBAN ES91 2100 0418 4502 0005 1332"
    " - Pedido P-2026-001 - Fecha: 15/01/2026 - Base: 100,00 EUR - IVA 21% - Cuota IVA: 21,00 EUR"
    " - TOTAL : 121,00 EUR"
)


def _wait(service: IngestionService, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = service.status(job_id)
        assert state is not None
        if state["state"] in {"complete", "failed"}:
            return state
        time.sleep(0.05)
    raise AssertionError(f"trabajo {job_id} no terminó: {service.status(job_id)}")


def _persist_job(service: IngestionService, job_id: str, rel: str, source: Path) -> Path:
    """Escribe el estado durable de un trabajo sin encolarlo (simula un crash)."""
    job_dir = service.jobs_dir / job_id
    child = uuid.uuid4().hex
    file_id = PurePosixPath(rel).name
    dest = job_dir / child / file_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    sha = sha256_file(dest)
    artifact_id = service.store.artifact(
        {"scan_id": f"job-{job_id}", "job_id": job_id},
        "job_input",
        file_id,
        dest,
        "application/pdf",
    )
    service.store.put(
        {
            "_id": f"job:{job_id}",
            "kind": "job",
            "job_id": job_id,
            "origin": "upload",
            "expected": [
                {
                    "file_id": file_id,
                    "sha256": sha,
                    "file_key": file_key(file_id, sha),
                    "artifact_id": artifact_id,
                    "staged": f"{child}/{file_id}",
                }
            ],
            "created_at": time.time(),
        }
    )
    return dest


def _multipart(parts: list[tuple[str, bytes, bytes]], boundary: str = "BOUND") -> tuple[bytes, str]:
    """Construye un cuerpo multipart crudo (filename en bytes, sin normalizar)."""
    chunks = []
    for filename, data, content_type in parts:
        chunks.append(
            b"--"
            + boundary.encode()
            + b'\r\nContent-Disposition: form-data; name="files"; filename="'
            + filename
            + b'"\r\nContent-Type: '
            + content_type
            + b"\r\n\r\n"
            + data
            + b"\r\n"
        )
    chunks.append(b"--" + boundary.encode() + b"--\r\n")
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


async def _stream(body: bytes, content_type: str, dest: Path, **kwargs) -> dict:
    async def chunks():
        for i in range(0, len(body), 7):
            yield body[i : i + 7]

    return await stream_uploads(chunks(), content_type, dest, **kwargs)


def test_submit_processes_and_removes_transient_cache(tmp_path: Path, cfg: AppConfig) -> None:
    source = tmp_path / "factura_ok.pdf"
    _make_text_pdf(source, _OK_TEXT)
    service = IngestionService(cfg)
    try:
        result = service.submit([("factura_ok.pdf", source)], origin="upload")
        assert result["rejected"] == []
        assert result["accepted"][0]["file_id"] == "factura_ok.pdf"
        job_id = result["job_id"]
        state = _wait(service, job_id)
        assert state["state"] == "complete"
        assert state["counts"] == {"total": 1, "done": 1, "error": 0, "pending": 0}
        item = state["items"][0]
        assert item["status"] == "done"
        assert item["result"] in {"PAGAR", "NO_PAGAR", "ESCALAR"}
        # Evidence persisted in PouchDB, transient staging removed.
        assert service.store.get(item["decision_id"]) is not None
        assert not (Path(cfg.root) / "work" / "jobs" / job_id).exists()
        assert not (cfg.root / "scans" / item["scan_id"]).exists()
        # The durable input artifact survives the cache removal.
        job = service.store.get(f"job:{job_id}")
        assert service.store.get(job["expected"][0]["artifact_id"]) is not None
    finally:
        service.stop()


def test_invalid_pdf_rejected_and_not_queued(tmp_path: Path, cfg: AppConfig) -> None:
    bad = tmp_path / "factura.pdf"
    bad.write_bytes(b"this is not a pdf at all")
    service = IngestionService(cfg)
    try:
        with pytest.raises(ValueError):
            service.submit([("factura.pdf", bad)], origin="upload")
        assert service.list_jobs()["jobs"] == []
    finally:
        service.stop()


def test_processing_failure_is_terminal_and_cleans_cache(tmp_path: Path, cfg: AppConfig) -> None:
    corrupt = tmp_path / "roto.pdf"
    corrupt.write_bytes(b"%PDF-1.4\nnot a real pdf body")
    service = IngestionService(cfg)
    try:
        result = service.submit([("roto.pdf", corrupt)], origin="upload")
        job_id = result["job_id"]
        state = _wait(service, job_id)
        assert state["state"] == "failed"
        assert state["items"][0]["status"] == "error"
        assert state["items"][0]["error"]
        # The original is safe in PouchDB, so the transient cache is removed too.
        assert not (Path(cfg.root) / "work" / "jobs" / job_id).exists()
    finally:
        service.stop()


def test_duplicate_basename_distinct_content_are_distinct(tmp_path: Path, cfg: AppConfig) -> None:
    first = tmp_path / "a" / "factura.pdf"
    second = tmp_path / "b" / "factura.pdf"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    _make_text_pdf(first, _OK_TEXT)
    _make_text_pdf(second, _OK_TEXT + " - Referencia extra 999")
    service = IngestionService(cfg)
    try:
        result = service.submit(
            [("a/factura.pdf", first), ("b/factura.pdf", second)], origin="upload"
        )
        assert result["rejected"] == []
        keys = {item["file_key"] for item in result["accepted"]}
        assert len(keys) == 2
        assert {item["file_id"] for item in result["accepted"]} == {"factura.pdf"}
        state = _wait(service, result["job_id"])
        assert state["state"] == "complete"
        assert state["counts"]["done"] == 2
        assert len({item["scan_id"] for item in state["items"]}) == 2
    finally:
        service.stop()


def test_same_basename_same_bytes_is_deduplicated(tmp_path: Path, cfg: AppConfig) -> None:
    first = tmp_path / "a" / "factura.pdf"
    second = tmp_path / "b" / "factura.pdf"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    _make_text_pdf(first, _OK_TEXT)
    shutil.copyfile(first, second)
    service = IngestionService(cfg)
    try:
        result = service.submit(
            [("a/factura.pdf", first), ("b/factura.pdf", second)], origin="upload"
        )
        assert len(result["accepted"]) == 1
        assert result["rejected"][0]["rel_path"] == "b/factura.pdf"
        state = _wait(service, result["job_id"])
        assert state["state"] == "complete"
        assert state["counts"] == {"total": 1, "done": 1, "error": 0, "pending": 0}
    finally:
        service.stop()


def test_duplicate_relative_path_rejected(tmp_path: Path, cfg: AppConfig) -> None:
    source = tmp_path / "factura.pdf"
    _make_text_pdf(source, _OK_TEXT)
    service = IngestionService(cfg)
    try:
        result = service.submit(
            [("sub/factura.pdf", source), ("sub/factura.pdf", source)], origin="upload"
        )
        assert len(result["accepted"]) == 1
        assert result["rejected"][0]["rel_path"] == "sub/factura.pdf"
    finally:
        service.stop()


def test_resume_pending_job_from_pouchdb(tmp_path: Path, cfg: AppConfig) -> None:
    source = tmp_path / "factura.pdf"
    _make_text_pdf(source, _OK_TEXT)
    writer = IngestionService(cfg)
    job_id = str(uuid.uuid4())
    _persist_job(writer, job_id, "factura.pdf", source)
    writer.stop()  # crash before the worker ever ran

    resumed = IngestionService(cfg)
    try:
        assert resumed.status(job_id)["state"] == "queued"
        resumed.resume()
        state = _wait(resumed, job_id)
        assert state["state"] == "complete"
        assert state["items"][0]["result"] in {"PAGAR", "NO_PAGAR", "ESCALAR"}
    finally:
        resumed.stop()


def test_resume_restores_original_from_artifact_when_cache_gone(
    tmp_path: Path, cfg: AppConfig
) -> None:
    source = tmp_path / "factura.pdf"
    _make_text_pdf(source, _OK_TEXT)
    writer = IngestionService(cfg)
    job_id = str(uuid.uuid4())
    staged = _persist_job(writer, job_id, "factura.pdf", source)
    writer.stop()
    staged.unlink()  # the transient cache is gone; only the DB artifact remains

    resumed = IngestionService(cfg)
    try:
        resumed.resume()
        state = _wait(resumed, job_id)
        assert state["state"] == "complete"
        assert state["items"][0]["result"] in {"PAGAR", "NO_PAGAR", "ESCALAR"}
    finally:
        resumed.stop()


def _persist_job_raw(
    service: IngestionService,
    job_id: str,
    file_id: str,
    source: Path,
    *,
    staged: str,
    artifact_id: str | None = None,
) -> None:
    job_dir = service.jobs_dir / job_id
    dest = job_dir / "keep" / file_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    sha = sha256_file(dest)
    if artifact_id is None:
        artifact_id = service.store.artifact(
            {"scan_id": f"job-{job_id}", "job_id": job_id},
            "job_input",
            file_id,
            dest,
            "application/pdf",
        )
    service.store.put(
        {
            "_id": f"job:{job_id}",
            "kind": "job",
            "job_id": job_id,
            "origin": "upload",
            "expected": [
                {
                    "file_id": file_id,
                    "sha256": sha,
                    "file_key": file_key(file_id, sha),
                    "artifact_id": artifact_id,
                    "staged": staged,
                }
            ],
            "created_at": time.time(),
        }
    )


def test_untrusted_staged_path_is_ignored_and_restored_from_artifact(
    tmp_path: Path, cfg: AppConfig
) -> None:
    source = tmp_path / "factura.pdf"
    _make_text_pdf(source, _OK_TEXT)
    writer = IngestionService(cfg)
    job_id = str(uuid.uuid4())
    _persist_job_raw(writer, job_id, "factura.pdf", source, staged="../../pouchdb")
    writer.stop()

    resumed = IngestionService(cfg)
    try:
        resumed.resume()
        state = _wait(resumed, job_id)
        # The doc-provided path is never used: the item is restored from the artifact.
        assert state["state"] == "complete"
        assert state["items"][0]["result"] in {"PAGAR", "NO_PAGAR", "ESCALAR"}
        assert (cfg.root / "pouchdb").exists()
    finally:
        resumed.stop()


def test_foreign_artifact_is_rejected(tmp_path: Path, cfg: AppConfig) -> None:
    source = tmp_path / "factura.pdf"
    _make_text_pdf(source, _OK_TEXT)
    writer = IngestionService(cfg)
    other_job = str(uuid.uuid4())
    _persist_job_raw(writer, other_job, "factura.pdf", source, staged="keep/factura.pdf")
    foreign = writer.store.get(f"job:{other_job}")["expected"][0]["artifact_id"]

    job_id = str(uuid.uuid4())
    _persist_job_raw(
        writer, job_id, "factura.pdf", source, staged="../../pouchdb", artifact_id=foreign
    )
    writer.stop()

    resumed = IngestionService(cfg)
    try:
        resumed.resume()
        state = _wait(resumed, job_id)
        assert state["state"] == "failed"
        assert state["items"][0]["status"] == "error"
    finally:
        resumed.stop()


def test_job_claim_is_exclusive_across_services(tmp_path: Path, cfg: AppConfig) -> None:
    first = _JobClaim(tmp_path / "job.lock")
    second = _JobClaim(tmp_path / "job.lock")
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()


def test_upload_route_multipart_accepts_and_completes(tmp_path: Path, cfg: AppConfig) -> None:
    from fastapi.testclient import TestClient

    from filemaid.api.app import create_app

    source = tmp_path / "factura.pdf"
    _make_text_pdf(source, _OK_TEXT)
    app = create_app(cfg)
    with TestClient(app) as client:
        response = client.post(
            "/api/ingest",
            files=[("files", ("sub/factura.pdf", source.read_bytes(), "application/pdf"))],
        )
        assert response.status_code == 202
        body = response.json()
        assert body["rejected"] == []
        assert body["accepted"][0]["rel_path"] == "sub/factura.pdf"
        job_id = body["job_id"]
        deadline = time.monotonic() + 30
        state = client.get(f"/api/jobs/{job_id}").json()
        while state["state"] not in {"complete", "failed"} and time.monotonic() < deadline:
            time.sleep(0.05)
            state = client.get(f"/api/jobs/{job_id}").json()
        assert state["state"] == "complete"
        assert state["items"][0]["result"] in {"PAGAR", "NO_PAGAR", "ESCALAR"}
        assert client.get("/api/jobs").json()["jobs"][0]["job_id"] == job_id


def test_upload_route_rejects_unsupported_suffix(tmp_path: Path, cfg: AppConfig) -> None:
    from fastapi.testclient import TestClient

    from filemaid.api.app import create_app

    app = create_app(cfg)
    with TestClient(app) as client:
        response = client.post(
            "/api/ingest",
            files=[("files", ("notas.txt", b"hola", "text/plain"))],
        )
        assert response.status_code == 400


def test_upload_route_reports_partial_rejection(tmp_path: Path, cfg: AppConfig) -> None:
    from fastapi.testclient import TestClient

    from filemaid.api.app import create_app

    source = tmp_path / "factura.pdf"
    _make_text_pdf(source, _OK_TEXT)
    app = create_app(cfg)
    with TestClient(app) as client:
        response = client.post(
            "/api/ingest",
            files=[
                ("files", ("factura.pdf", source.read_bytes(), "application/pdf")),
                ("files", ("notas.txt", b"hola", "text/plain")),
            ],
        )
        assert response.status_code == 202
        body = response.json()
        assert [item["file_id"] for item in body["accepted"]] == ["factura.pdf"]
        assert body["rejected"][0]["rel_path"] == "notas.txt"


def test_stream_uploads_rejects_incomplete_multipart(tmp_path: Path) -> None:
    body, content_type = _multipart([(b"factura.pdf", b"%PDF-1.4\n", b"application/pdf")])
    truncated = body[: -len(b"--BOUND--\r\n")]  # terminal boundary missing
    with pytest.raises(ValueError):
        asyncio.run(_stream(truncated, content_type, tmp_path))


def test_stream_uploads_enforces_aggregate_limit(tmp_path: Path) -> None:
    body, content_type = _multipart(
        [(b"factura.pdf", b"%PDF-1.4\n" + b"x" * 4096, b"application/pdf")]
    )
    with pytest.raises(UploadTooLarge):
        asyncio.run(_stream(body, content_type, tmp_path, max_total_bytes=1024))


def test_stream_uploads_rejects_non_utf8_filename(tmp_path: Path) -> None:
    body, content_type = _multipart([(b"\xff\xfe.pdf", b"%PDF-1.4\n", b"application/pdf")])
    result = asyncio.run(_stream(body, content_type, tmp_path))
    assert result["staged"] == []
    assert result["rejected"][0]["reason"] == "nombre no UTF-8"


def test_stream_uploads_rejects_oversize_file_but_keeps_others(tmp_path: Path) -> None:
    body, content_type = _multipart(
        [
            (b"grande.pdf", b"%PDF-1.4\n" + b"x" * 4096, b"application/pdf"),
            (b"pequeno.pdf", b"%PDF-1.4\n", b"application/pdf"),
        ]
    )
    result = asyncio.run(_stream(body, content_type, tmp_path, max_file_bytes=1024))
    assert [item["file_id"] for item in result["staged"]] == ["pequeno.pdf"]
    assert result["rejected"][0]["rel_path"] == "grande.pdf"


@pytest.mark.parametrize(
    "filename",
    ["../escape.pdf", "/etc/passwd", "C:\\Windows\\x.pdf", "a/../../b.pdf", "a//b.pdf", ""],
)
def test_safe_rel_path_rejects_traversal(filename: str) -> None:
    with pytest.raises(ValueError):
        safe_rel_path(filename)


@pytest.mark.parametrize("name", ["CON.pdf", "nul", "a:b.pdf", "trailing.", "trailing ", "x/y.pdf"])
def test_safe_file_id_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(ValueError):
        safe_file_id(name)


def test_safe_rel_path_preserves_basename_and_normalizes_separators() -> None:
    assert safe_rel_path("sub\\dir\\Factura.PDF") == "sub/dir/Factura.PDF"
    assert PurePosixPath(safe_rel_path("sub\\dir\\Factura.PDF")).name == "Factura.PDF"
