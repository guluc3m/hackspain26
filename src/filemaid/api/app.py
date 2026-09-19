"""API backend (FastAPI). Comparte types.py, store y motor de reglas con el pipeline.

No es solo lectura: la UI de revisión escribe overrides con procedencia y
dispara reprocesado; las decisiones se recalculan de forma determinista.
"""

from __future__ import annotations

import json
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


def _iterations(ledger_path: Path) -> dict[str, int]:
    """Pases de pipeline por factura: eventos 'decision' del ledger append-only.

    El decisions table colapsa por (invoice_id, run_id); el ledger es la
    única fuente append-only del número real de pasadas.
    """
    counts: dict[str, int] = {}
    for e in Ledger(ledger_path).read():
        if e.get("type") == "decision" and e.get("invoice_id"):
            counts[e["invoice_id"]] = counts.get(e["invoice_id"], 0) + 1
    return counts


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
            """SELECT i.id, i.file_id, i.status, i.source_path,
                      d.result, d.timestamp AS decided_at,
                      (SELECT MIN(m) FROM (
                         SELECT MAX(confidence) AS m FROM field_values
                         WHERE invoice_id = i.id GROUP BY field_type
                       )) AS confidence
               FROM invoices i
               LEFT JOIN decisions d
                 ON d.invoice_id = i.id
                AND d.rowid = (SELECT MAX(d2.rowid) FROM decisions d2 WHERE d2.invoice_id = i.id)
               ORDER BY i.file_id"""
        ).fetchall()
        iteraciones = _iterations(cfg.ledger_path)
        out: list[dict] = []
        for r in rows:
            item = dict(r)
            src = item.pop("source_path") or ""
            item["source_path"] = src or None
            item["folder"] = str(Path(src).parent) if src else None
            item["iterations"] = iteraciones.get(item["id"], 0)
            out.append(item)
        return out

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

    @app.get("/api/logs")
    def logs(q: str = "", event_type: str = "", limit: int = 200, offset: int = 0) -> dict:
        """Log finder: lee el ledger append-only (orden de escritura).

        seq = posición en el fichero (orden estable aunque un evento antiguo
        no tenga ts). Filtros: event_type exacto y q como búsqueda libre sobre
        el evento serializado. Los más recientes primero.
        """
        events = Ledger(cfg.ledger_path).read()
        for i, e in enumerate(events):
            e["seq"] = i + 1
        types = sorted({str(e.get("type", "")) for e in events})
        if event_type:
            events = [e for e in events if e.get("type") == event_type]
        if q:
            needle = q.lower()
            events = [
                e for e in events
                if needle in json.dumps(e, ensure_ascii=False, default=repr).lower()
            ]
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)
        total = len(events)
        items = list(reversed(events))[offset:offset + limit]
        return {"total": total, "types": types, "items": items}

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

    # UI construida (frontend/dist), si existe: `albertitos serve` sirve todo.
    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")

    def _find_pdf(file_id: str) -> Path | None:
        # 1) la ruta registrada en el store (trazabilidad de origen)
        store = Store(cfg.store_path)
        row = store.conn.execute(
            "SELECT source_path FROM invoices WHERE file_id = ? ORDER BY last_seen DESC LIMIT 1",
            (file_id,),
        ).fetchone()
        if row and row["source_path"] and Path(row["source_path"]).exists():
            return Path(row["source_path"])
        # 2) lotes conocidos bajo la raíz de datos
        for lote in (cfg.root / "lotes").glob("*"):
            if lote.is_dir() and (lote / file_id).exists():
                return lote / file_id
        return None

    return app


app = create_app()
