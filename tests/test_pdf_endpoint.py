"""Endpoint /facturas/{invoice_id}/pdf — el PDF original se ve en la UI."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from albertitos.ui.app import create_app
from albertitos.ui.demo import demo_records


def test_pdf_serve_inline(monkeypatch, tmp_path: Path):
    """Con ALBERTITOS_CARPETA apuntando a una carpeta con el PDF, responde 200
    inline con el contenido exacto del fichero."""
    carpeta = tmp_path / "facturas" / "sub"
    carpeta.mkdir(parents=True)
    (carpeta / "2026-05-28_P005.pdf").write_bytes(b"%PDF-1.4 prueba\n")
    monkeypatch.setenv("ALBERTITOS_CARPETA", str(tmp_path))
    with TestClient(create_app(records=demo_records())) as c:
        r = c.get("/facturas/INV-0001/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert "inline" in r.headers["content-disposition"]
    assert r.content == b"%PDF-1.4 prueba\n"


def test_pdf_404_si_no_esta(monkeypatch, tmp_path: Path):
    """PDF ausente ⇒ 404 limpio con pista de configuración, nunca 500."""
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    monkeypatch.setenv("ALBERTITOS_CARPETA", str(vacia))
    with TestClient(create_app(records=demo_records())) as c:
        r = c.get("/facturas/INV-0001/pdf")
    assert r.status_code == 404
    assert "ALBERTITOS_CARPETA" in r.json()["detail"]


def test_pdf_404_factura_sin_decision(monkeypatch, tmp_path: Path):
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    monkeypatch.setenv("ALBERTITOS_CARPETA", str(vacia))
    with TestClient(create_app(records=demo_records())) as c:
        r = c.get("/facturas/no-existe/pdf")
    assert r.status_code == 404
