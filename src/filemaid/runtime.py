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
    # Claves opcionales de los últimos peldaños de la escalera (Firecrawl, VLM
    # cloud, TypeSafe System One). A diferencia de los endpoints remotos sí son
    # significativas en ambos modos: standalone es justo donde se quiere un
    # respaldo cloud opcional. Nunca entran en versiones, evidencias ni trazas.
    "firecrawl_api_key": "",
    "cloud_vlm_api_key": "",
    "typesafe_api_key": "",
}

# Claves de los últimos peldaños: se guardan aquí, nunca se replican (_local/*).
RUNG_KEYS = ("firecrawl_api_key", "cloud_vlm_api_key", "typesafe_api_key")

_MASK_PREFIX = "****"
_MASK_PREFIX_UNICODE = "••••"


def mask_secret(value: str) -> str:
    """Máscara ASCII segura para JSON: solo los 4 últimos caracteres, nunca la clave."""
    return f"{_MASK_PREFIX}{value[-4:]}" if value else ""


def is_masked_secret(value: str) -> bool:
    """Máscara devuelta por la lectura de la API (ASCII o con puntos suspensivos)."""
    value = value.strip()
    return value.startswith(_MASK_PREFIX) or value.startswith(_MASK_PREFIX_UNICODE)


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
            **{key: str(saved.get(key, "") or "") for key in RUNG_KEYS},
            "configured": True,
        }
        return self._coerce(values)

    def masked(self) -> dict:
        """Lectura para la API: las claves de los últimos peldaños nunca salen en claro.

        Devuelve el mismo documento que ``get()`` con cada clave sustituida por su
        máscara (``""`` si no hay nada guardado) más el booleano ``<key>_set`` que
        permite a la UI decir "hay clave" sin conocer el valor.
        """
        values = self.get()
        for key in RUNG_KEYS:
            secret = str(values.get(key) or "")
            values[key] = mask_secret(secret)
            values[f"{key}_set"] = bool(secret)
        return values

    def resolve_rung_keys(self, values: dict) -> dict:
        """Semántica de PUT /api/config para las claves de los últimos peldaños.

        Campo ausente o ``""`` y la máscara que devuelve ``masked()`` conservan la
        clave guardada; cualquier otro valor no vacío la reemplaza;
        ``clear_keys=True`` borra las tres de una vez.
        """
        stored = self.get()
        merged = {key: value for key, value in values.items() if key != "clear_keys"}
        clear = bool(values.get("clear_keys"))
        for key in RUNG_KEYS:
            raw = str(merged.get(key) or "").strip()
            if clear:
                merged[key] = ""
            elif raw and not is_masked_secret(raw):
                merged[key] = raw
            else:
                merged[key] = stored.get(key, "")
        return merged

    @staticmethod
    def _coerce(values: dict) -> dict:
        """Standalone never keeps remote endpoints, model or server key.

        The optional last-rung API keys are the exception: they mean the same in
        both modes, so coercion always preserves them.
        """
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
        # Optional in both modes: an absent key means "rung skipped", never an error.
        rung_keys = {key: str(values.get(key, "") or "").strip() for key in RUNG_KEYS}
        if mode == "standalone":
            return {
                "mode": "standalone",
                "sync_url": "",
                "vlm_url": "",
                "vlm_model": "",
                "server_api_key": "",
                "local_vlm_fallback": False,
                **rung_keys,
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
            **rung_keys,
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
