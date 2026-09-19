# Vídeo filemaid — Remotion, 3 min (5400 frames @ 30 fps, 1920×1080)

## Renderizar

Desde `video/` (dependencias ya instaladas en `node_modules`):

```sh
npm run render        # = npx remotion render src/index.tsx filemaid out/filemaid.mp4
```

Salida: `video/out/filemaid.mp4` (180 s exactos).

Stills de verificación visual (uno por escena clave):

```sh
npx remotion still src/index.tsx filemaid out/still-portada.png --frame=100
npx remotion still src/index.tsx filemaid out/still-traza.png --frame=3000
npx remotion still src/index.tsx filemaid out/still-escalera.png --frame=2000
```

(El compositor se llama `filemaid` y el punto de entrada `src/index.tsx`.)

## Datos que usa

Todo lo que aparece en pantalla sale de ficheros medidos del repo; nada está inventado:

| Fichero | Qué aporta | Escena |
|---|---|---|
| `data_outcomes_lote1.jsonl` | Corrida real con rule_ids por file_id: `factura_8801.pdf` NO_PAGAR (NO_DOUBLE_PAYMENT), `scan_001.pdf` ESCALAR (7 UNKNOWN de las 8 reglas), `2026-03-19_P008.pdf` ESCALAR (DATE_VALID_NOT_FUTURE) | Traza (5) |
| `data_dryrun.json` | Dry-run del corpus: rung1 2 636 files/s, 0,4 ms mean; rung2 42,1 ms | Escalera (4) |
| `data_drills.json` | 4 drills PASS: provider-caído, backoff-429, crash-reanudación, ledger-corrupto | Resiliencia (7) |
| `data_impacto.json` | ADR-06: reproceso de 108 NO_PAGAR → 86 falsos corregidos, 0 regresiones | ADRs (6) |
| `data_lote1.json` | Lote 1 real: 500 archivos → 433 PAGAR / 22 NO_PAGAR / 45 ESCALAR; 4,162 files/s; 120,1 s; 0,00 € cloud; 471/500 (94,2 %) texto vectorial | Escala (8) |

Las 8 reglas mostradas son exactamente `RULE_CODES` de `src/filemaid/rules/rules.py`
(DATE_VALID_NOT_FUTURE, IBAN_MATCHES_MASTER, IVA_CONSISTENT, NIF_IN_MASTER,
NO_DOUBLE_PAYMENT, ORDER_BELONGS_TO_SUPPLIER, ORDER_PENDING, TOTALS_MUST_MATCH).
El cruce de importe factura↔pedido vive dentro de `ORDER_BELONGS_TO_SUPPLIER`
(rules.py:94–152). Detalle completo en `GUION.md`.
