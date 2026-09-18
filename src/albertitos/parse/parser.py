"""Parser: ExtractionFeature → ExtractionField (AGENTS.md §2, architecture.typ).

Fase de interpretación: produce `ExtractionField` con TODOS los candidatos
conservados, cada uno con extractor, confianza en [0,1] y referencia a la
feature que lo produjo. Nunca colapsa valores en el store.
"""

from __future__ import annotations

import hashlib

from albertitos.parse import extractors as ex
from albertitos.types import Candidate, ExtractionFeature, ExtractionField

# Features cuyo `data` es texto interpretable por el parser.
TEXT_FEATURE_TYPES = ("pdf_text", "ocr_text", "vlm_text")

# Orden de emisión de campos (determinista).
FIELD_ORDER = (
    "nif",
    "iban",
    "fecha",
    "pedido",
    "numero_factura",
    "base",
    "iva_pct",
    "iva_amount",
    "total",
    "proveedor",
)

# Registro de extractores por campo. Añadir un campo aquí no toca la
# extracción ni el motor de reglas (extensible por país, architecture.typ).
EXTRACTORS: dict[str, list[tuple[str, object]]] = {
    "nif": [("regex-nif", ex.extraer_nif)],
    "iban": [("regex-iban", ex.extraer_iban)],
    "fecha": [("regex-fecha", ex.extraer_fecha)],
    "pedido": [("regex-pedido", ex.extraer_pedido)],
    "numero_factura": [("regex-num-factura", ex.extraer_numero_factura)],
    "base": [("regex-importe", ex.extraer_base)],
    "iva_pct": [("regex-iva-pct", ex.extraer_iva_pct)],
    "iva_amount": [("regex-iva", ex.extraer_iva_amount)],
    "total": [("regex-total", ex.extraer_total)],
    "proveedor": [
        ("header-empresa", ex._proveedor_header),
        ("emisor", ex._proveedor_emisor),
    ],
}


def _feature_ref(feature: ExtractionFeature) -> str:
    ref = feature.sha256
    if not ref:
        data = feature.data
        raw = data if isinstance(data, (str, bytes)) else repr(data)
        if isinstance(raw, str):
            raw = raw.encode("utf-8", errors="replace")
        ref = hashlib.sha256(raw).hexdigest()
    return f"{feature.type}:{ref[:16]}"


def parse_invoice(features: list[ExtractionFeature]) -> list[ExtractionField]:
    """Convierte las features de una factura en campos con candidatos.

    - Solo interpreta features de texto (pdf_text, ocr_text, vlm…).
    - Cada candidato referencia la feature que lo produjo (feature_ref).
    - Nunca descarta un candidato: la ambigüedad es señal para las reglas y
      para la UI de revisión.
    """
    text_features = [f for f in features if f.type in TEXT_FEATURE_TYPES]
    collected: dict[str, list[Candidate]] = {}
    for feature in text_features:
        if not isinstance(feature.data, str) or not feature.data.strip():
            continue
        ref = _feature_ref(feature)
        for field_type, runners in EXTRACTORS.items():
            for extractor_name, fn in runners:
                for value, confidence in fn(feature.data):  # type: ignore[operator]
                    conf = min(1.0, max(0.0, float(confidence)))
                    cand = Candidate(
                        extractor=extractor_name,
                        value=value,
                        confidence=conf,
                        feature_ref=ref,
                    )
                    collected.setdefault(field_type, []).append(cand)

    fields: list[ExtractionField] = []
    seen_types: set[str] = set()
    for field_type in FIELD_ORDER:
        seen_types.add(field_type)
        if field_type not in collected:
            continue
        fields.append(ExtractionField(
            type=field_type,
            timestamp=max(f.timestamp for f in text_features) if text_features else 0.0,
            values=_dedupe(collected[field_type]),
        ))
    # Campos dinámicos no registrados en FIELD_ORDER (extensibilidad por país)
    for field_type in sorted(set(collected) - seen_types):
        fields.append(ExtractionField(
            type=field_type,
            timestamp=max(f.timestamp for f in text_features) if text_features else 0.0,
            values=_dedupe(collected[field_type]),
        ))
    return fields


def _dedupe(cands: list[Candidate]) -> list[Candidate]:
    """Deduplica candidatos idénticos (mismo extractor, feature y valor).

    La deduplicación solo elimina repeticiones exactas del MISMO extractor sobre
    la MISMA feature; candidatos de extractores o features distintas se
    conservan siempre.
    """
    seen: set[tuple[str, str, object]] = set()
    out: list[Candidate] = []
    for c in cands:
        key = (c.extractor, c.feature_ref, repr(c.value))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def field_by_type(
    fields: list[ExtractionField], field_type: str
) -> ExtractionField | None:
    """Devuelve el campo pedido, o None si no se extrajo."""
    for f in fields:
        if f.type == field_type:
            return f
    return None