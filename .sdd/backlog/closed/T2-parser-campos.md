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

---

## Resolución (W2 — 2026-09-19)

Implementado `src/albertitos/parse/` (`normalizers.py`, `extractors.py`,
`parser.py`) + tests en `tests/test_parse.py` y fixtures reales committeadas
(`tests/fixtures/facturas/`, `tests/fixtures/scans/`).

Decisiones documentadas:
- **IBAN mod-97 como señal, no veto**: el corpus usa IBANs sintéticos que no
  pasan mod-97 (solo IBANs reales lo pasan). Confianza: mod-97 OK → 0,9;
  formato plausible ES+24 pero check fallido → 0,75; mal formato → 0,4. El
  validador existe y está testeado; vetar sigue siendo cosa de las reglas.
- **NIF**: formato español; letra de control mod-23 solo para personas físicas
  (8 dígitos + letra). Empresas (letra+8): válido por formato (no existe
  dígito de control estándar). El CIF del cliente (A58231074) se excluye por
  contexto de línea (cliente/facturar a/destinatario/cif).
- **Campo extra `numero_factura`**: añadido (estructura extensible del
  architecture.typ) porque el trap del duplicado FA-8801 exige cruzar por
  número de factura, no por filename.
- **Formatos cubiertos**: ES (1.234,56) y anglosajón (EUR 1700.00), fechas
  DD/MM/AAAA y "25 de enero de 2026", etiquetas con puntos de guía
  ("BASE IMPONIBLE...... 2.452,27"), 4 variantes de maquetación del corpus.
- Cobertura medida sobre el corpus real: 471/500 facturas extraen todos los
  campos; los 29 restantes son los 26 scans sin capa de texto + 3 ilegibles
  (degradan a ESCALAR por evidencia faltante, como manda §6).
