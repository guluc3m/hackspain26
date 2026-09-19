"""Backend MongoDB para la parte DINÁMICA del store de facturas.

Decisión de alcance (KISS, AGENTS.md §2):
- Mongo SOLO donde el esquema es el problema: el estado actual de facturas
  (colección `facturas`, documento flexible: campos fijos + subdocumento
  `extra` libre — campos nuevos por país/administración sin migración) y las
  variables dinámicas filtrables (colección `attrs` ≡ `invoice_attrs`).
- SQLite se queda con lo relacional: evidence, decision_runs (histórico
  append-only con clave compuesta), stage_cache y resolutions. Su acceso es
  por clave, no flexible; migrarlo no aporta valor y dobla superficies de
  fallo.
- `MONGO_URI` por entorno, JAMÁS credenciales en el repo. Sin Mongo (no
  configurado, pymongo ausente o servidor caído) la app sigue con SQLite y
  /salud lo refleja (el Store escribe `store-backend.json` en su raíz).

El motor de reglas sigue puro: Mongo es SOLO persistencia.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

DEFAULT_DB = "albertitos"
DEFAULT_TIMEOUT_MS = 2000


@dataclass
class MongoStatus:
    """Estado de la conexión Mongo (para /salud). Nunca lanza."""

    state: str  # "activo" | "down" | "no-configurado" | "sin-pymongo"
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"state": self.state, "detail": self.detail}


def connect_mongo(
    uri: str | None = None,
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    db_name: str = DEFAULT_DB,
) -> tuple[MongoInvoiceBackend | None, MongoStatus]:
    """Conecta a Mongo (URI por argumento o env `MONGO_URI`); NUNCA lanza.

    Devuelve `(backend, estado)`. `backend is None` ⇒ la app sigue con SQLite
    (degradación explícita, /salud la refleja vía `store-backend.json`).
    """
    uri = (uri if uri is not None else os.environ.get("MONGO_URI", "")).strip()
    if not uri:
        return None, MongoStatus(
            "no-configurado", "MONGO_URI sin definir: facturas en SQLite"
        )
    try:
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError
    except ImportError:
        return None, MongoStatus(
            "sin-pymongo", "pymongo no instalado: facturas en SQLite"
        )
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        client.admin.command("ping")
    except PyMongoError as exc:
        return None, MongoStatus("down", f"Mongo no responde: {exc}")
    return MongoInvoiceBackend(client, db_name=db_name), MongoStatus(
        "activo", f"Mongo OK (db `{db_name}`)"
    )


class MongoInvoiceBackend:
    """`invoices` + `invoice_attrs` de SQLite como documento flexible.

    Documento de `facturas`: mismos campos fijos que la tabla SQLite
    (file_id, invoice_id, sha256, result, rule_codes, numero_factura,
    pedido, nif, iban, config_version, engine_version, updated_at) más
    `extra` como SUBDOCUMENTO libre — aparecer un campo nuevo (p. ej.
    `ruc` para Perú) no exige migración de esquema, solo un índice cuando
    se quiera filtrar por él.
    """

    def __init__(self, client: Any, db_name: str = DEFAULT_DB) -> None:
        self._client = client
        self._db = client[db_name]
        self.facturas = self._db["facturas"]
        self.attrs = self._db["attrs"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Índices fijos: identidad única de factura + filtrado de variables.

        Para filtrar por un campo de `extra` concreto (p. ej. `extra.moneda`
        cuando aparece el ejemplo Perú) se crea el índice a demanda — eso es
        exactamente el propósito del esquema flexible: el ÍNDICE es una
        decisión de consulta, no de esquema."""
        self.facturas.create_index("file_id", unique=True)
        self.attrs.create_index([("key", 1), ("value", 1)])
        self.attrs.create_index("file_id")

    # ------------------------------------------------------------- facturas

    def put_factura(self, doc: dict) -> None:
        self.facturas.replace_one({"file_id": doc["file_id"]}, doc, upsert=True)

    def get_factura(self, file_id: str) -> dict | None:
        return self.facturas.find_one({"file_id": file_id})

    def all_facturas(self) -> list[dict]:
        return list(self.facturas.find({}).sort("file_id", 1))

    def resultados_por_file(self, file_ids: list[str]) -> dict[str, str]:
        """file_id → result en una query por chunk (`$in`), como SQLite."""
        out: dict[str, str] = {}
        for i in range(0, len(file_ids), 400):
            chunk = list(file_ids[i : i + 400])
            for doc in self.facturas.find(
                {"file_id": {"$in": chunk}}, {"file_id": 1, "result": 1}
            ):
                out[doc["file_id"]] = doc["result"]
        return out

    # ---------------------------------------------------------------- attrs

    def register_attrs(self, file_id: str, extra: dict) -> list[str]:
        """Registra variables dinámicas (clave-valor por factura); devuelve
        los nombres de variable NUEVOS (para el evento `new_field` del ledger).
        """
        conocidas = set(self.attrs.distinct("key"))
        nuevas = [k for k in sorted(extra) if k not in conocidas]
        from pymongo import ReplaceOne

        ops = [
            ReplaceOne(
                {"file_id": file_id, "key": key},
                {"file_id": file_id, "key": key, "value": str(val)},
                upsert=True,
            )
            for key, val in sorted(extra.items())
        ]
        if ops:
            self.attrs.bulk_write(ops)
        return nuevas

    def attrs_for(self, file_id: str) -> dict[str, str]:
        return {
            d["key"]: d["value"]
            for d in self.attrs.find({"file_id": file_id}).sort("key", 1)
        }

    def files_with_attr(self, key: str, value: str | None = None) -> list[str]:
        query: dict = {"key": key}
        if value is not None:
            query["value"] = str(value)
        return sorted(
            d["file_id"]
            for d in self.attrs.find(query, {"file_id": 1}).sort("file_id", 1)
        )

    def known_attr_keys(self) -> list[str]:
        return sorted(self.attrs.distinct("key"))

    # ---------------------------------------------------------------- salud

    def ping(self) -> bool:
        self._client.admin.command("ping")
        return True

    def close(self) -> None:
        self._client.close()


# --------------------------------------------------------------- migración


def migrar_sqlite_a_mongo(backend: MongoInvoiceBackend, sqlite_path: Any) -> int:
    """Migra el estado actual de facturas de SQLite (`invoices` +
    `invoice_attrs`) a Mongo. Idempotente: upsert por `file_id`, re-correr
    no duplica. Lo relacional (evidence, decision_runs, stage_cache,
    resolutions) SE QUEDA en SQLite por diseño. Devuelve nº de facturas.
    """
    import json
    import sqlite3

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(invoices)")]
        n = 0
        for row in conn.execute("SELECT * FROM invoices ORDER BY file_id"):
            doc = {c: row[c] for c in cols if c not in ("extra",)}
            try:
                doc["extra"] = dict(json.loads(row["extra"])) if row["extra"] else {}
            except (TypeError, ValueError):
                doc["extra"] = {}
            backend.put_factura(doc)
            attrs = {
                r["key"]: r["value"]
                for r in conn.execute(
                    "SELECT key, value FROM invoice_attrs WHERE file_id=?",
                    (doc["file_id"],),
                )
            }
            backend.register_attrs(doc["file_id"], attrs)
            n += 1
        return n
    finally:
        conn.close()