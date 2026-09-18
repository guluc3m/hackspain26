# T2 · Parser: features → campos con candidatos
assignee: W2
priority: p0

## Objetivo
Implementar `src/albertitos/parse/`: tomar `ExtractionFeature` y producir
`ExtractionField` (types.py) por factura.

## Campos
`nif`, `iban`, `fecha` (DD/MM/AAAA), `pedido` (PO-YYYY-NNNN / FA-NNNN / etc.),
`base`, `iva_pct`, `iva_amount`, `total`, `proveedor`. Campos dinámicos por
país según architecture.typ — deja la estructura extensible.

## Reglas duras
- TODOS los candidatos se conservan: cada campo lleva `values[]` con
  (extractor, value, confidence). Nunca colapsar en el store.
- Normalización española: importes `1.234,56` → Decimal; fechas DD/MM/AAAA.
- Validadores: NIF con letra de control, IBAN con mod-97 — como candidatos con
  confianza, no como veto (vetar es cosa de las reglas).
- Cada candidato referencia la feature que lo produjo (`feature_ref`).

## Criterios de aceptación
- Dado texto de una factura real de `tests/fixtures/`, el parser emite los
  campos con ≥1 candidato y confianzas en [0,1].
- Test: importe español con punto de miles y coma decimal se parsea exacto.
- Test: NIF válido/inválido por letra; IBAN válido/inválido por mod-97.
- Test: dos extractores en desacuerdo ⇒ 2 candidatos, ninguno descartado.
- `uv run pytest` y `uv run ruff check .` en verde.
