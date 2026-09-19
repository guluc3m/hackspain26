# Triage de la cola de revisión — lote 1 (T14)

## ESCALAR por motivo dominante (decisión del motor de reglas, ledger)

| motivo | nº | archivos |
|---|---|---|
| mixto | 34 | 2026-07-01_P009.pdf, F26-9007_catering.pdf, FA-2508_consultoría.pdf, copia_2026_0518.pdf, factura_4485.pdf, factura_7265.pdf, fax_2026_0411.pdf, reimpresion_0712.pdf, scan_001.pdf, scan_002.pdf, scan_003.pdf, scan_004.pdf, scan_005.pdf, scan_006.pdf, scan_007.pdf, scan_008.pdf, scan_009.pdf, scan_010.pdf, scan_011.pdf, scan_012.pdf, scan_013.pdf, scan_014.pdf, scan_015.pdf, scan_016.pdf, scan_017.pdf, scan_018.pdf, scan_021.pdf, scan_022.pdf, scan_023.pdf, scan_025.pdf, scan_026.pdf, scan_027.pdf, scan_028.pdf, scan_029.pdf |
| NO_EMBEDDED_INSTRUCTIONS:UNKNOWN | 5 | 2026-06-04_P006.pdf, 2026-07-09_P010.pdf, F26-2201_transportes.pdf, F26-7728_limpiezas2.pdf, factura_5911.pdf |
| DATE_VALID_NOT_FUTURE:UNKNOWN | 3 | 2026-03-19_P008.pdf, FA-1123_construcciones.pdf, FA-2967_seguridad.pdf |
| PEDIDO_EN_REVISION:UNKNOWN | 2 | 2026-79712_limpiezas.pdf, FA-8488_transportes.pdf |
| IBAN_MATCHES_MASTER:UNKNOWN | 1 | F26-3011_suministros.pdf |

## Cola de extracción (`.sdd/review-queue/review.jsonl`) — páginas escaladas

Estas 10 páginas llegaron al rung 5 (escala de extracción); sin lectura
cloud fiable (5× status-404 del proveedor, 5 sin credenciales inyectadas).
Lecturas candidatas lado a lado + imagen en el review.jsonl (esquema UI W3).

| motivo | nº | archivos |
|---|---|---|
| cloud-failed:status-404 | 24 | copia_2026_0518.pdf, fax_2026_0411.pdf, reimpresion_0712.pdf, scan_001.pdf, scan_002.pdf, scan_008.pdf, scan_009.pdf, scan_010.pdf, scan_011.pdf, scan_012.pdf, scan_013.pdf, scan_014.pdf, scan_015.pdf, scan_016.pdf, scan_017.pdf, scan_018.pdf, scan_021.pdf, scan_022.pdf, scan_023.pdf, scan_025.pdf, scan_026.pdf, scan_027.pdf, scan_028.pdf, scan_029.pdf |
| skipped:cloud-vlm-not-configured | 5 | scan_003.pdf, scan_004.pdf, scan_005.pdf, scan_006.pdf, scan_007.pdf |

## Nota

Las 10 páginas de extracción están DENTRO de los 45 ESCALAR (la escalada
de extracción nunca decide: el motor emite UNKNOWN y el resultado final
es ESCALAR). El desglose de la primera tabla es el completo; la cola
Revisión de la UI muestra los 45 (deriva de las decisiones con resultado
ESCALAR, ui/ledger.py revision_queue) y el review.jsonl aporta imagen +
candidatas lado a lado para las 10 que llegaron al rung 5.
NO se han decidido resultados aquí: el humano decide (AGENTS.md §6/§7);
los overrides alimentan SOLO la extracción y la decisión se recalcula.

Hallazgo para seguimiento (no bloqueante): RUNNER_TIMEOUT es el motivo
dominante (20/45) — timeout de 20 s/archivo con rung 4 serializado en una
máquina en carga. Material para el informe y para re-procesado tras
revisión (el cache hace que re-ejecutar sea barato).
