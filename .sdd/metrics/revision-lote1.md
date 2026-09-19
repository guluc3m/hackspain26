# Cola de revisión — lote 1 (ESCALAR) — SOLO documentada, el humano decide

El pipeline NUNCA decide los ESCALAR: los 45 quedan en `.sdd/review-queue/` con la
imagen de página y todas las lecturas candidatas (texto, VLM local PaddleOCR-VL, deepseek cloud) lado a lado con provenance.

Total: 45 · Distribución de motivos (dominante = códigos UNKNOWN):

- extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola: **29**
- NO_EMBEDDED_INSTRUCTIONS: **6**
- DATE_VALID_NOT_FUTURE: **3**
- PEDIDO_EN_REVISION: **2**
- IBAN_MATCHES_MASTER,ORDER_AMOUNT_MATCHES,ORDER_PENDING,NO_EMBEDDED_INSTRUCTIONS,PROVEEDOR_FANTASMA: **2**
- NO_EMBEDDED_INSTRUCTIONS,AMOUNT_OUTLIER: **1**
- IBAN_MATCHES_MASTER: **1**
- IBAN_MATCHES_MASTER,ORDER_AMOUNT_MATCHES,ORDER_PENDING,PROVEEDOR_FANTASMA: **1**

| file_id | motivo dominante (códigos de regla UNKNOWN) |
|---|---|
| 2026-03-19_P008.pdf | DATE_VALID_NOT_FUTURE |
| 2026-06-04_P006.pdf | NO_EMBEDDED_INSTRUCTIONS |
| 2026-07-01_P009.pdf | NO_EMBEDDED_INSTRUCTIONS,AMOUNT_OUTLIER |
| 2026-07-09_P010.pdf | NO_EMBEDDED_INSTRUCTIONS |
| 2026-79712_limpiezas.pdf | PEDIDO_EN_REVISION |
| F26-2201_transportes.pdf | NO_EMBEDDED_INSTRUCTIONS |
| F26-3011_suministros.pdf | IBAN_MATCHES_MASTER |
| F26-7728_limpiezas2.pdf | NO_EMBEDDED_INSTRUCTIONS |
| F26-9007_catering.pdf | NO_EMBEDDED_INSTRUCTIONS |
| FA-1123_construcciones.pdf | DATE_VALID_NOT_FUTURE |
| FA-2508_consultoría.pdf | IBAN_MATCHES_MASTER,ORDER_AMOUNT_MATCHES,ORDER_PENDING,PROVEEDOR_FANTASMA |
| FA-2967_seguridad.pdf | DATE_VALID_NOT_FUTURE |
| FA-8488_transportes.pdf | PEDIDO_EN_REVISION |
| copia_2026_0518.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| factura_4485.pdf | IBAN_MATCHES_MASTER,ORDER_AMOUNT_MATCHES,ORDER_PENDING,NO_EMBEDDED_INSTRUCTIONS,PROVEEDOR_FANTASMA |
| factura_5911.pdf | NO_EMBEDDED_INSTRUCTIONS |
| factura_7265.pdf | IBAN_MATCHES_MASTER,ORDER_AMOUNT_MATCHES,ORDER_PENDING,NO_EMBEDDED_INSTRUCTIONS,PROVEEDOR_FANTASMA |
| fax_2026_0411.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| reimpresion_0712.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_001.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_002.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_003.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_004.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_005.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_006.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_007.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_008.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_009.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_010.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_011.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_012.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_013.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_014.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_015.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_016.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_017.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_018.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_021.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_022.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_023.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_025.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_026.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_027.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_028.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
| scan_029.pdf | extracción sin resolver (29): sin capa de texto, la batería queda UNKNOWN — lectura VLM/deepseek como candidatas en cola |
