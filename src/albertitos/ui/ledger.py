"""Lectura en SOLO LECTURA del store/ledger para la UI (AGENTS.md §9).

La UI nunca escribe en el store ni decide: las resoluciones humanas se
encolan como overrides en una cola aparte (`.sdd/review-queue/`) que el
pipeline consume; la decisión la recalcula siempre el motor determinista.

Formato esperado (alineado con T4): ficheros `*.jsonl` append-only, una línea
por registro con una clave `kind`:
  {"kind": "evidence", ...}  — fila de evidencia (AGENTS.md §5)
  {"kind": "decision", ...}  — decisión + veredictos + config snapshot
  {"kind": "fields",  ...}   — campos parseados (todas las candidatas) + imágenes
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RESULTADOS = ("PAGAR", "NO_PAGAR", "ESCALAR")


@dataclass
class EvidenceView:
    invoice_id: str
    stage: str
    extractor: str
    extractor_version: str
    config_version: str
    latency_ms: int
    confidence: float | None
    outcome: str
    detail: str
    cost_eur: float | None = None
    page: int | None = None


@dataclass
class VerdictView:
    code: str
    outcome: str  # "PASS" | "FAIL" | "UNKNOWN"
    reason: str
    consumed: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionView:
    invoice_id: str
    file_id: str  # nombre EXACTO del PDF, jamás normalizado
    result: str  # "PAGAR" | "NO_PAGAR" | "ESCALAR"
    verdicts: list[VerdictView]
    config_snapshot: dict[str, Any]
    timestamp: float = 0.0


@dataclass
class CandidateView:
    extractor: str
    value: Any
    confidence: float


@dataclass
class FieldView:
    type: str
    candidates: list[CandidateView]


@dataclass
class OverrideView:
    invoice_id: str
    file_id: str
    campo: str
    valor: str
    nota: str
    cuando: str


@dataclass
class LedgerView:
    decisions: list[DecisionView] = field(default_factory=list)
    evidence: list[EvidenceView] = field(default_factory=list)
    fields_by_invoice: dict[str, list[FieldView]] = field(default_factory=dict)
    images_by_invoice: dict[str, dict[int, str]] = field(default_factory=dict)
    overrides: list[OverrideView] = field(default_factory=list)


def load_ledger(store_dir: Path) -> list[dict[str, Any]]:
    """Lee todos los *.jsonl del ledger. Tolera líneas corruptas (no bloquea)."""
    registros: list[dict[str, Any]] = []
    if not store_dir.is_dir():
        return registros
    for ruta in sorted(store_dir.glob("*.jsonl")):
        with ruta.open("r", encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    rec = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    registros.append(rec)
    return registros


def build_view(
    registros: list[dict[str, Any]], overrides: list[OverrideView] | None = None
) -> LedgerView:
    vista = LedgerView(overrides=overrides or [])
    for rec in registros:
        kind = rec.get("kind")
        if kind == "evidence":
            vista.evidence.append(
                EvidenceView(
                    invoice_id=str(rec.get("invoice_id", "")),
                    stage=str(rec.get("stage", "")),
                    extractor=str(rec.get("extractor", "")),
                    extractor_version=str(rec.get("extractor_version", "")),
                    config_version=str(rec.get("config_version", "")),
                    latency_ms=int(rec.get("latency_ms", 0) or 0),
                    confidence=rec.get("confidence"),
                    outcome=str(rec.get("outcome", "")),
                    detail=str(rec.get("detail", "")),
                    cost_eur=rec.get("cost_eur"),
                    page=rec.get("page"),
                )
            )
        elif kind == "decision":
            veredictos = [
                VerdictView(
                    code=str(v.get("code", "")),
                    outcome=str(v.get("outcome", "")),
                    reason=str(v.get("reason", "")),
                    consumed=dict(v.get("consumed", {})),
                )
                for v in rec.get("rule_verdicts", [])
            ]
            vista.decisions.append(
                DecisionView(
                    invoice_id=str(rec.get("invoice_id", "")),
                    file_id=str(rec.get("file_id", "")),
                    result=str(rec.get("result", "")),
                    verdicts=veredictos,
                    config_snapshot=dict(rec.get("config_snapshot", {})),
                    timestamp=float(rec.get("timestamp", 0.0) or 0.0),
                )
            )
        elif kind == "fields":
            iid = str(rec.get("invoice_id", ""))
            campos: list[FieldView] = []
            for tipo, cands in rec.get("fields", {}).items():
                candidatos = [
                    CandidateView(
                        extractor=str(c.get("extractor", "")),
                        value=c.get("value"),
                        confidence=float(c.get("confidence", 0.0)),
                    )
                    for c in cands
                ]
                campos.append(FieldView(type=str(tipo), candidates=candidatos))
            vista.fields_by_invoice[iid] = campos
            imagenes: dict[int, str] = {}
            for pag, b64 in rec.get("page_images", {}).items():
                try:
                    imagenes[int(pag)] = str(b64)
                except (TypeError, ValueError):
                    continue
            if imagenes:
                vista.images_by_invoice[iid] = imagenes
    return vista


def decisive_codes(d: DecisionView) -> list[str]:
    """Códigos de regla que justifican el resultado (AGENTS.md §4)."""
    buscado = {"PAGAR": "PASS", "NO_PAGAR": "FAIL", "ESCALAR": "UNKNOWN"}.get(d.result)
    if buscado is None:
        return [v.code for v in d.verdicts]
    return [v.code for v in d.verdicts if v.outcome == buscado]


def ops_summary(vista: LedgerView) -> dict[str, Any]:
    """Agregados de la pantalla Operaciones. Todo lo devuelto es medido."""
    conteo = Counter(d.result for d in vista.decisions)
    con_evidencia = {e.invoice_id for e in vista.evidence}
    decididas = {d.invoice_id for d in vista.decisions}
    latencias = sum(e.latency_ms for e in vista.evidence)
    paginas = {(e.invoice_id, e.page) for e in vista.evidence if e.page is not None}
    costes = [e.cost_eur for e in vista.evidence if e.cost_eur is not None]
    version = None
    if vista.decisions:
        version = vista.decisions[-1].config_snapshot.get("rule_set_version")
    return {
        "total": len(vista.decisions),
        "conteo": {r: conteo.get(r, 0) for r in RESULTADOS},
        "pendientes": len(con_evidencia - decididas),
        "ms_por_pagina": round(latencias / len(paginas)) if paginas else None,
        "n_paginas": len(paginas),
        "coste_eur": round(sum(costes), 4) if costes else None,
        "n_registros_coste": len(costes),
        "rule_set_version": version,
    }


def facturas_rows(vista: LedgerView) -> list[dict[str, Any]]:
    """Una fila por factura, con la cadena de evidencia resumida."""
    evid: dict[str, list[EvidenceView]] = defaultdict(list)
    for e in vista.evidence:
        evid[e.invoice_id].append(e)
    decididos = {d.invoice_id for d in vista.decisions}
    filas: list[dict[str, Any]] = []
    for d in vista.decisions:
        evs = evid.get(d.invoice_id, [])
        confs = [e.confidence for e in evs if e.confidence is not None]
        filas.append(
            {
                "invoice_id": d.invoice_id,
                "file_id": d.file_id,
                "result": d.result,
                "codes": decisive_codes(d),
                "extractores": sorted({e.extractor for e in evs}),
                "latencia_ms": sum(e.latency_ms for e in evs),
                "confianza": min(confs) if confs else None,
                "paginas": sorted({e.page for e in evs if e.page is not None}),
                "n_evidencia": len(evs),
            }
        )
    for iid in sorted(set(evid) - decididos):
        evs = evid[iid]
        filas.append(
            {
                "invoice_id": iid,
                "file_id": "— aún sin decisión —",
                "result": "EN_PROCESO",
                "codes": [],
                "extractores": sorted({e.extractor for e in evs}),
                "latencia_ms": sum(e.latency_ms for e in evs),
                "confianza": None,
                "paginas": sorted({e.page for e in evs if e.page is not None}),
                "n_evidencia": len(evs),
            }
        )
    return filas


def factura_detalle(vista: LedgerView, invoice_id: str) -> dict[str, Any] | None:
    for d in vista.decisions:
        if d.invoice_id == invoice_id:
            return {
                "decision": d,
                "codes": decisive_codes(d),
                "evidencia": [e for e in vista.evidence if e.invoice_id == invoice_id],
                "campos": vista.fields_by_invoice.get(invoice_id, []),
                "imagenes": vista.images_by_invoice.get(invoice_id, {}),
            }
    evs = [e for e in vista.evidence if e.invoice_id == invoice_id]
    if evs:
        return {
            "decision": None,
            "codes": [],
            "evidencia": evs,
            "campos": vista.fields_by_invoice.get(invoice_id, []),
            "imagenes": vista.images_by_invoice.get(invoice_id, {}),
        }
    return None


def revision_queue(vista: LedgerView) -> list[dict[str, Any]]:
    """Cola de ESCALAR: candidatas lado a lado, desacuerdo resaltado."""
    cola: list[dict[str, Any]] = []
    for d in vista.decisions:
        if d.result != "ESCALAR":
            continue
        campos = []
        for f in vista.fields_by_invoice.get(d.invoice_id, []):
            valores = {json.dumps(c.value, sort_keys=True) for c in f.candidates}
            campos.append(
                {
                    "tipo": f.type,
                    "candidatos": f.candidates,
                    "desacuerdo": len(valores) > 1,
                }
            )
        desconocidas = [v for v in d.verdicts if v.outcome == "UNKNOWN"]
        cola.append(
            {
                "decision": d,
                "codes": decisive_codes(d),
                "campos": campos,
                "imagenes": vista.images_by_invoice.get(d.invoice_id, {}),
                "motivo": desconocidas[0].reason if desconocidas else "revisión requerida",
            }
        )
    return cola


def health(vista: LedgerView) -> dict[str, Any]:
    """Salud: fallos de proveedor/ERP, reintentos y estado degradado."""
    errores = [e for e in vista.evidence if e.outcome == "error"]
    omitidos = [e for e in vista.evidence if e.outcome.startswith("skipped")]
    repeticiones = Counter((e.invoice_id, e.stage, e.extractor) for e in vista.evidence)
    reintentos = [
        {"invoice_id": k[0], "stage": k[1], "extractor": k[2], "veces": v}
        for k, v in sorted(repeticiones.items())
        if v > 1
    ]
    return {
        "errores": errores,
        "omitidos": omitidos,
        "reintentos": reintentos,
        "degradado": bool(errores or omitidos),
    }


def reglas_activas(vista: LedgerView) -> dict[str, Any]:
    """Set activo y umbrales, desde el snapshot de la última decisión."""
    if not vista.decisions:
        return {"version": None, "umbrales": {}}
    snap = vista.decisions[-1].config_snapshot
    return {
        "version": snap.get("rule_set_version"),
        "umbrales": dict(snap.get("thresholds", {})),
    }


def what_if(vista: LedgerView, codigo: str, nuevo_umbral: float) -> list[dict[str, Any]]:
    """Vista «¿qué pasaría si…?»: veredictos que cambiarían de umbral.

    Solo lectura y orientativa: el motor recalcula de verdad al reprocesar.
    Cada veredicto guarda en `consumed` la confianza usada (`_confianza`) y el
    umbral vigente (`_umbral`); aquí se proyecta el cambio de umbral.
    """
    cambios: list[dict[str, Any]] = []
    for d in vista.decisions:
        for v in d.verdicts:
            if v.code != codigo:
                continue
            conf = v.consumed.get("_confianza")
            umbral = v.consumed.get("_umbral")
            if not isinstance(conf, (int, float)) or not isinstance(umbral, (int, float)):
                continue
            antes_falla = conf < umbral
            despues_falla = conf < nuevo_umbral
            if antes_falla == despues_falla:
                continue
            cambios.append(
                {
                    "file_id": d.file_id,
                    "invoice_id": d.invoice_id,
                    "antes": v.outcome,
                    "despues": "PASS" if not despues_falla else v.outcome,
                    "confianza": conf,
                    "umbral_actual": umbral,
                    "result_actual": d.result,
                }
            )
    return cambios
