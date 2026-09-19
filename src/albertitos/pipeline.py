"""Pipeline: bucle worker largo — extracción → parser → motor de reglas → store.

Idempotente y reanudable: la clave es (sha256, stage, engine_version,
config_version). Re-procesar un item completado es un no-op que reusa la
evidencia. Un fallo de dependencia degrada (skipped:<reason>), nunca para el
lote. Una caída a mitad de lote pierde como mucho el item en vuelo.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from albertitos.types import Decision

from .config import AppConfig
from .extract.cache import FeatureCache, sha256_file
from .extract.ladder import IMAGE_SUFFIXES as EXTRACT_IMAGE_SUFFIXES
from .extract.ladder import extract_file
from .parse.parser import parse_fields
from .rules.config import RuleConfig
from .rules.engine import evaluate
from .rules.master import load_master
from .store.db import Store
from .store.ledger import Ledger

_UUID_NAMESPACE = uuid.UUID("d5f04a3e-6f9a-4b3f-9d2f-5c1a2b3c4d5e")  # ns estable del proyecto
_SUPPORTED_SUFFIXES = {".pdf"} | EXTRACT_IMAGE_SUFFIXES


def invoice_id_for(sha256: str) -> str:
    """UUID interno estable: el file_id es solo el nombre de entrada."""
    return str(uuid.uuid5(_UUID_NAMESPACE, sha256))


class Pipeline:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.store = Store(cfg.store_path)
        self.ledger = Ledger(cfg.ledger_path)
        self.cache = FeatureCache(cfg.cache_dir)
        self.rule_config = RuleConfig.load(cfg.rules_config_path)
        self.master = load_master(cfg.master_dir)

    def run_lote(self, lote_dir: Path, outcomes_path: Path) -> list[Decision]:
        """Procesa todos los PDFs del lote (resumible desde cualquier punto)."""
        pdfs = sorted(p for p in lote_dir.iterdir() if p.suffix.lower() in _SUPPORTED_SUFFIXES)
        decisions: list[Decision] = []
        for pdf in pdfs:
            try:
                decisions.append(self.process_pdf(pdf))
            except Exception as exc:  # un item no tumba el lote
                self.ledger.append(
                    "item_error",
                    {"file_id": pdf.name, "error": f"{exc.__class__.__name__}: {exc}"},
                )
        emit_outcomes(decisions, outcomes_path)
        return decisions

    def process_pdf(self, pdf_path: Path) -> Decision:
        sha = sha256_file(pdf_path)
        invoice_id = invoice_id_for(sha)
        config_version = self.rule_config.version

        existing = self.store.invoice_by_sha(sha)
        if existing is None:
            self.store.upsert_invoice(invoice_id, pdf_path.name, sha)
        self.ledger.append("invoice_seen", {"invoice_id": invoice_id, "file_id": pdf_path.name, "sha256": sha})

        # Extracción (escalera por página, con cache e idempotencia)
        pages = extract_file(pdf_path, self.cache, self.cfg.extraction_config(), self.cfg.pages_dir)
        for page in pages:
            for feat in page.features:
                self.store.add_feature(
                    invoice_id,
                    stage=feat.extraction_method.split(":")[0],
                    page=feat.page,
                    extractor_version=feat.extractor_version,
                    config_version=config_version,
                    sha256=feat.sha256 or sha,
                    latency_ms=feat.latency_ms,
                    confidence=feat.confidence,
                    outcome=feat.extraction_method,
                    detail={"type": feat.type},
                )

        # Parser: todos los candidatos se conservan
        fields = parse_fields(pages)
        for f in fields:
            self.store.add_field(
                invoice_id,
                f.type,
                [{"extractor": c.extractor, "value": c.value, "confidence": c.confidence} for c in f.values],
            )

        # Decisión (motor puro) + evidencia
        decision = evaluate(
            {f.type: f for f in fields},
            self.master,
            self.rule_config,
            invoice_id,
            pdf_path.name,
            extractor_versions=self._extractor_versions(pages),
        )
        self.store.save_config_snapshot(decision.config_snapshot.config_version, asdict(decision.config_snapshot))
        run_id = config_version
        self.store.start_run(run_id, config_version, self.master.sha256)
        self.store.add_rule_evaluations(
            invoice_id, run_id,
            [{**asdict(e), "verdict": e.verdict.value} for e in decision.rule_evaluations],
        )
        self.store.save_decision(invoice_id, run_id, decision.result.value, asdict(decision.config_snapshot))
        self.store.finish_run(run_id)
        self.ledger.append(
            "decision",
            {"invoice_id": invoice_id, "file_id": decision.file_id,
             "result": decision.result.value, "run_id": run_id},
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


def outcomes_from_store(store: Store, run_id: str) -> list[dict[str, Any]]:
    rows = store.conn.execute(
        """SELECT i.file_id, d.result FROM decisions d JOIN invoices i ON i.id = d.invoice_id
           WHERE d.run_id = ? ORDER BY i.file_id""",
        (run_id,),
    ).fetchall()
    return [{"file_id": r["file_id"], "result": r["result"]} for r in rows]
