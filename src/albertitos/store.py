"""Store persistente (SQLite + ledger JSONL append-only) — AGENTS.md §5.

- Estado NUNCA en memoria y NUNCA en /tmp: vive en `.sdd/store.db` y
  `.sdd/ledger/`.
- Idempotencia: clave `(sha256, stage, engine_version, config_version)`.
  Re-procesar un ítem completado es no-op que reutiliza evidencia.
- Cada fase escribe fila de evidencia; histórico y resoluciones escaladas se
  conservan (corpus de retroalimentación, architecture.typ §Retroalimentación).
- Reprocesable desde cualquier punto: un crash pierde como mucho el ítem en
  vuelo (transacción por factura, ledger con fsync).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from albertitos.types import Decision, EvidenceRow

_NAMESPACE_UUID = uuid.UUID("6f1b0d3e-7c4a-4f2e-9a1b-2c3d4e5f6071")


@dataclass
class StoredDecision:
    file_id: str
    invoice_id: str
    sha256: str
    result: str
    rule_codes: list[str]
    numero_factura: str | None
    pedido: str
    config_version: str
    engine_version: str


def invoice_uuid(sha256: str) -> str:
    """UUID interno estable: mismo contenido ⇒ mismo invoice id."""
    return str(uuid.uuid5(_NAMESPACE_UUID, sha256))


class Store:
    """SQLite en `<root>/store.db` + ledger JSONL en `<root>/ledger/`."""

    def __init__(self, root: str | Path = ".sdd") -> None:
        self.root = Path(root)
        self.db_path = self.root / "store.db"
        self.ledger_dir = self.root / "ledger"
        self.ledger_path = self.ledger_dir / "ledger.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._init_schema()

    # ---------------------------------------------------------------- schema

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                file_id TEXT PRIMARY KEY,
                invoice_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                result TEXT NOT NULL,
                rule_codes TEXT NOT NULL,
                numero_factura TEXT,
                pedido TEXT,
                config_version TEXT NOT NULL,
                engine_version TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                invoice_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                extractor TEXT NOT NULL,
                extractor_version TEXT NOT NULL,
                config_version TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                confidence REAL,
                outcome TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stage_cache (
                sha256 TEXT NOT NULL,
                stage TEXT NOT NULL,
                engine_version TEXT NOT NULL,
                config_version TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (sha256, stage, engine_version, config_version)
            );
            CREATE TABLE IF NOT EXISTS resolutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                invoice_id TEXT NOT NULL,
                resolved_by TEXT NOT NULL,
                before TEXT NOT NULL,
                after TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    # ---------------------------------------------------------------- cache

    def get_cached(self, sha256: str, stage: str, engine_version: str,
                   config_version: str) -> dict | None:
        row = self._conn.execute(
            "SELECT payload FROM stage_cache WHERE sha256=? AND stage=? "
            "AND engine_version=? AND config_version=?",
            (sha256, stage, engine_version, config_version),
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def put_cached(self, sha256: str, stage: str, engine_version: str,
                   config_version: str, payload: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO stage_cache "
            "(sha256, stage, engine_version, config_version, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (sha256, stage, engine_version, config_version,
             json.dumps(payload, sort_keys=True)),
        )
        self._conn.commit()

    # ---------------------------------------------------------------- evidence

    def record_evidence(self, row: EvidenceRow) -> None:
        self._conn.execute(
            "INSERT INTO evidence (file_id, invoice_id, stage, extractor, "
            "extractor_version, config_version, sha256, latency_ms, confidence, "
            "outcome, detail, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (row.file_id, row.invoice_id, row.stage, row.extractor,
             row.extractor_version, row.config_version, row.sha256,
             row.latency_ms, row.confidence, row.outcome, row.detail,
             _now()),
        )
        self._conn.commit()

    def count_evidence(self, file_id: str | None = None) -> int:
        if file_id is None:
            row = self._conn.execute("SELECT COUNT(*) c FROM evidence").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) c FROM evidence WHERE file_id=?",
                (file_id,),
            ).fetchone()
        return int(row["c"])

    # ---------------------------------------------------------------- decisions

    def record_decision(self, decision: Decision, sha256: str, *,
                        numero_factura: str, pedido: str,
                        engine_version: str) -> bool:
        """UPSERT de la decisión. Devuelve True si el estado cambió (y por
        tanto se escribe evento en el ledger)."""
        codes = ",".join(
            f"{v.code}:{v.outcome}" for v in decision.rule_verdicts
        )
        row = self._conn.execute(
            "SELECT result, rule_codes FROM invoices WHERE file_id=?",
            (decision.file_id,),
        ).fetchone()
        changed = row is None or row["result"] != decision.result \
            or row["rule_codes"] != codes
        self._conn.execute(
            "INSERT INTO invoices (file_id, invoice_id, sha256, result, "
            "rule_codes, numero_factura, pedido, config_version, engine_version, "
            "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(file_id) DO UPDATE SET invoice_id=excluded.invoice_id, "
            "sha256=excluded.sha256, result=excluded.result, "
            "rule_codes=excluded.rule_codes, numero_factura=excluded.numero_factura, "
            "pedido=excluded.pedido, config_version=excluded.config_version, "
            "engine_version=excluded.engine_version, updated_at=excluded.updated_at",
            (decision.file_id, decision.invoice_id, sha256, decision.result,
             codes, numero_factura, pedido,
             decision.config_snapshot.get("config_version", ""),
             engine_version, _now()),
        )
        self._conn.commit()
        if changed:
            self._ledger({
                "event": "decision",
                "file_id": decision.file_id,
                "invoice_id": decision.invoice_id,
                "sha256": sha256,
                "result": decision.result,
                "rule_codes": codes,
                "config_version": decision.config_snapshot.get("config_version"),
            })
        return changed

    def decision_for(self, file_id: str) -> StoredDecision | None:
        row = self._conn.execute(
            "SELECT * FROM invoices WHERE file_id=?", (file_id,)
        ).fetchone()
        if row is None:
            return None
        return StoredDecision(
            file_id=row["file_id"], invoice_id=row["invoice_id"],
            sha256=row["sha256"], result=row["result"],
            rule_codes=row["rule_codes"].split(","), numero_factura=row["numero_factura"],
            pedido=row["pedido"], config_version=row["config_version"],
            engine_version=row["engine_version"],
        )

    def all_decisions(self) -> list[StoredDecision]:
        rows = self._conn.execute(
            "SELECT * FROM invoices ORDER BY file_id"
        ).fetchall()
        return [
            StoredDecision(
                file_id=r["file_id"], invoice_id=r["invoice_id"],
                sha256=r["sha256"], result=r["result"],
                rule_codes=r["rule_codes"].split(",") if r["rule_codes"] else [],
                numero_factura=r["numero_factura"] or "",
                pedido=r["pedido"] or "",
                config_version=r["config_version"], engine_version=r["engine_version"],
            )
            for r in rows
        ]

    # ---------------------------------------------------------------- feedback

    def save_resolution(self, file_id: str, invoice_id: str, resolved_by: str,
                        before: str, after: str, note: str = "") -> None:
        """Resolución de un caso escalado (corpus de retroalimentación)."""
        self._conn.execute(
            "INSERT INTO resolutions (file_id, invoice_id, resolved_by, before, "
            "after, note, created_at) VALUES (?,?,?,?,?,?,?)",
            (file_id, invoice_id, resolved_by, before, after, note, _now()),
        )
        self._conn.commit()
        self._ledger({
            "event": "resolution", "file_id": file_id, "invoice_id": invoice_id,
            "resolved_by": resolved_by, "before": before, "after": after,
        })

    def resolutions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM resolutions ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- ledger

    def _ledger(self, event: dict) -> None:
        with open(self.ledger_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def ledger_events(self) -> list[dict]:
        if not self.ledger_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def close(self) -> None:
        self._conn.close()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())