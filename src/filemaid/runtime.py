"""Device-local runtime configuration, stored only in PouchDB _local documents.

The persisted runtime doc is the source of truth: it survives restarts and is
never replicated (``_local/*`` docs are excluded from CouchDB replication), so
credentials and local endpoints stay on the device. Saving is durable and
independent of remote availability; remote sync is a separate, resumable state.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from filemaid.store.pouch import PouchStore, couchdb_url

SETTINGS_ID = "runtime-settings"
SYNC_STATE_ID = "sync-state"

_DEFAULT = {
    "mode": "standalone",
    "sync_url": "",
    "vlm_url": "",
    "vlm_model": "",
    "server_api_key": "",
    "local_vlm_fallback": False,
}


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
        saved = self.store.local_get(SETTINGS_ID)
        if not isinstance(saved, dict) or saved.get("mode") not in {"standalone", "server"}:
            return {**_DEFAULT, "configured": False}
        # A legacy server doc without a remote VLM URL is not a valid current
        # configuration: report unconfigured so the UI repairs it instead of
        # silently confirming a server with no VLM at all.
        if saved["mode"] == "server" and not (saved.get("sync_url") and saved.get("vlm_url")):
            return {**_DEFAULT, "configured": False}
        values = {
            "mode": saved["mode"],
            "sync_url": saved.get("sync_url", ""),
            "vlm_url": saved.get("vlm_url", ""),
            "vlm_model": saved.get("vlm_model", ""),
            "server_api_key": saved.get("server_api_key", ""),
            "local_vlm_fallback": bool(saved.get("local_vlm_fallback", False)),
            "configured": True,
        }
        return self._coerce(values)

    @staticmethod
    def _coerce(values: dict) -> dict:
        """Standalone never keeps remote endpoints, model or server key."""
        if values["mode"] == "standalone":
            values["sync_url"] = ""
            values["vlm_url"] = ""
            values["vlm_model"] = ""
            values["server_api_key"] = ""
            values["local_vlm_fallback"] = False
        return values

    def validate(self, values: dict) -> dict:
        mode = values.get("mode")
        if mode not in {"standalone", "server"}:
            raise ValueError("Seleccione standalone o server")
        vlm_model = str(values.get("vlm_model", "")).strip()
        if mode == "standalone":
            return {
                "mode": "standalone",
                "sync_url": "",
                "vlm_url": "",
                "vlm_model": "",
                "server_api_key": "",
                "local_vlm_fallback": False,
            }
        sync_url = str(values.get("sync_url", "")).strip()
        if not sync_url:
            raise ValueError("El modo servidor requiere la URL de una base CouchDB")
        sync_url = couchdb_url(sync_url)
        vlm_url = endpoint(values.get("vlm_url", ""), "Endpoint VLM")
        if not vlm_url:
            raise ValueError("El modo servidor requiere la URL del VLM remoto")
        server_api_key = str(values.get("server_api_key", "")).strip()
        if not server_api_key:
            raise ValueError("El modo servidor requiere la clave de API del servidor")
        return {
            "mode": "server",
            "sync_url": sync_url,
            "vlm_url": vlm_url,
            "vlm_model": vlm_model,
            "server_api_key": server_api_key,
            "local_vlm_fallback": bool(values.get("local_vlm_fallback", False)),
        }

    def save(self, values: dict) -> dict:
        """Durable local save. Never contacts the network."""
        settings = self.validate(values)
        self.store.local_put(SETTINGS_ID, settings)
        return {**settings, "configured": True}

    def sync(self, settings: dict | None = None) -> dict:
        settings = settings or self.get()
        if settings["mode"] != "server":
            raise ValueError("La sincronización requiere modo servidor")
        # The stored server key is the token for the native bridge; the env var
        # remains only as an external fallback when no key is stored.
        token = settings.get("server_api_key") or os.environ.get("FILEMAID_SYNC_TOKEN", "")
        return self.store.sync(settings["sync_url"], token)

    # -- remote sync state (device-local, resumable) ----------------------

    def sync_state(self) -> dict:
        saved = self.store.local_get(SYNC_STATE_ID)
        if not isinstance(saved, dict):
            saved = {}
        return {
            "state": saved.get("state", "idle"),
            "ok": bool(saved.get("ok", True)),
            "error": saved.get("error", ""),
            "last_sync": saved.get("last_sync"),
            "last_seq": saved.get("last_seq"),
            "synced_url": saved.get("synced_url", ""),
            "failed_url": saved.get("failed_url", ""),
        }

    def set_sync_state(
        self,
        *,
        state: str,
        ok: bool,
        error: str = "",
        last_sync: float | None = None,
        last_seq: object = None,
        synced_url: str = "",
        failed_url: str = "",
    ) -> None:
        self.store.local_put(
            SYNC_STATE_ID,
            {
                "state": state,
                "ok": ok,
                "error": error,
                "last_sync": last_sync,
                "last_seq": last_seq,
                "synced_url": synced_url,
                "failed_url": failed_url,
            },
        )
