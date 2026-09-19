"""SQLite: fuente de verdad relacional. WAL, idempotente, reanudable.

Clave de cache/idempotencia: (sha256, stage, engine_version, config_version).
Reprocesar un item completado debe ser un no-op que reusa la evidencia.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from albertitos.types import classify_unknown_reason

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
  id TEXT PRIMARY KEY,               -- UUID interno estable
  file_id TEXT NOT NULL,             -- nombre exacto del PDF
  sha256 TEXT NOT NULL,
  first_seen REAL NOT NULL,
  last_seen REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pendiente'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_sha ON invoices(sha256);

CREATE TABLE IF NOT EXISTS features (
  invoice_id TEXT NOT NULL,
  stage TEXT NOT NULL,               -- extraccion: pypdf|pypdfium2|zxing|tesseract|vlm|cloud_vlm
  page INTEGER,
  extractor_version TEXT NOT NULL,
  config_version TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  latency_ms INTEGER NOT NULL,
  confidence REAL,
  outcome TEXT NOT NULL,             -- ok | skipped:<reason> | fail
  detail TEXT NOT NULL,              -- JSON
  timestamp REAL NOT NULL,
  PRIMARY KEY (invoice_id, stage, page, extractor_version, config_version, outcome)
);

CREATE TABLE IF NOT EXISTS fields (
  invoice_id TEXT NOT NULL,
  type TEXT NOT NULL,                -- nif|iban|total|iva_amount|fecha|pedido|...
  timestamp REAL NOT NULL,
  PRIMARY KEY (invoice_id, type)
);

CREATE TABLE IF NOT EXISTS field_values (
  invoice_id TEXT NOT NULL,
  field_type TEXT NOT NULL,
  extractor TEXT NOT NULL,
  value TEXT NOT NULL,               -- JSON; nunca se colapsan los candidatos
  confidence REAL NOT NULL,
  PRIMARY KEY (invoice_id, field_type, extractor, value)
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  started REAL NOT NULL,
  finished REAL,
  config_version TEXT NOT NULL,
  master_sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_evaluations (
  invoice_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  code TEXT NOT NULL,
  verdict TEXT NOT NULL,             -- PASS|FAIL|UNKNOWN
  reason TEXT NOT NULL,
  reason_code TEXT NOT NULL DEFAULT '',  -- si UNKNOWN: causa estable (types.UNKNOWN_*)
  consumed TEXT NOT NULL,            -- JSON
  timestamp REAL NOT NULL,
  PRIMARY KEY (invoice_id, run_id, code)
);

CREATE TABLE IF NOT EXISTS decisions (
  invoice_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  result TEXT NOT NULL,              -- PAGAR|NO_PAGAR|ESCALAR
  config_snapshot TEXT NOT NULL,     -- JSON
  timestamp REAL NOT NULL,
  PRIMARY KEY (invoice_id, run_id)
);

CREATE TABLE IF NOT EXISTS config_snapshots (
  version TEXT PRIMARY KEY,
  snapshot TEXT NOT NULL             -- JSON
);

CREATE TABLE IF NOT EXISTS overrides (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id TEXT NOT NULL,
  field_type TEXT NOT NULL,
  before TEXT NOT NULL,              -- JSON
  after TEXT NOT NULL,               -- JSON
  who TEXT NOT NULL,
  rung TEXT NOT NULL,
  reason TEXT NOT NULL,
  timestamp REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Migraciones idempotentes de stores existentes (nunca bloquea el lote)."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(rule_evaluations)")}
        if "reason_code" not in cols:
            self.conn.execute(
                "ALTER TABLE rule_evaluations ADD COLUMN reason_code TEXT NOT NULL DEFAULT ''"
            )
        # backfill de filas legacy: clasifica el motivo textual con el clasificador estable
        rows = self.conn.execute(
            "SELECT rowid, reason FROM rule_evaluations WHERE verdict = 'UNKNOWN' AND reason_code = ''"
        ).fetchall()
        for r in rows:
            self.conn.execute(
                "UPDATE rule_evaluations SET reason_code = ? WHERE rowid = ?",
                (classify_unknown_reason(r["reason"]), r["rowid"]),
            )

    def close(self) -> None:
        self.conn.close()

    # -- invoices ----------------------------------------------------------
    def upsert_invoice(self, invoice_id: str, file_id: str, sha256: str) -> None:
        self.conn.execute(
            """INSERT INTO invoices (id, file_id, sha256, first_seen, last_seen, status)
               VALUES (?, ?, ?, unixepoch('now'), unixepoch('now'), 'pendiente')
               ON CONFLICT(sha256) DO UPDATE SET last_seen = unixepoch('now')""",
            (invoice_id, file_id, sha256),
        )
        self.conn.commit()

    def invoice_by_sha(self, sha256: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM invoices WHERE sha256 = ?", (sha256,)).fetchone()

    # -- evidencia ---------------------------------------------------------
    def add_feature(self, invoice_id: str, **kw: Any) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO features
               (invoice_id, stage, page, extractor_version, config_version, sha256,
                latency_ms, confidence, outcome, detail, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch('now'))""",
            (
                invoice_id,
                kw["stage"],
                kw.get("page"),
                kw["extractor_version"],
                kw["config_version"],
                kw["sha256"],
                kw["latency_ms"],
                kw.get("confidence"),
                kw["outcome"],
                json.dumps(kw.get("detail", {}), sort_keys=True),
            ),
        )
        self.conn.commit()

    def feature_cached(
        self, stage: str, sha256: str, extractor_version: str, config_version: str
    ) -> bool:
        return (
            self.conn.execute(
                """SELECT 1 FROM features
                   WHERE stage = ? AND sha256 = ? AND extractor_version = ? AND config_version = ?
                     AND outcome LIKE 'ok%'""",
                (stage, sha256, extractor_version, config_version),
            ).fetchone()
            is not None
        )

    def add_field(self, invoice_id: str, field_type: str, candidates: list[dict[str, Any]]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO fields (invoice_id, type, timestamp) VALUES (?, ?, unixepoch('now'))",
            (invoice_id, field_type),
        )
        for c in candidates:
            self.conn.execute(
                """INSERT OR IGNORE INTO field_values (invoice_id, field_type, extractor, value, confidence)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    invoice_id,
                    field_type,
                    c["extractor"],
                    json.dumps(c["value"], sort_keys=True),
                    c["confidence"],
                ),
            )
        self.conn.commit()

    def fields_for(self, invoice_id: str) -> dict[str, list[dict[str, Any]]]:
        rows = self.conn.execute(
            "SELECT field_type, extractor, value, confidence FROM field_values WHERE invoice_id = ?"
            " ORDER BY confidence DESC",
            (invoice_id,),
        ).fetchall()
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(r["field_type"], []).append(
                {
                    "extractor": r["extractor"],
                    "value": json.loads(r["value"]),
                    "confidence": r["confidence"],
                }
            )
        return out

    # -- lectura para informes (decisiones + breadcrumbs) -------------------
    def decision_rows_for_run(self, run_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT d.invoice_id, d.run_id, d.result, d.config_snapshot, d.timestamp,
                      i.file_id, i.sha256
               FROM decisions d JOIN invoices i ON i.id = d.invoice_id
               WHERE d.run_id = ? ORDER BY i.file_id""",
            (run_id,),
        ).fetchall()

    def rule_evaluations_for(self, invoice_id: str, run_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT code, verdict, reason, reason_code, consumed FROM rule_evaluations
               WHERE invoice_id = ? AND run_id = ? ORDER BY code""",
            (invoice_id, run_id),
        ).fetchall()

    def features_for(self, invoice_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT stage, page, extractor_version, latency_ms, confidence, outcome, detail
               FROM features WHERE invoice_id = ? ORDER BY page, stage""",
            (invoice_id,),
        ).fetchall()

    def run_row(self, run_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()

    # -- decisión ----------------------------------------------------------
    def start_run(self, run_id: str, config_version: str, master_sha256: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO runs (id, started, config_version, master_sha256)"
            " VALUES (?, unixepoch('now'), ?, ?)",
            (run_id, config_version, master_sha256),
        )
        self.conn.commit()

    def finish_run(self, run_id: str) -> None:
        self.conn.execute("UPDATE runs SET finished = unixepoch('now') WHERE id = ?", (run_id,))
        self.conn.commit()

    def save_config_snapshot(self, version: str, snapshot: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO config_snapshots (version, snapshot) VALUES (?, ?)",
            (version, json.dumps(snapshot, sort_keys=True)),
        )
        self.conn.commit()

    def save_decision(
        self, invoice_id: str, run_id: str, result: str, config_snapshot: dict[str, Any]
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO decisions (invoice_id, run_id, result, config_snapshot, timestamp)
               VALUES (?, ?, ?, ?, unixepoch('now'))""",
            (invoice_id, run_id, result, json.dumps(config_snapshot, sort_keys=True)),
        )
        self.conn.execute("UPDATE invoices SET status = ? WHERE id = ?", (result, invoice_id))
        self.conn.commit()

    def add_rule_evaluations(
        self, invoice_id: str, run_id: str, evaluations: list[dict[str, Any]]
    ) -> None:
        for e in evaluations:
            self.conn.execute(
                """INSERT OR REPLACE INTO rule_evaluations
                   (invoice_id, run_id, code, verdict, reason, reason_code, consumed, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, unixepoch('now'))""",
                (
                    invoice_id,
                    run_id,
                    e["code"],
                    e["verdict"],
                    e["reason"],
                    e.get("reason_code", ""),
                    json.dumps(e.get("consumed", {}), sort_keys=True),
                ),
            )
        self.conn.commit()

    # -- overrides ---------------------------------------------------------
    def add_override(self, o: dict[str, Any]) -> int:
        cur = self.conn.execute(
            """INSERT INTO overrides (invoice_id, field_type, before, after, who, rung, reason, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, unixepoch('now'))""",
            (
                o["invoice_id"],
                o["field_type"],
                json.dumps(o["before"], sort_keys=True),
                json.dumps(o["after"], sort_keys=True),
                o["who"],
                o["rung"],
                o["reason"],
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def overrides_for(self, invoice_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM overrides WHERE invoice_id = ? ORDER BY timestamp", (invoice_id,)
        ).fetchall()


def open_store(path: Path) -> Store:
    return Store(path)
