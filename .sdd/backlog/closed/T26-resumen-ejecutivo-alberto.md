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

## Cerrado — decisiones tomadas (W3)

- **`albertitos.resumen`** (`python -m albertitos.resumen`): lee el store
  REAL en SOLO LECTURA (sqlite modo ro) + el maestro (hoja Pedidos_2026 con
  Importe_Total; NUNCA Pedidos_2025_OLD/backup/NO_TOCAR — avisadas) y
  produce `resumen_alberto.html` (jinja2, estilo de la UI) + `resumen_alberto.pdf`
  (typst, mismo binario; dos renderizadores del MISMO dict de datos).
- **El eslabón importe**: el ledger real no guarda importes; el join es
  file_id → pedido (store.db) → Importe_Total (maestro Pedidos_2026). Todo
  medido; las PAGAR sin entrada en el maestro NO se suman y se listan como
  aviso (jamás inventadas).
- **Demo real**: 433 PAGAR por 2 331 130,43 EUR (top-1: 2026-02-04_P001.pdf,
  10 869,07 €), 22 NO_PAGAR por motivos en llano ("el importe no coincide
  con el pedido"...) con 3 ejemplos cada uno, 45 escaladas ordenadas por
  importe (13 con importe; el resto «sin importe en el maestro» — honesto),
  avisos: 2 duplicados, 3 proveedores fantasma, 0 sin texto.
- **Sin datos ⇒ PENDIENTE** (store vacío ⇒ «PENDIENTE (sin importes en el
  maestro)» con etiqueta sin datos), jamás ceros falsos — testeado.
- **Seguridad del maestro**: solo se lee Pedidos_2026 + Proveedores; las
  hojas trampa se ignoran y se avisan en el propio resumen.
- **Tests** (7): totales = suma EXACTA de los PAGAR sembrados (11 176,16 €),
  motivos en llano con ejemplos, revisar ordenado por importe con
  placeholder honesto, hojas trampa ignoradas, HTML+PDF generados (PDF
  skip si no hay typst), store vacío ⇒ PENDIENTE, CLI. Suite: 229 passed,
  ruff limpio, sin secretos.
