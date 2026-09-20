# Guion — Vídeo Remotion 3 min · filemaid · 500 Sombras de Alberto

30 fps · 1920×1080 · paleta y fuentes de docs/report/lib.typ (papel crema #f4ecd8, tinta #2a170f, oro #eab619, naranja #d96b2a, teal #35858a, rojo #cc291f; Bungee + DM Sans). Estética documental, sin gradientes.

## Estructura (5400 frames, 8 escenas)

| # | Escena | Seg | Frames | Contenido |
|---|--------|-----|--------|-----------|
| 1 | Portada | 0:00–0:12 | 0–360 | FILEMAID · «De 500 facturas a una decisión». Chips FACTURA/DECISIÓN/TRAZA. |
| 2 | El problema de Alberto | 0:12–0:35 | 360–1050 | 500 PDFs + Excel maestro + ERP 2009; decidir PAGAR/NO_PAGAR/ESCALAR; «ante duda razonable, escalar antes que pagar». |
| 3 | Cómo lo usamos | 0:35–0:55 | 1050–1650 | Producto: app de escritorio pywebview + UI (Dashboard→Ingesta→Revisión→Logs), watcher con notificación al ESCALAR, cero clics en el flujo nocturno. |
| 4 | Escalera de extracción | 0:55–1:25 | 1650–2550 | 7 escalones por página (pypdf → QR → Tesseract → VLM local → TypeSafe → Firecrawl → cloud VLM), degrada con calma; datos MEDIDOS del dry-run (94,2 % texto, rung1 2 636 files/s). |
| 5 | Trazabilidad: una decisión real | 1:25–2:00 | 2550–3600 | Casos reales de data_outcomes_lote1.jsonl: factura_8801.pdf (duplicado de FA-8801) → NO_DOUBLE_PAYMENT:FAIL ⇒ NO_PAGAR; scan_001.pdf → 7 UNKNOWN de las 8 reglas del motor ⇒ ESCALAR; 2026-03-19_P008.pdf → DATE_VALID_NOT_FUTURE:UNKNOWN ⇒ ESCALAR. Evidence: SHA256, extractor, versión, config_version, latencia. |
| 6 | Arquitectura y ADRs | 2:00–2:20 | 3600–4200 | Motor puro y determinista (snapshot de reglas + umbrales); 8 ADRs destacando ADR-06 (candidatos con provenance: 86 falsos NO_PAGAR corregidos en el reproceso de 108, 0 regresiones) y ADR-08 (resultado configurable por regla: FAIL → NO_PAGAR/ESCALAR). |
| 7 | Resiliencia y recuperación | 2:20–2:40 | 4200–4800 | DRILLS medidos (data_drills.json): provider-caído PASS, backoff-429 PASS (3 llamadas exactas), crash-reanudación PASS (0 duplicados), ledger-corrupto PASS. Idempotencia por SHA256+versión: 0 duplicados. |
| 8 | Escala, coste y límites | 2:40–3:00 | 4800–5400 | Fórmula: 94,2 % × ~0 ms + 5,8 % × ~34 s (VLM local). Lote 1 real: 500 en 120,1 s ≈ 4,162 files/s, 0,00 € cloud medido. Plan de volumen. |

## Reglas (el motor REAL: 8 códigos, src/filemaid/rules/rules.py RULE_CODES)

1. `DATE_VALID_NOT_FUTURE` — fecha válida y no futura.
2. `IBAN_MATCHES_MASTER` — el IBAN de la factura está en el maestro.
3. `IVA_CONSISTENT` — base + IVA = total (tolerancia 0,01 €).
4. `NIF_IN_MASTER` — el NIF del proveedor está en el maestro.
5. `NO_DOUBLE_PAYMENT` — el documento no es un duplicado ya pagado.
6. `ORDER_BELONGS_TO_SUPPLIER` — el pedido existe, pertenece al proveedor y **el importe de la factura cuadra con el importe del pedido** (tolerancia 0,01 €; el cruce de importe vive dentro de esta regla, rules.py:94–146).
7. `ORDER_PENDING` — el pedido está pendiente de pago (no ya servido/cerrado).
8. `TOTALS_MUST_MATCH` — los totales declarados cuadran con la suma de líneas.

FAIL ⇒ NO_PAGAR · UNKNOWN ⇒ ESCALAR. No existen otros códigos (p. ej. ORDER_AMOUNT_MATCHES, NO_EMBEDDED_INSTRUCTIONS o PROVEEDOR_FANTASMA no están en el motor actual).

## Reglas visuales
- Sin gradientes; esquinas rectas (radius 0–2px); bordes 1–2px tinta.
- StatusBadge: PAGAR=teal, NO_PAGAR=rojo, ESCALAR=naranja.
- Datos reales del repo: data_lote1.json, data_drills.json, data_dryrun.json, data_impacto.json, data_outcomes_lote1.jsonl (video/).
- Texto mínimo por frame; máx 5 bullets visibles a la vez.
- Duración final 180 s exactos, 5400 frames.
