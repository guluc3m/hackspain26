# T33-M2 · Un solo PdfReader por página en la escalera
assignee: W1
priority: p2

## Objetivo
`ExtractionLadder` re-parsea el PDF en cada llamada: `extract_file` crea un
`PdfReader` para contar páginas y `_extract_text` crea OTRO por página (en un
PDF de 2 páginas ⇒ 3 parses completos). Menor: crear UNO por `extract_page` y
reutilizarlo.

## Cambio
- `extract_page(pdf_bytes, ...)`: crea `PdfReader(io.BytesIO(pdf_bytes))` una
  vez; `_extract_text(reader, page_index)` reutiliza el reader con su
  try/except intacto (un PDF dañado degrada, no aborta).
- `extract_file` sigue creando el suyo solo para contar páginas.
- Cero cambios de comportamiento: mismas features, mismos cache keys.

## Test
El suite completo de la escalera (test_extract_ladder, test_psm_config,
test_run) es el test de comportamiento; añadir assert de que una página con
PDF dañado sigue resolviendo a `""` sin excepción.