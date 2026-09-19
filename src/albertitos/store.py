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
from dataclasses import dataclass, field
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
    nif: str = ""
    iban: str = ""
    extra: dict = field(default_factory=dict)


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
                updated_at TEXT NOT NULL,
                nif TEXT DEFAULT '',
                iban TEXT DEFAULT '',
                extra TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS decision_runs (
                file_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                invoice_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                result TEXT NOT NULL,
                rule_codes TEXT NOT NULL,
                numero_factura TEXT,
                pedido TEXT,
                nif TEXT DEFAULT '',
                iban TEXT DEFAULT '',
                extra TEXT DEFAULT '{}',
                config_version TEXT NOT NULL,
                engine_version TEXT NOT NULL,
                motivo TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY (file_id, run_id)
            );
            CREATE TABLE IF NOT EXISTS invoice_attrs (
                file_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (file_id, key)
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
        self._migrate()

    def _migrate(self) -> None:
        """Migraciones idempotentes de esquema (stores creados antes de T13).

        Esquema DINÁMICO: la columna `extra` (JSON) y la tabla `invoice_attrs`
        se añaden bajo demanda también a stores antiguos, sin perder datos."""
        for table in ("invoices", "decision_runs"):
            cols = {r["name"] for r in self._conn.execute(
                f"PRAGMA table_info({table})").fetchall()}
            if cols and "extra" not in cols:
                self._conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN extra TEXT DEFAULT '{{}}'")
        cols = {r["name"] for r in self._conn.execute(
            "PRAGMA table_info(invoices)").fetchall()}
        for col in ("nif", "iban"):
            if col not in cols:
                self._conn.execute(f"ALTER TABLE invoices ADD COLUMN {col} TEXT DEFAULT ''")
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
                        engine_version: str, run_id: str = "base",
                        nif: str = "", iban: str = "",
                        extra: dict | None = None) -> bool:
        """UPSERT de la decisión (estado actual) + fila de histórico en
        `decision_runs` (file_id, run_id) — T13: cada decisión nueva COEXISTE
        con la anterior (run_id distinto), jamás se sobreescribe el histórico.
        Devuelve True si el estado actual cambió (y se escribe en el ledger).

        Esquema dinámico: `extra` son campos no previstos según país/administración
        (ej. Perú: {"ruc": "20123456789", "moneda": "PEN", "monto_soles": 1250.5}).
        Se guardan: (a) íntegros en la columna JSON `extra` de invoices y
        decision_runs, y (b) como variables con nombre en `invoice_attrs`
        (clave-valor por factura) para filtrar después con SQL plano:

            store.record_decision(d, sha, numero_factura="F001", pedido="P01",
                                  extra={"ruc": "20123456789", "moneda": "PEN"})
            store.files_with_attr("moneda", "PEN")  # -> [file_id, ...]
        La primera vez que aparece una variable nueva se anota en el ledger
        (evento "new_field", trazabilidad §5). Los campos fijos (total, nif,
        iban, iva_amount, fecha, result...) y las queries existentes no cambian."""
        codes = ",".join(
            f"{v.code}:{v.outcome}" for v in decision.rule_verdicts
        )
        motivo = str(decision.config_snapshot.get("motivo", ""))
        extra = dict(extra or {})
        extra_json = json.dumps(extra, sort_keys=True, ensure_ascii=False)
        row = self._conn.execute(
            "SELECT result, rule_codes FROM invoices WHERE file_id=?",
            (decision.file_id,),
        ).fetchone()
        changed = row is None or row["result"] != decision.result \
            or row["rule_codes"] != codes
        self._conn.execute(
            "INSERT INTO invoices (file_id, invoice_id, sha256, result, "
            "rule_codes, numero_factura, pedido, config_version, engine_version, "
            "updated_at, nif, iban, extra) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(file_id) DO UPDATE SET invoice_id=excluded.invoice_id, "
            "sha256=excluded.sha256, result=excluded.result, "
            "rule_codes=excluded.rule_codes, numero_factura=excluded.numero_factura, "
            "pedido=excluded.pedido, config_version=excluded.config_version, "
            "engine_version=excluded.engine_version, updated_at=excluded.updated_at, "
            "nif=excluded.nif, iban=excluded.iban, extra=excluded.extra",
            (decision.file_id, decision.invoice_id, sha256, decision.result,
             codes, numero_factura, pedido,
             decision.config_snapshot.get("config_version", ""),
             engine_version, _now(), nif, iban, extra_json),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO decision_runs (file_id, run_id, invoice_id, "
            "sha256, result, rule_codes, numero_factura, pedido, nif, iban, "
            "extra, config_version, engine_version, motivo, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (decision.file_id, run_id, decision.invoice_id, sha256,
             decision.result, codes, numero_factura, pedido, nif, iban,
             extra_json, decision.config_snapshot.get("config_version", ""),
             engine_version, motivo, _now()),
        )
        self._register_attrs(decision.file_id, extra)
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
                "run_id": run_id,
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
            nif=_row_val(row, "nif"),
            iban=_row_val(row, "iban"),
            extra=_row_json(row, "extra"),
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
                nif=_row_val(r, "nif"), iban=_row_val(r, "iban"),
                extra=_row_json(r, "extra"),
            )
            for r in rows
        ]

    def decision_run_for(self, file_id: str, run_id: str = "base") -> StoredDecision | None:
        row = self._conn.execute(
            "SELECT * FROM decision_runs WHERE file_id=? AND run_id=?",
            (file_id, run_id),
        ).fetchone()
        if row is None:
            return None
        return StoredDecision(
            file_id=row["file_id"], invoice_id=row["invoice_id"],
            sha256=row["sha256"], result=row["result"],
            rule_codes=row["rule_codes"].split(",") if row["rule_codes"] else [],
            numero_factura=row["numero_factura"] or "",
            pedido=row["pedido"] or "",
            config_version=row["config_version"], engine_version=row["engine_version"],
            extra=_row_json(row, "extra"),
        )

    def resultados_por_file(self, file_ids: list[str]) -> dict[str, str]:
        """file_id → result en UNA query (estado del lote para la UI, T33-M2).

        Antes: `decision_for` por archivo en cada tick del runner ⇒ O(N²)
        SELECTs en un lote de 500. Mismo output, una query por tick."""
        if not file_ids:
            return {}
        out: dict[str, str] = {}
        CH = 400  # sqlite límite de params: chunks
        for i in range(0, len(file_ids), CH):
            chunk = list(file_ids[i:i + CH])
            placeholders = ",".join("?" for _ in chunk)
            rows = self._conn.execute(
                f"SELECT file_id, result FROM invoices "
                f"WHERE file_id IN ({placeholders})",
                chunk,
            ).fetchall()
            for r in rows:
                out[r["file_id"]] = r["result"]
        return out

    def run_ids(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT run_id FROM decision_runs ORDER BY run_id"
        ).fetchall()
        return [r["run_id"] for r in rows]

    def run_decisions(self, run_id: str = "base") -> list[StoredDecision]:
        rows = self._conn.execute(
            "SELECT * FROM decision_runs WHERE run_id=? ORDER BY file_id",
            (run_id,),
        ).fetchall()
        return [
            StoredDecision(
                file_id=r["file_id"], invoice_id=r["invoice_id"],
                sha256=r["sha256"], result=r["result"],
                rule_codes=r["rule_codes"].split(",") if r["rule_codes"] else [],
                numero_factura=r["numero_factura"] or "",
                pedido=r["pedido"] or "",
                config_version=r["config_version"], engine_version=r["engine_version"],
                nif=_row_val(r, "nif"), iban=_row_val(r, "iban"),
                extra=_row_json(r, "extra"),
            )
            for r in rows
        ]

    # ---------------------------------------------------------------- attrs

    def _register_attrs(self, file_id: str, extra: dict) -> None:
        """Registra variables nuevas con nombre cuando aparecen (esquema
        dinámico): `invoice_attrs` es clave-valor por factura, así cualquier
        campo nuevo es filtrable con SQL sin tocar el esquema fijo. La primera
        vez que se ve un nombre de variable se anota en el ledger."""
        for key, val in sorted(extra.items()):
            nuevo = self._conn.execute(
                "SELECT 1 FROM invoice_attrs WHERE key=? LIMIT 1", (key,)
            ).fetchone() is None
            self._conn.execute(
                "INSERT OR REPLACE INTO invoice_attrs (file_id, key, value) "
                "VALUES (?,?,?)",
                (file_id, key, str(val)),
            )
            if nuevo:
                self._ledger({"event": "new_field", "file_id": file_id, "key": key})

    def attrs_for(self, file_id: str) -> dict[str, str]:
        """Variables dinámicas registradas para una factura (clave → valor)."""
        rows = self._conn.execute(
            "SELECT key, value FROM invoice_attrs WHERE file_id=? ORDER BY key",
            (file_id,),
        ).fetchall()
        return {r["key"]: r["value"] for r in rows}

    def files_with_attr(self, key: str, value: str | None = None) -> list[str]:
        """file_ids con una variable dinámica dada (filtro opcional por valor)."""
        if value is None:
            rows = self._conn.execute(
                "SELECT file_id FROM invoice_attrs WHERE key=? ORDER BY file_id",
                (key,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT file_id FROM invoice_attrs WHERE key=? AND value=? "
                "ORDER BY file_id",
                (key, str(value)),
            ).fetchall()
        return [r["file_id"] for r in rows]

    def known_attr_keys(self) -> list[str]:
        """Nombres de variables dinámicas vistas hasta ahora."""
        rows = self._conn.execute(
            "SELECT DISTINCT key FROM invoice_attrs ORDER BY key"
        ).fetchall()
        return [r["key"] for r in rows]

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
        import os as _os
        if not self.ledger_dir.exists():
            print("DEBUG ledger dir GONE:", self.ledger_dir, "| root listado:",
                  _os.listdir(self.root) if self.root.exists() else "root-gone")
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


def _row_json(row, col: str) -> dict:
    """Dict JSON de columna tolerante a esquemas antiguos (sin la columna)."""
    try:
        raw = row[col]
    except IndexError:
        return {}
    if not raw:
        return {}
    try:
        return dict(json.loads(raw))
    except (TypeError, ValueError):
        return {}


def _row_val(row, col: str) -> str:
    """Valor de columna tolerante a esquemas antiguos (sqlite3.Row sin .get)."""
    try:
        return row[col] or ""
    except IndexError:
        return ""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
