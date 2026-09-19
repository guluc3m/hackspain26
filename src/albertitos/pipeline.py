"""Pipeline por lotes: PDF → features → parse → decide → store → emit.

Glue de integración de T4: consume `ExtractionFeature` y emite decisiones al
store con idempotencia. La fuente de features es inyectable: cuando la
escalera completa de T1 (OCR/VLM/QR) esté integrada, se sustituye
`extract_features` sin tocar store/emit (contrato: features dentro,
decisiones fuera).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from albertitos.emit import list_pdf_files
from albertitos.extract.review import (
    aplicar_overrides,
    leer_overrides_pendientes,
    marcar_consumidas,
)
from albertitos.parse.parser import field_by_type, parse_invoice
from albertitos.rules import BatchContext, decide
from albertitos.rules.config import EngineConfig
from albertitos.rules.master import Maestro
from albertitos.store import Store, invoice_uuid
from albertitos.types import EvidenceRow, ExtractionFeature

ENGINE_NAME = "albertitos-pipeline"
ENGINE_VERSION = "1.0.0"
STAGE_FEATURES = "features"
STAGE_PARSE = "parse"
STAGE_DECISION = "decision"


@dataclass
class BatchReport:
    procesados: int = 0
    reutilizados: int = 0
    resultados: dict[str, str] = field(default_factory=dict)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _pypdf_version() -> str:
    import pypdf

    return getattr(pypdf, "__version__", "unknown")


def _mejor_valor(fields: list, tipo: str) -> str:
    f = field_by_type(fields, tipo)
    if not f or not f.values:
        return ""
    return str(f.values[0].value)


def extract_features(path: Path, sha256: str) -> tuple[list, dict]:
    """Rung 1 mínimo (pypdf, por página) → (features, stats).

    La escalera completa de T1 sustituye esta función con la misma interfaz.
    Los datos extraídos son NO CONFIABLES: las instrucciones del PDF son
    datos, nunca comandos (AGENTS.md §12).
    """
    from pypdf import PdfReader

    started = time.monotonic()
    stats = {"paginas": 0, "chars": 0, "outcome": "ok"}
    try:
        reader = PdfReader(path)
        textos = [(i + 1, pg.extract_text() or "")
                  for i, pg in enumerate(reader.pages)]
        stats["paginas"] = len(textos)
    except Exception as e:  # noqa: BLE001 — un PDF corrupto degrada, no aborta el lote
        stats["outcome"] = "error"
        stats["detail"] = f"pypdf: {e}"[:200]
        return [], stats
    texto_total = "\n".join(t for _, t in textos)
    stats["chars"] = len(texto_total)
    if not texto_total.strip():
        stats["outcome"] = "no-text-layer"  # rung 2+ (T1) lo rescataría
    return (
        [
            ExtractionFeature(
                type="pdf_text", extraction_method="pypdf", timestamp=time.time(),
                data=texto_total, sha256=sha256, latency_ms=_ms(started),
            )
        ]
        if texto_total.strip()
        else []
    ), stats


@dataclass(frozen=True)
class PipelineDeps:
    """Inyección de dependencias del lote."""

    master: Maestro
    config: EngineConfig
    engine_version: str = ENGINE_VERSION
    fail_injector: object = None  # callable(file_id, index) -> None | raise


def run_batch(pdf_dir: str | Path, store: Store, deps: PipelineDeps) -> BatchReport:
    """Procesa el lote con idempotencia: re-ejecutar completado = no-op.

    Orden determinista: file_id ascendente (base del NO_DOUBLE_PAYMENT).
    Si `fail_injector` lanza en el ítem N, el lote se corta ahí; re-ejecutarlo
    reanuda desde ese punto sin duplicados.
    """
    cfg = deps.config
    report = BatchReport()

    prev_num = {d.numero_factura: d.file_id
                for d in store.all_decisions() if d.numero_factura}
    prev_pedidos = {d.pedido for d in store.all_decisions()
                    if d.result == "PAGAR" and d.pedido}

    for index, path in enumerate(list_pdf_files(pdf_dir)):
        if deps.fail_injector is not None:
            deps.fail_injector(path.name, index)
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        invoice_id = invoice_uuid(sha256)

        cached = store.get_cached(sha256, STAGE_DECISION, deps.engine_version,
                                  cfg.config_version)
        # El cache es válido solo si este file_id ya tiene su fila de decisión
        # en el store (dos PDFs distintos pueden compartir sha256: el cache
        # acelera, pero la fila por file_id es lo que cuenta).
        if cached is not None and store.decision_for(path.name) is not None:
            report.reutilizados += 1
            report.resultados[path.name] = cached["result"]
            continue

        started = time.monotonic()
        features, stats = extract_features(path, sha256)
        store.record_evidence(EvidenceRow(
            file_id=path.name, invoice_id=invoice_id, stage=STAGE_FEATURES,
            extractor="pypdf", extractor_version=_pypdf_version(),
            config_version=cfg.config_version, sha256=sha256,
            latency_ms=_ms(started), confidence=None,
            outcome=stats.get("outcome", "ok"),
            detail=f"paginas={stats.get('paginas', 0)}, chars={stats.get('chars', 0)}",
        ))
        store.put_cached(sha256, STAGE_FEATURES, deps.engine_version,
                         cfg.config_version, {"features": len(features)})

        fields = parse_invoice(features)
        store.record_evidence(EvidenceRow(
            file_id=path.name, invoice_id=invoice_id, stage=STAGE_PARSE,
            extractor="parser", extractor_version=ENGINE_VERSION,
            config_version=cfg.config_version, sha256=sha256,
            latency_ms=_ms(started), confidence=None,
            outcome="ok" if fields else "empty",
            detail=",".join(sorted(f.type for f in fields)),
        ))

        # overrides humanos (T38-F6): alimentan SOLO la extracción; el motor
        # recalcula. Quedan marcados CONSUMIDOS para no re-inyectar.
        ruta_overrides = store.root / "review-queue" / "overrides.jsonl"
        pendientes = leer_overrides_pendientes(ruta_overrides)
        propias = [
            o for o in pendientes
            if o.get("file_id") == path.name or o.get("invoice_id") == invoice_id
        ]
        if propias:
            aplicadas = aplicar_overrides(fields, propias)
            marcar_consumidas(ruta_overrides, propias)
            store.record_evidence(EvidenceRow(
                file_id=path.name, invoice_id=invoice_id, stage="override",
                extractor="humano", extractor_version="ui", config_version=cfg.config_version,
                sha256=sha256, latency_ms=0, confidence=1.0, outcome="aplicado",
                detail=",".join(f"{a['campo']}={a['valor']}" for a in aplicadas)[:200],
            ))

        textos = tuple(f.data for f in features if isinstance(f.data, str))
        numero_factura = _mejor(fields, "numero_factura")
        pedido_id = _mejor(fields, "pedido")

        decision = decide(
            fields, textos, deps.master, cfg,
            BatchContext(facturas_vistas=dict(prev_num),
                         pedidos_pagados=frozenset(prev_pedidos)),
            invoice_id=invoice_id, file_id=path.name,
        )
        store.record_decision(
            decision, sha256, numero_factura=numero_factura,
            pedido=pedido_id, engine_version=deps.engine_version,
            nif=_mejor(fields, "nif"), iban=_mejor(fields, "iban"),
        )
        store.record_evidence(EvidenceRow(
            file_id=path.name, invoice_id=invoice_id, stage=STAGE_DECISION,
            extractor="rule-engine", extractor_version=deps.engine_version,
            config_version=cfg.config_version, sha256=sha256,
            latency_ms=_ms(started), confidence=None,
            outcome=decision.result,
            detail=",".join(f"{v.code}:{v.outcome}" for v in decision.rule_verdicts),
        ))
        store.put_cached(sha256, STAGE_DECISION, deps.engine_version,
                         cfg.config_version,
                         {"result": decision.result, "invoice_id": invoice_id})
        report.resultados[path.name] = decision.result
        report.procesados += 1
        if decision.result == "PAGAR" and pedido_id:
            prev_pedidos.add(pedido_id)
        if numero_factura:
            prev_num[numero_factura] = path.name
    return report


def _mejor(fields: list, tipo: str) -> str:
    """Escalar elegido por el parser para un campo (registro en consumed es
    cosa del motor; aquí solo se extrae para trazabilidad del lote)."""
    f = field_by_type(fields, tipo)
    if not f or not f.values:
        return ""
    best = max(f.values, key=lambda c: c.confidence)
    return str(best.value)


def build_deps(master_path: str | Path, rules_yaml: str | Path,
               *, fecha_referencia: str, fail_injector=None) -> PipelineDeps:
    """Helper de arranque: maestro + config + deps del pipeline."""
    from albertitos.rules import load_config, load_master

    cfg = load_config(rules_yaml, fecha_referencia=fecha_referencia)
    master = load_master(master_path, hojas_ignoradas=cfg.hojas_ignoradas)
    return PipelineDeps(master=master, config=cfg, fail_injector=fail_injector)