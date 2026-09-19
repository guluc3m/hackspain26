"""Local application API: PouchDB evidence, runtime selection and synchronization."""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from filemaid.config import AppConfig
from filemaid.pipeline import Pipeline
from filemaid.provision import get_provisioner
from filemaid.rules.config import RuleConfig
from filemaid.runtime import RuntimeSettings
from filemaid.store import queries
from filemaid.store.pouch import PouchStore


class OverrideIn(BaseModel):
    field_type: str
    before: object
    after: object
    who: str
    rung: str = "review-ui"
    reason: str = ""


class ConnectionIn(BaseModel):
    mode: str
    sync_url: str = Field(default="", max_length=2048)
    vlm_url: str = Field(default="", max_length=2048)
    vlm_model: str = Field(default="", max_length=256)
    local_vlm_fallback: bool = False


def _vlm_status(cfg: AppConfig, settings: RuntimeSettings) -> dict:
    current = settings.get()
    local_required = current["mode"] == "standalone" or current["local_vlm_fallback"]
    local_fallback = current["local_vlm_fallback"]
    probe = get_provisioner(cfg).status()
    if not local_required:
        state = "remote-only" if current["mode"] == "server" else "idle"
    else:
        state = probe["state"]
    return {
        **probe,
        "mode": current["mode"],
        "local_required": local_required,
        "local_fallback": local_fallback,
        "state": state,
    }


