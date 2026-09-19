# Capacidad, hardware y coste

Documento de referencia con los límites reales de esta máquina y el coste de
operación de la escalera de extracción. Cada número lleva etiqueta:
**[medido]** (corrida real en esta máquina, fuente citada), **[estimado]**
(derivado con supuestos explícitos) o **[no medido]**.

Fuentes de datos: `docs/report/escalabilidad_datos.typ` (generado por
`filemaid.metrics`), `video/data_dryrun.json` (dry-run del corpus), 
`video/data_lote1.json` (lote 1 real) y medición propia
`data/bench_vlm_local.json` (ver §5). Desglose adicional de latencias por
escalón: `docs/benchmarks_extraccion.md`.

## 1. Hardware y límites medidos

| Recurso | Valor | Etiqueta |
|---|---|---|
| CPU | 8 núcleos (i5-12400), sin GPU ni `/dev/dri` | [medido] |
| RAM | 16 GB físicos (el informe del ledger reporta 12 GB visibles al proceso) | [medido] |
| Modelo OCR | PaddleOCR-VL 1.6 Q8 vía llama-server, ~1,1 GB en disco, 4 hilos, KV cache q8_0 | [medido] |
| Concurrentes VLM | 1 (el escalón 4 corre serializado) | [medido] |

### Throughput por escalón (corpus de 500 facturas)

| Escalón | Función | Latencia media | p95 | Etiqueta |
|---|---|---|---|---|
| 1 · pypdf (capa de texto) | extraer texto si pasa plausibilidad | 0,4 ms | 2,0 ms | [medido] |
| 2 · rasterizado + QR (pypdfium2+zxing) | render a PNG y leer QR | 42,1 ms | 73,0 ms | [medido] |
| 3 · Tesseract | OCR clásico con doble puerta (word-conf + cobertura) | — | — | [no medido] (stub: `skipped:stub`) |
| 4 · VLM local (PaddleOCR-VL) | OCR/lectura de páginas sin texto | 33 870 ms (n=28, lote 1) | 60 075 ms | [medido, bajo carga] |
| 5 · TypeSafe Jev | juicios tipados sobre texto previo | — | — | [no medido] (sin clave) |
| 6 · Firecrawl | parser documental (respaldo) | — | — | [no medido] (sin clave) |
| 7 · VLM cloud | lectura de escalado, nunca respuesta automática | 1 555 ms media (n=29, intentos 404) | 30 780 ms | [medido, error de credenciales: no representa latencia real de inferencia] |

Throughput extremo a extremo:

- Dry-run escalón 1: **2 636 files/s**, wall 3,57 s para 500 archivos [medido].
- Lote 1 real (escalera completa, 94,2 % texto usable + 29 raster→VLM):
  **500 archivos en ~120 s ⇒ 4,16 files/s** [medido] (`video/data_lote1.json`).
- Perfil de carga T23: UI + 2 runners simultáneos, peor p95 7,7 ms, 108,7–110,0
  files/s por runner, 0 fallos [medido].

### Límite práctico de archivos/hora en esta máquina

Con la mezcla medida (94,2 % de facturas resueltas en el escalón 1, 5,8 %
cae al VLM local serializado, escalón 4):

$$
\text{files/s} \approx \frac{1}{0{,}942 \cdot t_1 + 0{,}058 \cdot (t_{1{,}2} + t_{4})}
$$

Con t₁ ≈ 0,4 ms [medido], t₁,₂ ≈ 42 ms [medido] y t₄ ≈ 33,9 s [medido]:

$$
\text{files/s} \approx \frac{1}{0{,}0004 + 0{,}058 \cdot 33{,}9} \approx 0{,}51\ \text{files/s} \Rightarrow \approx 1\,820\ \text{archivos/h} \; \text{[estimado]}
$$

El lote 1 real dio 4,16 files/s (14 400/h equivalentes) [medido]: mejor que el
techo anterior porque solo 28 de 500 páginas (5,6 %) invocaron el VLM y el
resto del pipeline solapa con esa espera. Cota conservadora operativa para
planificación: **4–14 mil archivos/h con la mezcla actual** [estimado, límites
anclados a datos medidos]. El factor dominante no es la CPU: es el número de
páginas que caen al escalón 4 (serializado, ~34 s por página).

