# T26 · BONUS: Resumen Ejecutivo para Alberto
assignee: W3
priority: p1

## Objetivo (criterio bonus: mejora adicional ORIGINAL para Alberto)
La necesidad concreta: Alberto no quiere 500 líneas de JSON — quiere saber
**"¿qué pago hoy y por qué?"**. Genera `resumen_alberto.pdf` (y `.html`) en
español llano desde el store REAL post-fix.

## Contenido (datos medidos, cero hardcodeo)
1. **Hoy se pagan**: nº de facturas y € TOTAL (suma de los PAGAR del lote) +
   tabla top-10 por importe (proveedor, file_id, importe).
2. **No se pagan (NO_PAGAR)**: nº + los motivos por regla, en llano
   ("el importe no coincide con el pedido"), con 3 ejemplos cada una.
3. **Te toca mirar (ESCALAR)**: nº + lista ordenada por urgencia (importe
   desc), con la página y el motivo — directamente enlazado a la cola de
   revisión de la UI.
4. **Avisos**: duplicados detectados, proveedores nuevos no dados de alta,
   facturas sin texto legible, coste de la corrida (medido).
5. Todo con la etiqueta medido/estimado y fuentes al pie (los mismos JSONs
   de .sdd/metrics/).

## Implementación
`src/albertitos/resumen.py` + `python -m albertitos.resumen` → PDF (typst,
mismo binario) + HTML (jinja, mismo estilo que la UI). El HTML es la fuente
del PDF (typst puede compilar el .typ que genera; si es más simple, dos
renderizadores del mismo dict de datos).

## Criterios de aceptación
- Genera ambos formatos desde el store sembrado en tests.
- Test: totales de la sección "hoy se pagan" = suma exacta de los PAGAR del
  JSON (no inventados); sin datos ⇒ placeholder PENDIENTE, jamás ceros falsos.
- pytest+ruff verde; ticket a closed en el mismo commit.
