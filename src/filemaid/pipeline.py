"""Pipeline: bucle worker largo — extracción → parser → motor de reglas → store.

Idempotente y reanudable: la clave es (sha256, stage, engine_version,
config_version). Re-procesar un item completado es un no-op que reusa la
evidencia. Un fallo de dependencia degrada (skipped:<reason>), nunca para el
lote. La pertenencia, el progreso y la finalización del lote viven en PouchDB:
una caída a mitad de lote se reanuda reutilizando las decisiones ya persistidas
y la salida final solo se escribe cuando todas las facturas esperadas tienen
decisión.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from filemaid.types import (
    OVERRIDE_EXTRACTOR,
    Candidate,
    ConfigSnapshot,
    Decision,
    ExtractionField,
    Result,
    RuleEvaluation,
    RuleVerdict,
)

from .config import AppConfig
from .extract.cache import FeatureCache, sha256_file
from .extract.ladder import IMAGE_SUFFIXES as EXTRACT_IMAGE_SUFFIXES
from .extract.ladder import extract_file
from .parse.parser import parse_fields
from .rules.config import RuleConfig
from .rules.engine import evaluate
from .rules.master import load_master
from .store.pouch import PouchStore, canonical, file_key
from .store.trace import ScanTrace, current_trace

_UUID_NAMESPACE = uuid.UUID("d5f04a3e-6f9a-4b3f-9d2f-5c1a2b3c4d5e")  # ns estable del proyecto
_SUPPORTED_SUFFIXES = {".pdf"} | EXTRACT_IMAGE_SUFFIXES


def invoice_id_for(sha256: str) -> str:
    """UUID interno estable: el file_id es solo el nombre de entrada."""
    return str(uuid.uuid5(_UUID_NAMESPACE, sha256))


def sync_if_configured(cfg: AppConfig) -> bool:
    """Best-effort remote sync; a remote outage never fails a completed command.

    Returns ``True`` when there is nothing to sync or the sync succeeded, and
    ``False`` when the remote was unreachable: local state stays durable and the
    pending sync is retried by the API loop or the next command.
    """
    try:
        settings = cfg.runtime_settings()
        if settings.get("mode") != "server" or not settings.get("sync_url"):
            return True
        PouchStore(cfg.root).sync(
            settings["sync_url"], os.environ.get("FILEMAID_SYNC_TOKEN", "")
        )
        return True
    except Exception:
        logging.getLogger(__name__).warning(
            "remote sync failed; evidence retained locally", exc_info=True
        )
        return False


def apply_overrides(
    fields: list[ExtractionField], overrides: list[dict]
) -> tuple[list[ExtractionField], list[dict]]:
    """Inject the latest committed override per field as an ``override`` candidate.

    Only the newest override per ``field_type`` is applied (older ones stay in
    the append-only history), so repeated corrections never pile up equal-score
    candidates. Every original candidate is preserved; the injected candidate
    has confidence 1.0 and ``override`` ranks first, so it wins a score tie
    deterministically while still flowing through ``escoger`` (format tests,
    score threshold, rule ``min_confidence``) and the rule's ``chosen_candidates``.
    """
    latest: dict[str, dict] = {}
    for doc in sorted(overrides, key=lambda d: (d.get("timestamp", 0), d["_id"])):
        payload = doc.get("payload") or {}
        field_type = payload.get("field_type")
        if field_type:
            latest[field_type] = doc
    if not latest:
        return fields, []

    by_type = {f.type: f for f in fields}
    applied: list[dict] = []
    for field_type, doc in sorted(latest.items()):
        payload = doc["payload"]
        value = payload.get("after")
        field = by_type.get(field_type)
        if field is None:
            field = ExtractionField(type=field_type)
            fields.append(field)
            by_type[field_type] = field
        field.values.insert(
            0, Candidate(extractor=OVERRIDE_EXTRACTOR, value=value, confidence=1.0)
        )
        applied.append(
            {
                "field_type": field_type,
                "value": value,
                "before": payload.get("before"),
                "who": payload.get("who", ""),
                "rung": payload.get("rung", ""),
                "reason": payload.get("reason", ""),
                "override_id": doc["_id"],
                "timestamp": doc.get("timestamp"),
            }
        )
    return fields, applied


class Pipeline:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.store = PouchStore(cfg.root)
        self.store.request(op="info")
        self.cache = FeatureCache(self.store)
        self.rule_config = RuleConfig.load(cfg.rules_config_path)
        self.master = load_master(cfg.master_dir)
        self._in_batch = False
        self._last_scan_id: str | None = None
        self.last_batch_id: str | None = None

    @property
    def last_scan_id(self) -> str | None:
        """Scan id produced by the most recent ``process_pdf`` call."""
        return self._last_scan_id

    def _sync_if_configured(self) -> None:
        """Best-effort remote sync; a remote outage never fails a saved invoice."""
        sync_if_configured(self.cfg)

    def run_lote(self, lote_dir: Path, outcomes_path: Path) -> list[Decision]:
        """Procesa el lote de forma reanudable; pertenencia y progreso viven en PouchDB.

        El ``batch_id`` es determinista a partir del directorio, la versión de
        reglas, la config de extracción, el sha256 del maestro y el sha256 de
        cada fichero: repetir el comando reanuda el mismo lote en lugar de
        duplicarlo. La salida final solo se escribe cuando todas las facturas
        esperadas tienen decisión persistida; un fallo deja el lote incompleto y
        sin artefacto final.
        """
        entries = self._lote_entries(lote_dir)
        expected = [name for name, _ in entries]
        config_version = self.cfg.extraction_config().get("config_version", "")
        batch_id = self._batch_id(lote_dir, entries, config_version)
        self.last_batch_id = batch_id
        self._ensure_batch(batch_id, lote_dir, expected, config_version)

        if self.store.get(f"batch_result:{batch_id}") is not None:
            export_outcomes(self.store, batch_id, outcomes_path)
            self._archive_export(batch_id, outcomes_path)
            self._sync_if_configured()
            return self._decisions_for_batch(batch_id, entries)

        decisions: list[Decision] = []
        errors: list[str] = []
        self._in_batch = True
        try:
            for name, sha in entries:
                if sha is None:
                    errors.append(name)
                    continue
                item = self._batch_item(batch_id, name, sha)
                if item is not None and self.store.get(item["decision_id"]) is not None:
                    decisions.append(self._decision_from_doc(item["decision_id"]))
                    continue
                try:
                    decision = self.process_pdf(lote_dir / name)
                    scan_id = self._verified_scan_id(name, sha)
                except Exception:
                    errors.append(name)
                    logging.getLogger(__name__).exception("No se pudo procesar %s", name)
                    continue
                decisions.append(decision)
                self._record_batch_item(batch_id, name, sha, scan_id)
        finally:
            self._in_batch = False

        missing = self._missing_items(batch_id, entries)
        if missing or errors:
            self._sync_if_configured()
            raise RuntimeError(
                f"lote incompleto: faltan={sorted(set(missing) | set(errors))}; "
                "no se emite salida final"
            )
        if self.cfg.extraction_config().get("config_version", "") != config_version:
            self._sync_if_configured()
            raise RuntimeError(
                "la configuración de extracción cambió durante el lote; no se emite salida final"
            )

        self.store.put(
            {
                "_id": f"batch_result:{batch_id}",
                "kind": "batch_result",
                "batch_id": batch_id,
                "run_id": self.rule_config.version,
                "status": "complete",
                "expected": expected,
                "decisions": [
                    f"decision:{sid}" for sid in self._batch_scan_ids(batch_id, entries)
                ],
                "finished_at": time.time(),
            }
        )
        export_outcomes(self.store, batch_id, outcomes_path)
        self._archive_export(batch_id, outcomes_path)
        self._sync_if_configured()
        return decisions

    def _lote_entries(self, lote_dir: Path) -> list[tuple[str, str | None]]:
        """Nombre exacto y sha256 de cada fichero soportado, ordenado por nombre."""
        pdfs = sorted(p for p in lote_dir.iterdir() if p.suffix.lower() in _SUPPORTED_SUFFIXES)
        entries: list[tuple[str, str | None]] = []
        for pdf in pdfs:
            try:
                sha: str | None = sha256_file(pdf)
            except OSError:
                sha = None
            entries.append((pdf.name, sha))
        return entries

    def _batch_id(
        self, lote_dir: Path, entries: list[tuple[str, str | None]], config_version: str
    ) -> str:
        payload = canonical(
            {
                "lote": str(lote_dir.resolve()),
                "run_id": self.rule_config.version,
                "extraction_config_version": config_version,
                "master_sha256": self.master.sha256,
                "files": [[name, sha] for name, sha in entries],
            }
        )
        return str(uuid.uuid5(_UUID_NAMESPACE, payload.decode("utf-8")))

    def _ensure_batch(
        self, batch_id: str, lote_dir: Path, expected: list[str], config_version: str
    ) -> None:
        if self.store.get(f"batch:{batch_id}") is not None:
            return
        self.store.put(
            {
                "_id": f"batch:{batch_id}",
                "kind": "batch",
                "batch_id": batch_id,
                "run_id": self.rule_config.version,
                "extraction_config_version": config_version,
                "master_sha256": self.master.sha256,
                "lote": str(lote_dir.resolve()),
                "expected": expected,
                "started_at": time.time(),
            }
        )

    def _batch_item(self, batch_id: str, name: str, sha: str) -> dict | None:
        return self.store.get(f"batch_item:{batch_id}:{file_key(name, sha)}")

    def _verified_scan_id(self, name: str, sha: str) -> str:
        """El scan recién creado debe corresponder al fichero esperado (sha inicial)."""
        scan_id = self._last_scan_id
        if scan_id is None:
            raise RuntimeError("invariante: process_pdf no fijó scan_id")
        decision = self.store.get(f"decision:{scan_id}")
        if decision is None:
            raise RuntimeError(f"decisión ausente tras procesar {name}")
        if decision.get("file_key") != file_key(name, sha):
            raise RuntimeError(f"el fichero {name} cambió durante el lote")
        return scan_id

    def _record_batch_item(self, batch_id: str, name: str, sha: str, scan_id: str) -> None:
        """Persist the per-item batch association so a crash never loses membership."""
        key = file_key(name, sha)
        self.store.put(
            {
                "_id": f"batch_item:{batch_id}:{key}",
                "kind": "batch_item",
                "batch_id": batch_id,
                "file_id": name,
                "file_key": key,
                "scan_id": scan_id,
                "decision_id": f"decision:{scan_id}",
                "timestamp": time.time(),
            }
        )

    def _missing_items(self, batch_id: str, entries: list[tuple[str, str | None]]) -> list[str]:
        missing: list[str] = []
        for name, sha in entries:
            if sha is None:
                missing.append(name)
                continue
            item = self._batch_item(batch_id, name, sha)
            if item is None or self.store.get(item["decision_id"]) is None:
                missing.append(name)
        return missing

    def _batch_scan_ids(self, batch_id: str, entries: list[tuple[str, str | None]]) -> list[str]:
        ids: list[str] = []
        for name, sha in entries:
            if sha is None:
                continue
            item = self._batch_item(batch_id, name, sha)
            if item is not None:
                ids.append(item["scan_id"])
        return ids

    def _decisions_for_batch(
        self, batch_id: str, entries: list[tuple[str, str | None]]
    ) -> list[Decision]:
        decisions: list[Decision] = []
        for name, sha in entries:
            item = self._batch_item(batch_id, name, sha) if sha is not None else None
            if item is None:
                raise RuntimeError(f"asociación de lote ausente para {name}")
            decisions.append(self._decision_from_doc(item["decision_id"]))
        return decisions

    def _decision_from_doc(self, decision_id: str) -> Decision:
        doc = self.store.get(decision_id)
        if doc is None:
            raise RuntimeError(f"decisión ausente en PouchDB: {decision_id}")
        return decision_from_dict(self.store.hydrate(doc)["decision"])

    def _archive_export(self, batch_id: str, outcomes_path: Path) -> None:
        """Store the final export once per batch (never once per scan)."""
        prefix = f"artifact:batch-{batch_id}:"
        if any(d.get("stage") == "export" for d in self.store.list(prefix)):
            return
        identity = {"scan_id": f"batch-{batch_id}", "batch_id": batch_id}
        self.store.artifact(
            identity, "export", outcomes_path.name, outcomes_path, "application/x-ndjson"
        )

    def process_pdf(
        self, pdf_path: Path, scan_id: str | None = None, resume: bool = False
    ) -> Decision:
        try:
            sha = sha256_file(pdf_path)
        except OSError as exc:
            error_scan_id = str(uuid.uuid4())
            self.store.put(
                {
                    "_id": f"event:{error_scan_id}:{uuid.uuid4()}",
                    "kind": "event",
                    "scan_id": error_scan_id,
                    "file_id": pdf_path.name,
                    "file_key": None,
                    "invoice_id": None,
                    "timestamp": time.time(),
                    "type": "item_error",
                    "payload": {"file_id": pdf_path.name, "error": f"{type(exc).__name__}: {exc}"},
                }
            )
            raise
        trace = ScanTrace(
            self.store, pdf_path, sha, invoice_id_for(sha), scan_id=scan_id, resume=resume
        )
        self._last_scan_id = trace.scan_id
        with trace.active():
            try:
                source = trace.begin(
                    self.rule_config.version,
                    self.cfg.extraction_config().get("config_version", ""),
                    self.master.sha256,
                )
                trace.event(
                    "invoice_seen",
                    {
                        "invoice_id": trace.identity["invoice_id"],
                        "file_id": pdf_path.name,
                        "sha256": sha,
                    },
                )
                decision = self._process_pdf(source)
                if not self._in_batch:
                    self._sync_if_configured()
                return decision
            except Exception as exc:
                trace.event(
                    "item_error",
                    {
                        **trace.identity,
                        "file_id": pdf_path.name,
                        "error": f"{exc.__class__.__name__}: {exc}",
                    },
                )
                raise

    def _process_pdf(self, pdf_path: Path) -> Decision:
        t_start = time.perf_counter()
        sha = sha256_file(pdf_path)
        invoice_id = invoice_id_for(sha)
        config_version = self.rule_config.version

        # Extracción (escalera por página, con cache e idempotencia)
        t_extract_0 = time.perf_counter()
        trace = current_trace()
        pages_dir = self.cfg.pages_dir / (trace.scan_id if trace else invoice_id)
        pages = extract_file(pdf_path, self.cache, self.cfg.extraction_config(), pages_dir)
        extraction_ms = round((time.perf_counter() - t_extract_0) * 1000)
        if trace:
            trace.pages(pages, pages_dir)

        rung_latencies: dict[str, int] = {}
        for page in pages:
            for feat in page.features:
                stage_name = feat.extraction_method.split(":")[0]
                rung_latencies[f"{stage_name}_p{feat.page if feat.page is not None else 0}"] = (
                    feat.latency_ms
                )

        # Parser: todos los candidatos se conservan
        t_parse_0 = time.perf_counter()
        fields = parse_fields(pages)
        parser_ms = round((time.perf_counter() - t_parse_0) * 1000)
        # Correcciones humanas: la última por campo entra como candidato
        # `override`; los candidatos originales se conservan en la evidencia.
        key = trace.identity["file_key"] if trace else file_key(pdf_path.name, sha)
        fields, applied_overrides = apply_overrides(fields, self._overrides_for(key))
        if trace:
            trace.fields(fields, parser_ms)

        # Decisión (motor puro) + evidencia
        t_eval_0 = time.perf_counter()
        decision = evaluate(
            {f.type: f for f in fields},
            self.master,
            self.rule_config,
            invoice_id,
            pdf_path.name,
            extractor_versions=self._extractor_versions(pages),
        )
        evaluation_ms = round((time.perf_counter() - t_eval_0) * 1000)
        total_ms = round((time.perf_counter() - t_start) * 1000)

        stage_timings: dict[str, int] = {
            "extraction_ms": extraction_ms,
            "parser_ms": parser_ms,
            "evaluation_ms": evaluation_ms,
            "total_ms": total_ms,
            **rung_latencies,
        }
        decision.extraction_ms = extraction_ms
        decision.parser_ms = parser_ms
        decision.evaluation_ms = evaluation_ms
        decision.total_ms = total_ms
        decision.timings = stage_timings

        run_id = config_version
        if trace:
            trace.decision(decision, run_id, applied_overrides)
            trace.event(
                "decision",
                {
                    "invoice_id": invoice_id,
                    "file_id": decision.file_id,
                    "result": decision.result.value,
                    "run_id": run_id,
                    "extraction_ms": extraction_ms,
                    "parser_ms": parser_ms,
                    "evaluation_ms": evaluation_ms,
                    "total_ms": total_ms,
                    "timings": stage_timings,
                },
            )
        return decision

    def reprocess(self, invoice_id: str, pdf_path: Path) -> Decision:
        """Reprocesado tras un override: la decisión se recalcula de forma determinista."""
        return self.process_pdf(pdf_path)

    def _overrides_for(self, key: str) -> list[dict]:
        """Human overrides for a file key, oldest first (append-only history)."""
        file = self.store.get(f"file:{key}")
        if file is None:
            return []
        return [
            self.store.hydrate(d)
            for d in self.store.for_file(file["file_id"], "event")
            if d.get("file_key") == key and d.get("type") == "override"
        ]

    def _extractor_versions(self, pages: list) -> dict[str, str]:
        versions: dict[str, str] = {}
        for page in pages:
            for feat in page.features:
                if feat.extractor_version:
                    versions.setdefault(feat.extraction_method, feat.extractor_version)
        return versions


def reprocess_from_store(
    store: PouchStore,
    cfg: AppConfig,
    file_id: str,
    file_key: str = "",
    scan_id: str | None = None,
    resume: bool = False,
) -> tuple[Decision, str]:
    """Restore the original from PouchDB attachments and reprocess deterministically.

    Shared by the review service and the API so both apply the same overrides.
    Returns the new decision and the scan id that produced it.
    """
    if not file_id or Path(file_id).name != file_id or file_id in {".", ".."}:
        raise ValueError("nombre de fichero inválido")
    scans = store.for_file(file_id, "scan")
    if file_key:
        scans = [s for s in scans if s["file_key"] == file_key]
    elif len({s["file_key"] for s in scans}) > 1:
        raise ValueError("basename ambiguo: indique file_key")
    if not scans:
        raise KeyError(file_id)
    scans.sort(key=lambda s: (s["timestamp"], s["_id"]), reverse=True)
    artifacts = store.for_file(file_id, "artifact")
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
        raise KeyError("artefacto de entrada no encontrado")
    work = cfg.root / "work"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as temp:
        pdf = Path(temp) / file_id
        with pdf.open("wb") as output:
            for chunk in store.read_artifact(original["_id"]):
                output.write(chunk)
        pipeline = Pipeline(cfg)
        decision = pipeline.process_pdf(pdf, scan_id=scan_id, resume=resume)
        if pipeline.last_scan_id is None:
            raise RuntimeError("invariante: process_pdf no fijó scan_id")
        return decision, pipeline.last_scan_id


def write_outcomes(rows: list[dict[str, Any]], path: Path) -> None:
    """Write outcomes atomically (temp + rename) so a crash never leaves a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def export_outcomes(store: PouchStore, batch_id: str, path: Path) -> list[dict[str, Any]]:
    """Emit outcomes.jsonl from the DB batch result; only complete batches export."""
    result = store.get(f"batch_result:{batch_id}")
    if result is None or result.get("status") != "complete":
        raise RuntimeError(f"lote {batch_id} incompleto; no se emite salida final")
    decision_ids = result.get("decisions", [])
    expected = result.get("expected", [])
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for decision_id in decision_ids:
        doc = store.get(decision_id)
        if doc is None:
            raise RuntimeError(f"decisión ausente en PouchDB: {decision_id}")
        doc = store.hydrate(doc)
        file_id = doc["file_id"]
        outcome = doc["decision"]["result"]
        if Path(file_id).name != file_id or file_id in {".", ".."}:
            raise RuntimeError(f"file_id inválido en el lote {batch_id}: {file_id!r}")
        if outcome not in {"PAGAR", "NO_PAGAR", "ESCALAR"}:
            raise RuntimeError(f"resultado inválido en el lote {batch_id}: {outcome!r}")
        if file_id in seen:
            raise RuntimeError(f"file_id duplicado en el lote {batch_id}: {file_id!r}")
        seen.add(file_id)
        rows.append({"file_id": file_id, "result": outcome})
    if seen != set(expected):
        raise RuntimeError(
            f"lote {batch_id} incompleto: {sorted(seen)} != {sorted(expected)}"
        )
    rows.sort(key=lambda r: r["file_id"])
    write_outcomes(rows, path)
    return rows


def decision_from_dict(data: dict[str, Any]) -> Decision:
    """Reconstruye una Decision persistida para reanudar un lote sin re-extraer."""
    evaluations = [
        RuleEvaluation(
            code=r["code"],
            verdict=RuleVerdict(r["verdict"]),
            reason=r.get("reason", ""),
            consumed=r.get("consumed", {}),
            chosen_candidates=r.get("chosen_candidates", {}),
            reason_code=r.get("reason_code", ""),
        )
        for r in data.get("rule_evaluations", [])
    ]
    snapshot = data.get("config_snapshot")
    if isinstance(snapshot, dict):
        snapshot = ConfigSnapshot(**snapshot)
    return Decision(
        invoice_id=data["invoice_id"],
        file_id=data["file_id"],
        result=Result(data["result"]),
        rule_evaluations=evaluations,
        config_snapshot=snapshot,
        extraction_ms=data.get("extraction_ms", 0),
        parser_ms=data.get("parser_ms", 0),
        evaluation_ms=data.get("evaluation_ms", 0),
        total_ms=data.get("total_ms", 0),
        timings=data.get("timings", {}),
    )
