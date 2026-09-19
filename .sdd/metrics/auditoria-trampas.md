# Auditoría de trampas contra el outcomes real del lote 1 (T17)

Outcomes: `.sdd/metrics/outcomes-lote1-post-fix.jsonl` (500 facturas) — 433 PAGAR / 22 NO_PAGAR / 45 ESCALAR.
Regla del ticket: NO se cambian resultados a mano; los ROJOS quedan
identificados con causa para que el supervisor decida reprocesar.

## Tabla trampa → obtenido → esperado

| trampa | obtenido | esperado | estado |
|---|---|---|---|
| 3 proveedores fantasma (IBAN ES6614910001213000098877) | obtenido ESCALAR×3; 3 facturas con el fantasma detectado por regla (IBAN ES6614910001213000098877); ninguna con resultado distinto de ESCALAR. | ESCALAR citando la regla | VERDE |
| Duplicado FA-8801 | VERDE (2026-05-28_P005.pdf=PAGAR; factura_8801.pdf=NO_PAGAR; el 2º no paga por NO_DOUBLE_PAYMENT) | 2ª copia NO_PAGAR (NO_DOUBLE_PAYMENT) o ESCALAR (§6) | — |
| Instrucciones embebidas (7) | VERDE (9 facturas con instrucción embebida marcadas; 0 PAGAR) | ninguna cambia el resultado | — |
| Pedidos con NIF vacío (0538–0557) | SIN MUESTRAS (0 facturas los citan en lote 1) | ESCALAR si aparecen | — |
| Outlier 84700 + pendiente_revisar | outlier 84700 (2026-07-01_P009.pdf, pedido PO-2026-0497): ESCALAR — VERDE; PO-2026-0007 (FA-8488_transportes.pdf): ESCALAR con PEDIDO_EN_REVISION — VERDE; PO-2026-0141 (2026-79712_limpiezas.pdf): ESCALAR con PEDIDO_EN_REVISION — VERDE | ESCALAR | — |
| 26 scan_*.pdf | VERDE (26 scans: {'ESCALAR': 26}; confianzas sospechosas (>0.8): 0; 5 peores: scan_001.pdf (0.0), scan_002.pdf (0.0), scan_003.pdf (0.0), scan_004.pdf (0.0), scan_005.pdf (0.0)) | ESCALAR con lectura dudosa | — |
| 108 NO_PAGAR por código | VERDE: sin código dominante (>60) — ORDER_AMOUNT_MATCHES=14, IBAN_MATCHES_MASTER=7, IVA_CONSISTENT=6, TOTALS_MUST_MATCH=3, NO_DOUBLE_PAYMENT=2, ORDER_BELONGS_TO_SUPPLIER=1 | matching con datos correctos | — |

## Hallazgo principal — colapso de candidatos en el motor (ROJO)

El parser conserva TODOS los candidatos de `total` (doctrina §2). En las
facturas con línea «Subtotal» + «TOTAL A PAGAR», ambos aparecen como
candidatos (p.ej. 2026-01-26_P007.pdf: [1409.4, 1705.37]). El motor colapsa
values[] con el PRIMER candidato (el Subtotal) y lo compara contra el
importe CON IVA del maestro ⇒ ORDER_AMOUNT_MATCHES:FAIL +
TOTALS_MUST_MATCH:FAIL espurios. Medido: **0 de los 22
NO_PAGAR son falsos** (un candidato de total sí matchea el maestro con
tolerancia 0,01 entre los 0 con ORDER_AMOUNT_MATCHES
no-PASS); **0 son genuinos** (ningún candidato matchea —
importe realmente distinto del pedido).

Causa raíz: selección del escalar en el colapso de `ExtractionField.values[]`
(AGENTS.md §2: «collapse only at the moment a rule needs a scalar, and record
which candidate was chosen and why» — el registro del porqué no se está
haciendo y la elección ignora el desacuerdo entre candidatos).
Es un bug de MATCHING/selección, no de extracción (los candidatos correctos
están en el store) ni de política (NO_PAGAR definitivo solo si NINGÚN
candidato matchea; con desacuerdo entre candidatos ⇒ ESCALAR por §6).

Impacto si se corrige y reprocesa: los 94 pasarían a PAGAR (si el resto de
reglas PASA) o a ESCALAR; el outcomes real cambiaría — decisión del
supervisor antes de la validación binaria. La corrección toca el colapso
(T3/W2): preferir el candidato de la línea «TOTAL A PAGAR» / tratar el
desacuerdo entre candidatos como ambigüedad (ESCALAR), nunca tomar el
primero sin registrar el porqué.

## Notas

- Pedidos PO-2026-0538…0557 (NIF vacío en maestro): NINGUNA factura del lote 1 los cita — sin muestras; riesgo para el lote 2 (NIF faltante ⇒ NIF_IN_MASTER debe UNKNOWN ⇒ ESCALAR).
- Rung 4 sobre scans: 20 invocaciones, todas below-threshold; ninguna lectura VLM local alcanzó confianza alta — coherente con la política (las 26 scans ⇒ ESCALAR).
