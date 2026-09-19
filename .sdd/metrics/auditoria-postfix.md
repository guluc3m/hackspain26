# Auditoría POST-fix del lote 1 (T22) — motor runner-1.1.0, ADR-06

Outcomes: `.sdd/metrics/outcomes-lote1-post-fix.jsonl` — 433 PAGAR / 22 NO_PAGAR / 45 ESCALAR.

## 1. Trampas de T17 contra el outcomes regenerado

| trampa | obtenido | estado |
|---|---|---|
| 3 proveedores fantasma | obtenido ESCALAR×3; 3 facturas con el fantasma detectado por regla (IBAN ES6614910001213000098877); ninguna con resultado distinto de ESCALAR. | VERDE |
| Duplicado FA-8801 | VERDE (2026-05-28_P005.pdf=PAGAR; factura_8801.pdf=NO_PAGAR; el 2º no paga por NO_DOUBLE_PAYMENT) | — |
| Instrucciones embebidas | VERDE (9 facturas con instrucción embebida marcadas; 0 PAGAR) | — |
| Pedidos NIF vacío (0538–0557) | SIN MUESTRAS (0 facturas los citan en lote 1) | — |
| Outlier 84700 + pendiente_revisar | outlier 84700 (2026-07-01_P009.pdf, pedido PO-2026-0497): ESCALAR — VERDE; PO-2026-0007 (FA-8488_transportes.pdf): ESCALAR con PEDIDO_EN_REVISION — VERDE; PO-2026-0141 (2026-79712_limpiezas.pdf): ESCALAR con PEDIDO_EN_REVISION — VERDE | — |
| 26 scan_*.pdf | VERDE (26 scans: {'ESCALAR': 26}; confianzas sospechosas (>0.8): 0; 5 peores: scan_001.pdf (0.0), scan_002.pdf (0.0), scan_003.pdf (0.0), scan_004.pdf (0.0), scan_005.pdf (0.0)) | — |

## 2. Los 22 NO_PAGAR restantes (distribución por código FAIL)

| código FAIL | nº |
|---|---|
| ORDER_AMOUNT_MATCHES | 14 |
| IBAN_MATCHES_MASTER | 7 |
| IVA_CONSISTENT | 6 |
| TOTALS_MUST_MATCH | 3 |
| NO_DOUBLE_PAYMENT | 2 |
| ORDER_BELONGS_TO_SUPPLIER | 1 |

Genuinos del T17 que siguen NO_PAGAR (0 regresiones): **14/14**.

## 3. Provenance de los 86 nuevos PAGAR (muestra de 20, verificación total)

Verificados recomputando el veredicto con el motor determinista: 86/86 con ORDER_AMOUNT_MATCHES:PASS cuyo candidato citado matchea el maestro con tolerancia 0,01. Fallas: 0.

| archivo | candidato elegido | extractor | feature_ref | importe maestro | matchea ±0,01 |
|---|---|---|---|---|---|
| 2026-01-26_P007.pdf | 1705.37 | regex-total | pdf_text:1745ff0f865d53c5 | 1705.37 | True |
| 2026-01-30_P010.pdf | 3605.4 | regex-total | pdf_text:3f9a1eb4ed8d5346 | 3605.4 | True |
| 2026-02-05_P011.pdf | 1111.74 | regex-total | pdf_text:a3b6776465e18180 | 1111.74 | True |
| 2026-02-07_P002.pdf | 4763.93 | regex-total | pdf_text:04702e91fa4f7e56 | 4763.93 | True |
| 2026-02-07_P007.pdf | 2802.51 | regex-total | pdf_text:2c31e84b60400237 | 2802.51 | True |
| 2026-02-19_P005.pdf | 8332.24 | regex-total | pdf_text:6a3a5818162d6c6d | 8332.24 | True |
| 2026-02-23_P010.pdf | 8031.76 | regex-total | pdf_text:58bd1531d675c086 | 8031.76 | True |
| 2026-03-05_P004.pdf | 2077.03 | regex-total | pdf_text:4e77487a8935150d | 2077.03 | True |
| 2026-03-08_P004.pdf | 8751.43 | regex-total | pdf_text:36b60bbf4d8f7185 | 8751.43 | True |
| 2026-03-16_P011.pdf | 5152.75 | regex-total | pdf_text:f04e2ca4a19e97d4 | 5152.75 | True |
| 2026-03-17_P006.pdf | 365.09 | regex-total | pdf_text:592c289110170c57 | 365.09 | True |
| 2026-04-06_P002.pdf | 9454.83 | regex-total | pdf_text:1965c2794aa8c8e3 | 9454.83 | True |
| 2026-04-12_P005.pdf | 153.19 | regex-total | pdf_text:b5ab942b42cabce5 | 153.19 | True |
| 2026-04-15_P005.pdf | 6586.55 | regex-total | pdf_text:50c8d40ac5b85709 | 6586.55 | True |
| 2026-04-27_P010.pdf | 4507.37 | regex-total | pdf_text:e7fc3096f0d77010 | 4507.37 | True |
| 2026-04-30_P004.pdf | 550.31 | regex-total | pdf_text:e748abe0cc5d736e | 550.31 | True |
| 2026-04-30_P011.pdf | 9976.09 | regex-total | pdf_text:bdb873371ea80b20 | 9976.09 | True |
| 2026-05-04_P001.pdf | 8091.65 | regex-total | pdf_text:7c457f20900894c7 | 8091.65 | True |
| 2026-05-18_P011.pdf | 8963.7 | regex-total | pdf_text:95378e91f6d2fb7b | 8963.7 | True |
| 2026-05-21_P006.pdf | 1709.68 | regex-total | pdf_text:1b731125d0908b0a | 1709.68 | True |

## Veredicto: VERDE

El diff del subset va aparte en `.sdd/metrics/impacto-fix-colapso.json`
(schema de impacto ≠ schema de auditoría, no se mezclan).
