"""Pipeline: bucle worker largo — extracción → parser → motor de reglas → store.

Idempotente y reanudable: la clave es (sha256, stage, engine_version,
config_version). Re-procesar un item completado es un no-op que reusa la
evidencia. Un fallo de dependencia degrada (skipped:<reason>), nunca para el
lote. Una caída a mitad de lote pierde como mucho el item en vuelo.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from filemaid.types import Decision

from .config import AppConfig
from .extract.cache import FeatureCache, sha256_file
from .extract.ladder import IMAGE_SUFFIXES as EXTRACT_IMAGE_SUFFIXES
from .extract.ladder import extract_file
from .parse.parser import parse_fields
from .rules.config import RuleConfig
from .rules.engine import evaluate
from .rules.master import load_master
from .store.pouch import PouchStore
from .store.trace import ScanTrace, current_trace

_UUID_NAMESPACE = uuid.UUID("d5f04a3e-6f9a-4b3f-9d2f-5c1a2b3c4d5e")  # ns estable del proyecto
_SUPPORTED_SUFFIXES = {".pdf"} | EXTRACT_IMAGE_SUFFIXES


def invoice_id_for(sha256: str) -> str:
    """UUID interno estable: el file_id es solo el nombre de entrada."""
    return str(uuid.uuid5(_UUID_NAMESPACE, sha256))


class Pipeline:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.store = PouchStore(cfg.root)
        self.store.request(op="info")
        self.cache = FeatureCache(self.store)
        self.rule_config = RuleConfig.load(cfg.rules_config_path)
        self.master = load_master(cfg.master_dir)
        self._batch_scans: dict[int, dict] | None = None

    def _sync_if_configured(self) -> None:
        settings = self.cfg.runtime_settings()
        if settings.get("mode") == "server":
            sync_url = settings.get("sync_url", "")
            if sync_url:
                token = os.environ.get("FILEMAID_SYNC_TOKEN", "")
                self.store.sync(sync_url, token)

    def run_lote(self, lote_dir: Path, outcomes_path: Path) -> list[Decision]:
        """Procesa todos los PDFs del lote (resumible desde cualquier punto)."""
        pdfs = sorted(p for p in lote_dir.iterdir() if p.suffix.lower() in _SUPPORTED_SUFFIXES)
        decisions: list[Decision] = []
        self._batch_scans = {}
        for pdf in pdfs:
            try:
                decisions.append(self.process_pdf(pdf))
            except Exception:
                logging.getLogger(__name__).exception("No se pudo procesar %s", pdf.name)
        emit_outcomes(decisions, outcomes_path)
        for decision in decisions:
            scan_identity = self._batch_scans.get(id(decision))
            if scan_identity:
                self.store.artifact(
                    scan_identity,
                    "export",
                    outcomes_path.name,
                    outcomes_path,
                    "application/x-ndjson",
                )
        self._batch_scans = None

        self._sync_if_configured()

        return decisions

    def process_pdf(self, pdf_path: Path) -> Decision:
        try:
            sha = sha256_file(pdf_path)
        except OSError as exc:
            scan_id = str(uuid.uuid4())
            self.store.put(
                {
                    "_id": f"event:{scan_id}:{uuid.uuid4()}",
                    "kind": "event",
                    "scan_id": scan_id,
                    "file_id": pdf_path.name,
                    "file_key": None,
                    "invoice_id": None,
                    "timestamp": time.time(),
                    "type": "item_error",
                    "payload": {"file_id": pdf_path.name, "error": f"{type(exc).__name__}: {exc}"},
                }
            )
            raise
        trace = ScanTrace(self.store, pdf_path, sha, invoice_id_for(sha))
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
                if self._batch_scans is not None:
                    self._batch_scans[id(decision)] = trace.identity
                else:
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
            trace.decision(decision, run_id)
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

    def _extractor_versions(self, pages: list) -> dict[str, str]:
        versions: dict[str, str] = {}
        for page in pages:
            for feat in page.features:
                if feat.extractor_version:
                    versions.setdefault(feat.extraction_method, feat.extractor_version)
        return versions


def emit_outcomes(decisions: list[Decision], path: Path) -> None:
    """outcomes.jsonl: file_id = nombre exacto del PDF; tres resultados solo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in decisions:
            row = {"file_id": d.file_id, "result": d.result.value}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def outcomes_from_store(store: PouchStore, run_id: str) -> list[dict[str, Any]]:
    matching_decisions = []
    for raw in store.list("decision:"):
        d = store.hydrate(raw)
        if d.get("run_id") == run_id:
            matching_decisions.append(d)
    matching_decisions.sort(key=lambda d: (d.get("file_id", ""), d.get("timestamp", 0)))
    latest_by_file: dict[str, dict] = {}
    identities: dict[str, str] = {}
    for d in matching_decisions:
        name = d["file_id"]
        key = d["file_key"]
        if name in identities and identities[name] != key:
            raise ValueError(f"Ambiguous filename in run: {name}; export the individual batch")
        identities[name] = key
        latest_by_file[d.get("file_id", "")] = d
    sorted_items = sorted(latest_by_file.values(), key=lambda d: d.get("file_id", ""))
    return [
        {"file_id": d.get("file_id", ""), "result": d.get("decision", {}).get("result", "")}
        for d in sorted_items
    ]
