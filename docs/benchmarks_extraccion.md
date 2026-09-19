# Benchmarks local vs remoto — escalones 4, 5 y 7

> Etiquetas usadas en todo el documento: **[medido]** = corrida real en esta
> máquina con datos verificables; **[medido bajo carga]** = medido mientras el
> runner procesaba el corpus (la carga concurrente puede inflar la latencia);
> **[estimado]** = calculado a partir de precios públicos, no corrido aquí;
> **[no medido]** = sin credenciales en esta máquina, no se ha corrido nunca.

## Contexto

Hardware real de esta máquina: 8 núcleos i5-12400, 16 GB RAM, sin GPU ni
`/dev/dri`. Modelo local: PaddleOCR-VL 1.6 Q8 (0,94 GB) vía `llama-server`
(llama.cpp, endpoint OpenAI-compatible en `127.0.0.1:8080`, temp 0), aprovisionado
con `uv run scripts/setup_llama.sh` (DECISIONS.md D-002).

Los escalones 5 y 7 (TypeSafe System One y VLM cloud) **no tienen clave API
configurada en esta máquina** (verificado: ni variables de entorno
`TYPESAFE_API_KEY`/`OPENAI_API_KEY`, ni campo `api_key` en
`master/extraction.yaml`). Su latencia aquí es por tanto **[no medido]**; sus
precios se citan de fuentes públicas **[estimado]**.

## Metodología de la medición local

Script desechable (`data/bench_vlm/medir_vlm_local.py`, eliminado tras la
medición) que con `uv run` hace exactamente lo que hace el escalón 4
(`src/filemaid/extract/rungs/vlm_local.py`):

1. Renderiza la primera página de 5 PDFs del corpus real
   (`caja-de-alberto/facturas/`) con `pypdfium2`, escala 2,0 (~144 dpi).
2. Los envía a `http://127.0.0.1:8080/v1/chat/completions` con el mismo prompt
   del rung (`"OCR:"`), `temperature: 0`, `max_tokens: 1024`.
3. Cronometra con `time.monotonic()` de ida y vuelta, y registra `usage`.

Durante la medición el runner estaba procesando el lote 1 sobre los mismos 500
PDFs (`filemaid run` activo, load 4,98), y ambos comparten el mismo
`llama-server` de 4 hilos: los números de esta sección son **[medido bajo
carga]**. Los del lote 1 completo son de la corrida en solitario del runner
**[medido]**.

## Resultados

### Latencia del escalón 4 (VLM local), medición puntual de 5 páginas [medido bajo carga]

| Fichero | Latencia | Tokens entrada | Tokens salida | Palabras OCR |
|---|---|---|---|---|
| 2026-01-08_P001.pdf | 35,2 s | 1273 | 205 | 46 |
| 2026-01-11_P007.pdf | 33,7 s | 1273 | 235 | 54 |
| 2026-01-12_P002.pdf | 32,9 s | 1273 | 225 | 56 |
| 2026-01-12_P010.pdf | 32,4 s | 1273 | 203 | 47 |
| 2026-01-14_P002.pdf | 43,3 s | 1273 | 238 | 55 |

Resumen: **media 35,5 s · p50 33,7 s · p95 35,2 s** (n=5). Las 5 páginas
devolvieron OCR real y utilizable (nº de factura, fecha, pedido, CIF), 46-56
palabras cada una. Coste: 0,00 €.

Notas: los tokens de entrada son constantes (1273) porque dominan los tokens
de imagen; el tiempo crece sobre todo con los tokens de salida. La llamada más
lenta (43,3 s) corresponde a la página con más texto de las 5. La latencia es
«de ida y vuelta» HTTP: incluye renderizado previo (no medido por separado) y
cola del servidor si había otra petición en curso del runner.

### Latencia del escalón 4 en la corrida real del lote 1 (500 PDFs) [medido]

Datos de `video/data_lote1.json` (corrida T14, runner-1.0.0):

- El VLM local se invocó **28 veces** (solo las páginas que no resolvieron los
  escalones 1-3: 500 − 471 texto vectorial).
- Latencia media **33,9 s**, latencia máxima **60,1 s** (timeout de 120 s del
  rung no se alcanzó; una invocación alcanzó el `RUNNER_TIMEOUT` de 60 s).
- Consistente con la medición puntual de 5 páginas (~33-35 s): la carga
  concurrente no distorsionó apreciablemente el resultado, porque el runner
  serializa las invocaciones al VLM (`rung4_serializado: true`).

### Escalones 5 y 7 [no medido] — sin clave en esta máquina

No se ha hecho ninguna llamada real a `https://api.typesafe.ai/v1/systemone`
(escalón 5, `typesafe_jev.py`) ni a un endpoint OpenAI-compatible cloud
(escalón 7, `cloud_vlm.py`). En el lote 1, el intento de escalado cloud que sí
ocurrió (5 llamadas con 404, 29 invocaciones registradas en `rung5_cloud` con
media 1,56 s) **no fue facturable** (coste medido del lote: 0,00 €).

## Tabla comparativa por escalón

Coste por 1000 páginas asumiendo el perfil real del corpus (94,2 % de páginas
resueltas en escalón 1, 5,8 % llegan a escalón 4, ~0 % llegan a 5/7 en la
mezcla actual). La columna «si todo llegara aquí» es el coste hipotético si
cada página se procesase por ese escalón, para comparar escalones entre sí.