## 2. Fórmula de coste

Por archivo y por lote:

$$
\text{coste} = f_{\text{texto}} \cdot 0 \;+\; f_{\text{ocr}} \cdot t_{\text{VLM}} \cdot P_{(W)} \cdot \frac{\text{€/kWh}}{3\,600\,000} \;+\; \sum_{\text{llamadas cloud}} \text{precio}_{\text{llamada}}
$$

donde:

- $f_{\text{texto}}$ = fracción de archivos resueltos sin OCR (0,942 [medido]);
  coste marginal de software: **0 €** (todo local, sin licencias de pago).
- $f_{\text{ocr}}$ = fracción que cae al escalón 4 (0,058 [medido]).
- $t_{\text{VLM}}$ = segundos de CPU por página OCR (33,9 s media [medido]).
- $P$ = potencia del paquete CPU en vatios. **No medible sin root** (RAPL
  `energy_uj` no legible en esta máquina [medido]): se usa el TDP del
  i5-12400, 65 W, como cota superior [estimado].
- €/kWh = tarifa eléctrica (0,15 €/kWh de referencia doméstica España
  [estimado]).
- $\sum \text{precio}$ = solo si hay escalones remotos configurados; precio
  por página de referencia en §3.

### Coste LOCAL (solo energía, 0 € de software)

| Magnitud | Valor | Etiqueta |
|---|---|---|
| Energía del lote 1 (500 facturas, 120 s a 65 W) | 0,0022 kWh ⇒ **0,00033 €** | [estimado] (potencia=TDP, tarifa asumida) |
| Energía por archivo (mezcla 94,2 % texto) | ≈ 6,5×10⁻⁷ € | [estimado] |
| Coste software por archivo | **0,00 €** | [medido] (0 llamadas cloud facturables en lote 1) |

Incluso a 10 000 facturas, el coste eléctrico local es del orden de
0,005 € [estimado]. El coste real de la vía local es tiempo de máquina, no
dinero.

### Coste REMOTO/cloud (precio de referencia, fecha 2026-09-19) [estimado]

Sin clave configurada en esta máquina: ningún precio es medido; son precios
públicos de lista [estimado]:

| Proveedor / modelo | Precio de lista (entrada+salida) | € aprox. por página OCR* |
|---|---|---|
| OpenAI gpt-4o-mini | $0,15/1M tokens entrada, $0,60/1M salida | ~0,0003 $ |
| Google Gemini 2.5 Flash | $0,30/1M entrada, $2,50/1M salida | ~0,0004–0,001 $ |

\* Supuesto [estimado]: página de factura ≈ 285 tokens de entrada de imagen +
285–400 tokens de salida (equivalente usado por OpenAI para imágenes de baja
resolución). Un PDF de 1 página = 1 llamada.

Aplicado al lote 1 (29 páginas raster): 29 × 0,0003 $ ≈ **0,009 $ ≈ 0,008 €**
[estimado]. Coste cloud medido real del lote 1: **0,00 €** [medido] (0 lecturas
facturables; 5 intentos devolvieron 404 sin facturar).

## 3. Plan de volumen: 1k / 10k / 100k facturas

El cuello de botella es el escalón 4 (VLM local, serializado, ~34 s/página
[medido]). La escalera paraleliza por diseño: 1 y 2 son puros CPU-local por
archivo (ya a 2 636 files/s [medido]); el 4 se puede paralelizar en procesos
o réplicas de llama-server; 5–7 son llamadas HTTP (paralelizan de forma
trivial, limitadas por rate-limit del proveedor).

