"""API backend (FastAPI). Comparte types.py, store y motor de reglas con el pipeline.

No es solo lectura: la UI de revisión escribe overrides con procedencia y
dispara reprocesado; las decisiones se recalculan de forma determinista.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from filemaid.config import AppConfig
from filemaid.pipeline import Pipeline
from filemaid.rules.config import RuleConfig
from filemaid.store.db import Store
from filemaid.store.ledger import Ledger


class OverrideIn(BaseModel):
    field_type: str
    before: object
    after: object
    who: str
    rung: str = "review-ui"
    reason: str = ""


def create_app(cfg: AppConfig | None = None) -> FastAPI:
    cfg = cfg or AppConfig.load()
    app = FastAPI(title="filemaid", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/api/facturas")
    def facturas() -> list[dict]:
        store = Store(cfg.store_path)
        rows = store.conn.execute(
            """SELECT i.id, i.file_id, i.status, d.result, d.timestamp
               FROM invoices i LEFT JOIN decisions d ON d.invoice_id = i.id
               ORDER BY i.file_id"""
        ).fetchall()
        return [dict(r) for r in rows]

    @app.get("/api/facturas/{invoice_id}")
    def factura(invoice_id: str) -> dict:
        store = Store(cfg.store_path)
        inv = store.conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if inv is None:
            raise HTTPException(404, "factura no encontrada")
        dec = store.conn.execute(
            "SELECT * FROM decisions WHERE invoice_id = ? ORDER BY timestamp DESC LIMIT 1", (invoice_id,)
        ).fetchone()
        rules = store.conn.execute(
            """SELECT code, verdict, reason, consumed FROM rule_evaluations
               WHERE invoice_id = ?
                 AND run_id = (SELECT run_id FROM rule_evaluations
                               WHERE invoice_id = ? ORDER BY timestamp DESC LIMIT 1)
               ORDER BY code""",
            (invoice_id, invoice_id),
        ).fetchall()
        return {
            "invoice": dict(inv),
            "fields": store.fields_for(invoice_id),
            "decision": dict(dec) if dec else None,
            "rule_evaluations": [dict(r) for r in rules],
            "overrides": [dict(o) for o in store.overrides_for(invoice_id)],
        }

    @app.post("/api/revision/{invoice_id}/override")
    def override(invoice_id: str, body: OverrideIn) -> dict:
        """Override humano con procedencia; afecta solo a la extracción.

        El store guarda antes/después/quién/cuándo/desde qué escalón; la
        decisión se recalcula después con el mismo motor determinista.
        """
        store = Store(cfg.store_path)
        if store.conn.execute("SELECT 1 FROM invoices WHERE id = ?", (invoice_id,)).fetchone() is None:
            raise HTTPException(404, "factura no encontrada")
        store.add_override(body.model_dump() | {"invoice_id": invoice_id})
        Ledger(cfg.ledger_path).append(
            "override", {"invoice_id": invoice_id, **body.model_dump()}
        )
        return {"ok": True, "nota": "reprocesar con: filemaid reprocess --invoice-id ... --pdf ..."}

    @app.get("/api/reglas")
    def reglas() -> dict:
        rc = RuleConfig.load(cfg.rules_config_path)
        return {
            "config_version": rc.version,
            "enabled": rc.enabled_codes,
            "thresholds": rc.thresholds,
            "outcomes": rc.outcomes,
        }

    @app.get("/api/salud")
    def salud() -> dict:
        import shutil

        import httpx

        llama = "down"
        try:
            r = httpx.get(f"{cfg.llama_base_url}/health", timeout=1.0)
            llama = "ok" if r.status_code == 200 else "degradado"
        except httpx.HTTPError:
            pass
        return {
            "tesseract": "ok" if shutil.which("tesseract") else "ausente",
            "llama-server": llama,
            "cloud_vlm": "ok" if cfg.cloud_api_key else "sin-clave",
            "store": "ok" if cfg.store_path.exists() else "vacío",
        }

    @app.post("/api/reprocesar/{file_id}")
    def reprocesar(file_id: str) -> dict:
        pdf = _find_pdf(file_id)
        if pdf is None:
            raise HTTPException(404, "PDF no encontrado en los lotes conocidos")
        pipeline = Pipeline(cfg)
        d = pipeline.process_pdf(pdf)
        return {"file_id": d.file_id, "result": d.result.value}

    if cfg.pages_dir.exists():
        app.mount(
            "/paginas",
            StaticFiles(directory=str(cfg.pages_dir)),
            name="paginas",
        )

    def _find_pdf(file_id: str) -> Path | None:
        for lote in (cfg.root / "lotes").glob("*"):
            if lote.is_dir() and (lote / file_id).exists():
                return lote / file_id
        return None

    return app


app = create_app()