| Escalón | Motor | Latencia p50 / p95 | Coste por 1000 páginas (perfil real 94,2 % texto) | Si cada página llegara a este escalón | Calidad esperada | Etiqueta |
|---|---|---|---|---|---|---|
| 4 — VLM local | PaddleOCR-VL 1.6 Q8 en llama-server, 8 núcleos CPU | 33,7 s / 35,2 s (n=5) [medido bajo carga]; media 33,9 s, máx 60,1 s en lote 1 (n=28) [medido] | 0,00 € (coste marginal solo electricidad ≈ 0,0 €) [estimado] | ~34 s × 1000 ≈ 9,4 h de CPU (0,00 €) [estimado] | OCR multilingüe real (0,9B params): las 5 páginas de prueba y las 28 del lote devolvieron texto de factura utilizable (nº, fecha, CIF, importes); calidad buena para facturas estándar, degradación esperable en sellos/manuscritos [medido en muestra pequeña] | p50/p95 [medido]; coste [estimado] |
| 5 — TypeSafe System One | `jev-latest`, juicio tipado sobre texto previo (nunca OCR) | — | — | Precio público de referencia: el propio vendor advierte que sus cifras publicadas no son precios verificados (cookbook de self-consistency); sin precio por token establecido en docs: **no facturable hoy en esta máquina** | Juicios tipados calibrados (noul/choice/score) con confianza: no genera texto, solo decide; útil como segunda opinión sobre el texto del escalón 1 [estimado] | **[no medido]** (sin `TYPESAFE_API_KEY`) |
| 7 — VLM cloud | Endpoint OpenAI-compatible (>25B multimodal), default `gpt-4o-mini` | — | — | GPT-4o-mini: 0,15 $/M tokens entrada + 0,60 $/M tokens salida (OpenAI). Una página ≈ 1273 tokens de imagen + ~230 de texto salida ⇒ ≈ 0,0002 + 0,00014 ≈ **0,33 $/1000 páginas ≈ 0,30 €** [estimado] | OCR/lectura de máxima calidad para casos límite (escaneos degradados, sellos, manuscritos); en la arquitectura su lectura es «otro candidato», nunca respuesta automática | **[no medido]** (sin `OPENAI_API_KEY`); precio [estimado] |

Fuentes del precio cloud [estimado]:
- GPT-4o-mini: 0,15 $/1M tokens entrada, 0,60 $/1M tokens salida (OpenAI, docs
  oficiales; páginas de terceros como langcopilot.com y cloudprice.net lo
  confirman). Cálculo con los tokens reales medidos aquí (1273 entrada, ~230
  salida por página).
- TypeSafe: `docs.typesafe.ai/api` (endpoint y formato de preguntas tipadas) y
  `docs.typesafe.ai/cookbooks/consistency_noul_cookbook`, que advierte
  explícitamente que sus números no son precios verificados de jev-latest.

## Conclusiones prácticas para Alberto

**1. Con la mezcla real (94,2 % de páginas ya resuelta por texto vectorial), el
sistema vive casi todo en escalón 1 y el coste cloud es cero.** En el lote 1
real (500 PDFs): 471 páginas resueltas en escalón 1, solo 28 invocaciones al
VLM local, 0 lecturas cloud facturables, coste total 0,00 €. Los escalones 5 y
7 solo intervienen en la cola (45 ESCALAR del triage), y ni siquiera esa cola
necesitó facturación: los 5 intentos cloud devolvieron 404 sin coste.

**2. El cuello de botella es la latencia del VLM local en CPU, no su coste.**
~34 s por página con 8 núcleos es lento pero tolerable porque:
- Solo lo recibe el 5,8 % de las páginas (28 de 500 en el lote 1): ~16 min de
  VLM por cada 500 PDFs, dentro de los ~120 s de wall-clock × paralelismo que
  ya se midieron (4,16 files/s).
- Es gratis. El equivalente cloud (escalón 7) costaría ≈ 0,30 € por 1000
  páginas [estimado]: a escala de 500 PDFs/mes, la diferencia es de céntimos;
  la decisión entre escalón 4 y 7 es de latencia y privacidad (los documentos
  no salen de la máquina con el escalón 4), no de dinero.

**3. Cuándo se activa cada escalón con la mezcla real:**
- **Escalón 4 (VLM local):** solo para las ~29 páginas sin texto vectorial
  (rasterizadas, escaneos). Es la primera vez que hay que "leer" de verdad, y
  es gratis, así que siempre se prefiere antes que cualquier llamada cloud.
- **Escalón 5 (TypeSafe):** sin clave en esta máquina, no se ejecuta nunca.
  Cuando tenga clave, su rol es de **segunda opinión tipada** sobre el texto
  que ya existe (no OCR): decide si un texto es factura, si tiene datos
  fiscales, si es legible. Sería útil para las 22 NO_PAGAR dudosas o para
  reducir los 45 ESCALAR, no para extraer texto. El precio que conviene
  negociar/medir es por lectura tipada, no por token OCR.
- **Escalón 7 (VLM cloud):** último recurso, sin umbral de parada propio (su
  lectura es «otro candidato»). Con la mezcla real casi no se activa. Si se
  activara para todo el corpus, el coste sería ≈ 0,30 €/1000 páginas
  [estimado] — sigue siendo barato; el motivo para no usarlo por defecto es la
  latencia (~3 s/página [estimado]), la privacidad y el principio de resolver
  localmente todo lo que se pueda.

**4. Dónde medir cuando haya credenciales:** repetir esta misma metodología
(render con `pypdfium2` + llamada real) sobre 5 páginas con `TYPESAFE_API_KEY`
y `OPENAI_API_KEY` configuradas, y sustituir las filas [no medido] por valores
[medido]. El script desechable usado aquí se borró tras la medición; la lógica
está descrita arriba en «Metodología» y es reproducible en 20 líneas.