def create_app(cfg: AppConfig | None = None) -> FastAPI:
    cfg = cfg or AppConfig.load()
    pouch = PouchStore(cfg.root)
    settings = RuntimeSettings(cfg)
    sync_lock = threading.RLock()
    wake = threading.Event()
    inflight = threading.Event()

    def _current_seq() -> object:
        try:
            return pouch.request(op="info").get("update_seq")
        except Exception:
            return None

    def sync_status() -> dict:
        current = settings.get()
        stored = settings.sync_state()
        if not current["configured"] or current["mode"] != "server":
            return {
                "ok": True,
                "state": "standalone" if current["mode"] == "standalone" else "idle",
                "error": "",
                "pending": False,
                "last_sync": stored["last_sync"],
            }
        seq = _current_seq()
        # Pending is measured against the last SUCCESSFUL destination, so a new
        # (never-synced) target is pending even if the local seq is unchanged.
        same_remote = stored["synced_url"] == current["sync_url"]
        pending = bool(not same_remote or (seq is not None and stored["last_seq"] != seq))
        failed_current = stored["failed_url"] == current["sync_url"]
        if inflight.is_set():
            state = "syncing"
        elif failed_current:
            state = "error"
        elif pending:
            state = "pending"
        else:
            state = stored["state"]
        return {
            "ok": not failed_current,
            "state": state,
            "error": stored["error"] if failed_current else "",
            "pending": pending,
            "last_sync": stored["last_sync"] if same_remote else None,
        }

    def synchronize(values: dict | None = None) -> dict:
        with sync_lock:
            values = values or settings.get()
            if values["mode"] != "server":
                raise ValueError("Seleccione modo servidor para sincronizar")
            previous = settings.sync_state()
            inflight.set()
            try:
                result = settings.sync(values)
            except Exception as exc:
                # Keep the last successful destination checkpoint; record the
                # failed target separately so status shows error + pending.
                settings.set_sync_state(
                    state="error",
                    ok=False,
                    error=str(exc),
                    last_sync=previous["last_sync"],
                    last_seq=previous["last_seq"],
                    synced_url=previous["synced_url"],
                    failed_url=values["sync_url"],
                )
                raise
            finally:
                inflight.clear()
            # The bridge returns the sequence captured inside the locked sync,
            # so a write after this point stays pending, never marked synced.
            settings.set_sync_state(
                state="synced",
                ok=True,
                error="",
                last_sync=time.time(),
                last_seq=result.get("seq"),
                synced_url=values["sync_url"],
                failed_url="",
            )
            return {"ok": True, **result}

    async def sync_loop() -> None:
        while True:
            try:
                current = await asyncio.to_thread(settings.get)
                if current["configured"] and current["mode"] == "server":
                    await asyncio.to_thread(synchronize)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.to_thread(wake.wait, 30)
            wake.clear()

    @asynccontextmanager
    async def lifespan(_app):
        current = await asyncio.to_thread(settings.get)
        if current["configured"] and (
            current["mode"] == "standalone" or current["local_vlm_fallback"]
        ):
            get_provisioner(cfg).ensure()
        task = asyncio.create_task(sync_loop())
        try:
            yield
        finally:
            wake.set()  # release the loop's wait so shutdown is prompt
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="filemaid", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/api/config")
    def connection() -> dict:
        return settings.get()

    @app.put("/api/config")
    def configure(body: ConnectionIn) -> dict:
        try:
            # Durable local save first: a remote outage must never discard the
            # confirmed configuration. Sync/provision run in the background.
            saved = settings.save(body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if saved["mode"] == "server":
            wake.set()
        if saved["mode"] == "standalone" or saved["local_vlm_fallback"]:
            try:
                get_provisioner(cfg).ensure()
            except Exception:
                pass
        return saved

    @app.post("/api/sync")
    def sync_now() -> dict:
        try:
            return synchronize()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"Sincronización fallida: {exc}") from exc

    @app.get("/api/sync/status")
    def sync_status_route() -> dict:
        return sync_status()

    @app.get("/api/vlm/status")
    def vlm_status_route() -> dict:
        return _vlm_status(cfg, settings)

    @app.post("/api/vlm/provision")
    def vlm_provision_route() -> dict:
        current = settings.get()
        if not current["configured"]:
            raise HTTPException(409, "Configure el modo antes de provisionar el VLM local")
        if not (current["mode"] == "standalone" or current["local_vlm_fallback"]):
            raise HTTPException(409, "El modo actual no requiere VLM local")
        get_provisioner(cfg).ensure()
        return _vlm_status(cfg, settings)

    @app.get("/api/facturas")
    def facturas() -> list[dict]:
        return queries.invoice_rows(pouch)

    @app.get("/api/facturas/{file_key}")
    def factura(file_key: str) -> dict:
        detail = queries.invoice_detail(pouch, file_key)
        if detail is None:
            raise HTTPException(404, "factura no encontrada")
        return detail

    @app.post("/api/revision/{file_key}/override")
    def override(file_key: str, body: OverrideIn) -> dict:
        if pouch.get(f"file:{file_key}") is None:
            raise HTTPException(404, "factura no encontrada")
        queries.save_override(pouch, file_key, body.model_dump())
        if settings.get()["mode"] == "server":
            wake.set()
        return {"ok": True}

    @app.get("/api/reglas")
    def reglas() -> dict:
        rc = RuleConfig.load(cfg.rules_config_path)
        return {
            "config_version": rc.version,
            "rule_set_version": rc.version,
            "enabled": rc.enabled_codes,
            "thresholds": rc.thresholds,
            "outcomes": rc.outcomes,
        }

    @app.get("/api/salud")
    def salud() -> dict:
        import shutil

        try:
            pouch.request(op="info")
            storage = "ok"
        except RuntimeError:
            storage = "error"
        current = settings.get()
        return {
            "tesseract": "ok" if shutil.which("tesseract") else "ausente",
            "llama-server": "remoto" if current["mode"] == "server" else "local",
            "cloud_vlm": "ok" if cfg.cloud_api_key else "sin-clave",
            "store": storage,
            "sync": sync_status(),
            "vlm": _vlm_status(cfg, settings),
        }

    @app.post("/api/reprocesar/{file_id}")
    def reprocesar(file_id: str, file_key: str = "") -> dict:
        if not file_id or Path(file_id).name != file_id or file_id in {".", ".."}:
            raise HTTPException(400, "nombre de fichero inválido")
        scans = pouch.for_file(file_id, "scan")
        if file_key:
            scans = [s for s in scans if s["file_key"] == file_key]
        elif len({s["file_key"] for s in scans}) > 1:
            raise HTTPException(409, "basename ambiguo: indique file_key")
        if not scans:
            raise HTTPException(404, "factura no encontrada")
        scans.sort(key=lambda s: (s["timestamp"], s["_id"]), reverse=True)
        artifacts = pouch.for_file(file_id, "artifact")
        original = next(
            (
                a
                for s in scans
                for a in artifacts
                if a["scan_id"] == s["scan_id"] and a["stage"] == "input"
            ),
            None,
        )
        if original is None:
            raise HTTPException(404, "artefacto de entrada no encontrado")
        work = cfg.root / "work"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temp:
            pdf = Path(temp) / file_id
            with pdf.open("wb") as output:
                for chunk in pouch.read_artifact(original["_id"]):
                    output.write(chunk)
            decision = Pipeline(cfg).process_pdf(pdf)
        return {"file_id": decision.file_id, "result": decision.result.value}

    @app.get("/api/logs")
    def logs(
        invoice: str = "", q: str = "", event_type: str = "", limit: int = 200, offset: int = 0
    ) -> dict:
        return queries.logs(pouch, invoice, q, event_type, max(1, min(limit, 500)), max(0, offset))

    @app.get("/api/trazas")
    def trazas(file_id: str) -> list[dict]:
        return [pouch.hydrate(d) for d in pouch.for_file(file_id)]

    @app.get("/api/artefactos/{artifact_id}")
    def artefacto(artifact_id: str):
        doc = pouch.get(artifact_id)
        if doc is None or doc.get("kind") != "artifact":
            raise HTTPException(404, "artefacto no encontrado")
        return StreamingResponse(
            pouch.read_artifact(artifact_id),
            media_type=doc["media_type"],
            headers={"Content-Disposition": "attachment", "X-Content-Type-Options": "nosniff"},
        )

    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")
    return app


app = create_app()
