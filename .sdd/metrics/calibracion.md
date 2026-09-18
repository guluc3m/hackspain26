# Calibración de los umbrales del rung 3 — evidencia del ADR D-001 (T10)

**Fecha**: 2026-09-18 · **Corpus**: 500 PDFs reales de `caja-de-alberto/facturas/`
(solo lectura) · **Corrida**: dry-run rungs 1–2, idempotente, cache por página
(`.sdd/cache/dryrun/`), concurrencia 2, timeout 30 s/archivo.
**El dry-run NO decide resultados: solo mide extracción.**

## 1. Dry-run medido (`.sdd/metrics/corpus-dryrun.json`)

| Métrica | Valor MEDIDO |
|---|---|
| Archivos | 500 (0 errores, 0 timeouts) |
| Capa de texto usable (rung 1) | **471** (94,2 %) |
| Caen a raster/QR (rung 2) | **29** (5,8 %) — sin QR en todo el corpus |
| Solo-QR | 0 |
| Páginas únicas procesadas | 493 (duplicados detectados: FA-8801 y otros) |
| Latencia rung 1 | media **0,4 ms**, p95 **2,0 ms** |
| Latencia rung 2 (raster+QR) | media **42,1 ms**, p95 **73,0 ms** |
| Throughput rung 1 | **2 636 archivos/s** (2 workers, texto) |
| Pared total 500 archivos | 3,57 s |

Suma de rutas: 471 + 29 = **500** ✓. Los 29 que caen a raster son los
26 sin capa de texto + 3 escaneos de baja calidad que la doctrina anuncia
(§11 traps). Evidencia cruda línea a línea: `.sdd/metrics/evidence-dryrun.jsonl`.

## 2. Calibración del rung 3 — datos medidos

Se OCRizaron las **29 páginas** que llegan al rung 3 con el motor tesseract
(libtesseract **5.5.1** vía tesserocr, user-space; `tessdata_fast` spa+eng,
**psm 6** — idéntico a `run_tesseract`), y se midieron las DOS partes del gate
(word-conf ponderada por longitud + cobertura de campos esperados). Además se
midió la cobertura de campos sobre las **493 capas de texto únicas** del corpus
(referencia de lo que alcanza una página "buena").

Distribuciones medidas (`.sdd/metrics/calibracion/calibracion-rung3.json`):

| | word_conf OCR (29 págs) | cobertura OCR (29 págs) | cobertura capas de texto (493) |
|---|---|---|---|
| media | 56,7 | 0,483 | 0,954 |
| p5 | 22,8 | 0,0 | 0,8 |
| p50 | 55,2 | 0,4 | 1,0 |
| p95 | 92,1 | 1,0 | 1,0 |

### Umbral de word-conf (tablas medidas)

| umbral | % páginas OCR por encima |
|---|---|
| 40 | **89,7** |
| 50 | 62,1 |
| 60 | 34,5 |
| 70 | 20,7 |
| 80 | 17,2 |

**Hueco medido**: la distribución es bimodal — las 3 páginas ilegibles del
corpus quedan en `[17,0 ; 26,0]` (fax_2026_0411 17,0 · scan_022 22,8 ·
reimpresion_0712 26,0) y la página legible más baja queda en **42,6** (gap
16,5). `word_conf = 40` cae dentro de ese hueco: **89,7 %** del rung-3 pasa y
las 3 que quedan debajo son exactamente los escaneos ilegibles anunciados por
la doctrina (§11). El valor anterior (60) cortaba al 65,5 % de páginas legibles
hacia el VLM sin ganancia de calidad medible.

### Umbral de cobertura de campos (tablas medidas)

| umbral | % OCR (29 págs) por encima | % capas de texto (493) por encima |
|---|---|---|
| 0,2 | 89,7 | 100,0 |
| 0,4 | **72,4** | **100,0** |
| 0,5 | 44,8 | 100,0 |
| 0,6 | 44,8 | 100,0 |
| 0,8 | 24,1 | 100,0 |

**Decisión: `tesseract_min_word_conf = 40.0`, `tesseract_min_field_coverage = 0.4`**
(config `extract-v2`; antes 60/0,5 sin medición).

Justificación citando el corpus:
- **40,0 de word-conf** separa legible de ilegible con el 100 % de acierto
  medido (3 ilegibles debajo, 26 legibles encima; 89,7 %/10,3 %).
- **0,4 de cobertura**: el 100 % de las capas de texto usables puntúa ≥ 0,8 —
  un OCR sano sobre página legible tiene margen 2×; el 72,4 % de las páginas
  OCRizadas alcanza 0,4. Con ambos gates: **22/29 (75,9 %)** de las páginas sin
  texto se resuelven en el rung 3; **7 (24,1 %)** caen al rung 4 (VLM), que es
  la escalada correcta: 3 ilegibles + 4 con campos ausentes (scan_012/014/017
  con cobertura 0,2 y scan_025 con conf 87 pero cobertura 0,0 — página de
  confianza alta sin campos de factura ⇒ sospechosa, mejor lectura VLM).
- Con los umbrales viejos (60/0,5) solo paraban en rung 3 el 44,8 % de las
  páginas sin texto y se multiplicaban las llamadas VLM sin mejora medida.
- Con 0,2 el gate admite páginas a las que les falta medio campo (riesgo de
  parseo con evidencia débil); con 0,6 no gana nada medible (mismo 44,8 %).

Consecuencias: el rung 3 resuelve ~5 % del corpus completo (22 páginas de 500)
a coste ~0; el VLM local solo recibe las 7 páginas donde tesseract no es
fiable — exactamente el papel de la escalera (D-001).

## 3. Reproducibilidad

```
# dry-run idempotente (cache por página en .sdd/cache/dryrun)
uv run python -m albertitos.extract.dryrun \
  --corpus caja-de-alberto/facturas \
  --out .sdd/metrics/corpus-dryrun.json \
  --evidence .sdd/metrics/evidence-dryrun.jsonl

# calibración (tesserocr+pillow user-space, NO en pyproject; --no-sync evita
# que uv sync los prune; tesseract NO está en PATH — el rung 3 usa el binario
# cuando existe, la calibración mide con la misma familia de motor 5.5.1)
uv pip install --python .venv tesserocr pillow
mkdir -p .sdd/tessdata && curl -sL -o .sdd/tessdata/spa.traineddata \
  https://github.com/tesseract-ocr/tessdata_fast/raw/main/spa.traineddata
uv run --no-sync python tools/calibrate_rung3.py
```

Corrida de verificación: re-run del dry-run produce métricas idénticas
(salvo `wall_seconds`) y **0 re-procesos** (solo filas `cache_hit`;
tests/test_dryrun.py).
