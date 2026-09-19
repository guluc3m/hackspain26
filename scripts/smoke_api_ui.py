"""Smoke E2E: pipeline -> API enriquecida -> logs -> override -> reprocesar -> UI servida.

Se ejecuta contra un directorio raíz desechable; no toca data/ del repo.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from albertitos.api.app import create_app
from albertitos.config import AppConfig
from albertitos.pipeline import Pipeline

scratch = REPO / ".smoke-tmp"
if scratch.exists():
    shutil.rmtree(scratch)

cfg = AppConfig(scratch / "data")
cfg.master_dir = scratch / "master"
cfg.master_dir.mkdir(parents=True)
for name in ("rules.yaml", "proveedores.csv", "pedidos.csv"):
    shutil.copy(REPO / "master" / name, cfg.master_dir / name)
cfg.rules_config_path = cfg.master_dir / "rules.yaml"

# PDF de texto mínimo (misma técnica que scripts/smoke_skeleton.py)
def make_pdf(path: Path, text: str) -> None:
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
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))


lote = scratch / "lote"
lote.mkdir()
make_pdf(lote / "factura_smoke.pdf", "NIF B12345678 IBAN ES9121000418450200051332 TOTAL 121.00")

decisions = Pipeline(cfg).run_lote(lote, scratch / "outcomes.jsonl")
print("pipeline:", [(d.file_id, d.result.value) for d in decisions])

c = TestClient(create_app(cfg))

rows = c.get("/api/facturas").json()
assert len(rows) == 1, rows
r = rows[0]
assert r["folder"] == str(lote), r
assert r["source_path"] == str(lote / "factura_smoke.pdf"), r
assert r["iterations"] == 1, r
print("facturas:", {k: r[k] for k in ("file_id", "status", "result", "folder", "iterations", "confidence")})

logs = c.get("/api/logs").json()
assert logs["total"] >= 2, logs
print("logs:", logs["total"], "eventos, tipos:", logs["types"])
assert logs["items"][0]["seq"] >= 1

inv_id = r["id"]
ov = c.post(
    f"/api/revision/{inv_id}/override",
    json={"field_type": "total", "before": 121.0, "after": 121.0, "who": "smoke", "rung": "review-ui", "reason": "prueba"},
)
assert ov.status_code == 200, ov.text

rep = c.post("/api/reprocesar/factura_smoke.pdf")
assert rep.status_code == 200, rep.text
rows2 = c.get("/api/facturas").json()
assert rows2[0]["iterations"] == 2, rows2
print("reprocesado OK, iteraciones:", rows2[0]["iterations"])

ui = c.get("/")
assert ui.status_code == 200 and "albertitos" in ui.text, ui.status_code
print("UI servida por / (dist mount):", ui.status_code)

shutil.rmtree(scratch)
print("SMOKE OK")