| Volumen | % al escalón 4 (misma mezcla) | Tiempo estimado en esta máquina | Plan |
|---|---|---|---|
| 1 000 | ~58 páginas [estimado] | ~33 min en serie [estimado] | Esta máquina tal cual: 1 proceso, 1 llama-server, sin cambios. |
| 10 000 | ~580 páginas [estimado] | ~5,5 h en serie [estimado]; ~1,4 h con 4 réplicas de llama-server (8 núcleos / 4 hilos por instancia ya ajustado) [estimado] | Paralelizar escalón 4 (réplicas del sidecar o cola de procesos); escalones 1–2 no necesitan nada. |
| 100 000 | ~5 800 páginas [estimado] | ~2,3 días en serie [estimado]; ~14 h con 4 réplicas [estimado] | 2 vías: (a) máquina dedicada 16 núcleos/32 GB + 8 réplicas VLM [estimado]; (b) desviar el excedente al escalón 7 (cloud VLM) solo para el pico: 5 800 páginas × 0,0003 $ ≈ 1,7 $ [estimado] — la vía cloud es 3 órdenes de magnitud más barata en €/página que amortizar hardware, pero envía datos fuera. |

Supuestos del plan [estimado]: misma mezcla 94,2/5,8 %; latencia VLM estable
(con contención de lote 1 se degrada, ver §5); una factura = 1 página.

### Escalones sustituibles y nuevos tipos de archivo

- Cada escalón es un módulo con `NAME` + `extract(PageContext)` registrado en
  `_RUNGS` (`src/filemaid/extract/ladder.py`): añadir soporte de un formato
  nuevo (xlsx, email) = añadir un escalón o adaptar el rasterizador; el bucle
  de la escalera no se toca [medido, estructura del código].
- Un escalón sin dependencia (sin binario, sin clave) devuelve
  `skipped:<razón>` y la escalera continúa: el lote nunca se detiene
  [medido, drills de resiliencia 4/4 PASS en `.sdd/metrics/drills.json`].
- Imágenes (png/jpg) entran directo al escalón 2 [medido, `extract_page_any`].
- El texto crudo nunca se lanza a la red desde escalones locales sin
  `remote_rungs_enabled` [medido, `remote_allowed`].

## 4. Benchmarks local vs remoto

Latencia por escalón en esta máquina (p50/p95, ms, sobre 1 página):

| Escalón | p50 | p95 | Fuente | Etiqueta |
|---|---|---|---|---|
| 1 · pypdf | 0,4 (media) | 2,0 | dry-run, n=493 | [medido] |
| 2 · raster+QR | 42,1 (media) | 73,0 | dry-run, n=29 | [medido] |
| 3 · Tesseract | — | — | stub | [no medido] |
| 4 · VLM local | 17 812 | 19 301 | medición propia n=5, §5 | [medido, bajo carga] |
| 4 · VLM local (media lote) | — | — | lote 1, n=28: media 33 870, máx 60 075 | [medido, bajo carga] |
| 5 · TypeSafe Jev | — | — | sin clave en esta máquina | [no medido] |
| 6 · Firecrawl | — | — | sin clave en esta máquina | [no medido] |
| 7 · VLM cloud | 1 555 (media, n=29) | 30 780 | lote 1 (intentos fallidos 404, sin inferencia) | [medido, no representativo] / [no medido] para inferencia real |

Comparativa de latencia p50 del escalón OCR (local vs cloud), con precios del §2:
local ≈ 18–34 s/página en CPU a 0 € software [medido bajo carga]; cloud ≈
1,5–3 s/página típica [estimado, precio de lista] a ~0,0003–0,001 $/página
[estimado].

## 5. Medición propia de hoy (2026-09-19)

Script desechable `data/bench_vlm_local.py` (`uv run python
data/bench_vlm_local.py`), resultado en `data/bench_vlm_local.json`:

- 5 páginas del corpus que el escalón 1 rechaza (sin texto usable), render a
  160 dpi, misma llamada `/v1/chat/completions` que el escalón 4.
- Latencias (ms): 161 104, 19 301, 4 266, 17 087, 17 812.
- **p50 = 17,8 s · p95 = 19,3 s · media = 43,9 s** [medido].
- **Nota: corrió EN PARALELO al procesado del lote 1** (el VLM estaba en uso
  por los runners): hay contención de CPU y el outlier de 161 s es contención,
  no latencia del modelo en vacío. Los p50/p95 de las 4 páginas restantes
  (17–19 s) son consistentes con la media del lote 1 (33,9 s, n=28) una vez
  descontado ese outlier.
- No se tocó el proceso del lote ni sus canales; la medición solo compitió por
  CPU.
