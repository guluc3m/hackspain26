"""Device-local runtime configuration, stored only in PouchDB _local documents."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from filemaid.store.pouch import PouchStore, couchdb_url


def endpoint(value: str, name: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"{name}: se requiere una URL HTTP(S)")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(f"{name}: no incluya credenciales, query ni fragmentos")
    try:
        _ = parts.port
    except ValueError as exc:
        raise ValueError(f"{name}: puerto inválido") from exc
    return value


class RuntimeSettings:
    def __init__(self, cfg) -> None:
        self.store = PouchStore(cfg.root)

    def get(self) -> dict:
        saved = self.store.local_get("runtime-settings") or {}
        return {
            "mode": saved.get("mode", "standalone"),
            "sync_url": saved.get("sync_url", ""),
            "vlm_url": saved.get("vlm_url", ""),
            "vlm_model": saved.get("vlm_model", ""),
        }

    def validate(self, values: dict) -> dict:
        mode = values.get("mode")
        if mode not in {"standalone", "server"}:
            raise ValueError("Seleccione standalone o server")
        sync_url = values.get("sync_url", "").strip()
        if sync_url:
            sync_url = couchdb_url(sync_url)
        vlm_url = endpoint(values.get("vlm_url", ""), "Endpoint VLM")
        if mode == "server" and not sync_url:
            raise ValueError("El modo servidor requiere la URL de una base CouchDB")
        return {
            "mode": mode,
            "sync_url": sync_url,
            "vlm_url": vlm_url,
            "vlm_model": values.get("vlm_model", "").strip(),
        }

    def save(self, values: dict) -> dict:
        settings = self.validate(values)
        self.store.local_put("runtime-settings", settings)
        return settings

    def sync(self, settings: dict | None = None) -> dict:
        settings = settings or self.get()
        if settings["mode"] != "server":
            raise ValueError("La sincronización requiere modo servidor")
        return self.store.sync(settings["sync_url"], os.environ.get("FILEMAID_SYNC_TOKEN", ""))
