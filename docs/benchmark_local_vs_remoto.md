# Benchmark local vs remoto — latencia y coste por escalón (4, 5 y 7)

> Etiquetas usadas en todo el documento:
> **[medido hoy]** = corrida real en esta máquina, 2026-09-20, comando reproducible indicado;
> **[medido antes]** = corrida real previa, fuente citada (fecha de la corrida original entre paréntesis);
> **[estimado]** = calculado a partir de precios públicos u otra medición, nunca corrido tal cual.

## Contexto

- Corpus real: `caja-de-alberto/facturas/` (500 PDFs). Perfil medido en el
  dry-run (`video/data_dryrun.json`, 2026-09-20) [medido antes]: 471/500
  (94,2 %) resuelven en escalón 1 (texto vectorial), 29/500 (5,8 %) son
  escaneos sin texto plausible → candidatos a escalón 4; 0 llegan a QR-only.
- Hardware local (lscpu/free, 2026-09-20) [medido antes,
  `docs/benchmarks_extraccion.md`]: i5-12400 de 6 núcleos / 12 hilos con
  **8 hilos online** (CPUs 2-5 y 8-11; 0-1 y 6-7 offline), 16 GB RAM, sin GPU
  ni `/dev/dri`. Modelo escalón 4: PaddleOCR-VL 1.6 Q8 (0,94 GB) vía
  `llama-server` (llama.cpp, 4 hilos, contexto 8192, endpoint
  OpenAI-compatible en `127.0.0.1:8080`, temp 0), aprovisionado con
  `uv run scripts/setup_llama.sh` (DECISIONS.md D-002).
- Sin credenciales cloud en esta máquina (verificado hoy 2026-09-20: no hay
  `TYPESAFE_API_KEY`/`OPENAI_API_KEY`/`FIRECRAWL_API_KEY` en el entorno ni
  `api_key` en `master/*.yaml`) → escalones 5 y 7 solo **[estimado]** /
  **[medido antes]**.

## Metodología de la medición de hoy (escalón 4)

- Comando reproducible: `uv run python scripts/bench_vlm_local.py`
  (defaults: `--url http://127.0.0.1:8080 --serial 8 --concurrente 5
  --concurrencia 2 --salida .sdd/metrics/vlm-local-latencia.json`),
  ejecutado el 2026-09-20 a las ~06:14-06:28 CEST con el `llama-server` en
  reposo (sin carga del runner).
- Subconjunto: las 3 primeras páginas escaneadas del corpus (orden
  determinista del script) × 8-9 peticiones seriales + 5-6 concurrentes
  (n=13-15 peticiones por corrida, ≤10 páginas, dentro del límite).
  Imágenes: `copia_2026_0518.pdf`, `fax_2026_0411.pdf`, `reimpresion_0712.pdf`,
  renderizadas con `pypdfium2` escala 2,0 (~144 dpi), página 1, PNG
  (785/2773/1341 KiB).
- Contrato del rung: prompt `"OCR:"`, `temperature: 0`, `max_tokens: 1024`
  (igual que `src/filemaid/extract/rungs/vlm_local.py`). Latencia «ida y
  vuelta» HTTP medida por el script; resultado íntegro en
  `.sdd/metrics/vlm-local-latencia.json`.
- Se hicieron **3 corridas** el 2026-09-20 (06:06, 06:14 y 06:28), todas con
  el servidor en reposo y todas con el 100 % de peticiones devolviendo OCR
  utilizable (`todas_devolvieron_ocr: true`) y coste 0,00 €
  (`data/bench_vlm_local_limpio.json`, `data/bench_vlm_local_final.json` y
  `.sdd/metrics/vlm-local-latencia.json`). Las cifras canónicas de este
  documento son las de la última corrida (06:28, n=8 serial + n=5
  concurrente); las otras dos se citan como repetición que confirma
  estabilidad.
- Verificación post-corrida: `pgrep -af llama-server` muestra el mismo PID
  (60766, iniciado 2026-09-20 04:27, desdemonizado) que ya corría antes de la
  medición; no se arrancó ni se cerró ningún servidor (ver «Procesos», abajo).

## Resultados de la medición de hoy (escalón 4) [medido hoy, 2026-09-20]

Fase serial (8 peticiones, 1 imagen cada una, rotando las 3 imágenes):

- p50 **3 942 ms** · p95 **4 388 ms** (n=8). Salida estable: 201-210 tokens
  OCR por petición, todas con texto utilizable.
- Corridas de repetición [medido hoy]: 06:06 (n=10): p50 3 617 ms, p95
  4 313 ms; 06:14 (n=9): p50 3 987 ms, p95 4 319 ms. Las tres corridas caen
  en el mismo rango (3,3-4,6 s): sin bi-modalidad; el servidor en reposo da
  una latencia estable de **~3,3-4,6 s** por página.
- Nota del propio script (`.sdd/metrics/vlm-local-latencia.json`,
  `nota_primer_encuentro`): con el servidor caliente no hay diferencia
  estable entre primer encuentro de imagen y reuso vía prompt-cache
  (cached_tokens ≈ 1272/1273); el bi-modal 3,5 s / 34,9 s de la corrida de
  las 04:41 (ver [medido antes]) fue contención de CPU con el runner activo,
  no latencia en reposo.

Fase concurrente (5 peticiones, semáforo de 2):

- p50 **6 110 ms** · p95 **6 329 ms** (n=5), wall-clock 17,8 s,
  ~16,8 páginas/min equivalentes. Con 2 peticiones en paralelo el
  servidor encola: cada petición añade ~0,7-2 s de cola frente al serial.
  (Repetición 06:14 [medido hoy]: p50 4 687 ms, p95 4 770 ms, ~25,5
  páginas/min — la mejora entre corridas es efecto de caché caliente del
  prompt; rango honesto: **17-26 páginas/min** con concurrencia 2 [medido
  hoy].)

## Resultados previos (fuente: `.sdd/metrics/vlm-local-latencia.json` de las 04:41 y `video/data_lote1.json`, corrida T14 del lote 1) [medido antes, 2026-09-20]

- Medición de las 04:41 (servidor en reposo, 3 imágenes × 8 seriales + 5
  concurrentes c=2): serial bi-modal p50 ≈ 3,5 s / p95 ≈ 34,9 s — las 2
  peticiones lentas eran primer encuentro del mmproj con el runner
  procesando el lote 1 a la vez (contención de CPU); estado estable 3,0-3,6 s
  con prompt-cache.
- Lote 1 completo (500 PDFs, `rung4_vlm_local`): 28 invocaciones del escalón 4,
  media **33,9 s**, máximo **60,1 s** (timeout de 120 s del rung no se
  alcanzó; una invocación alcanzó el `RUNGER_TIMEOUT` de 60 s). El rung se
  serializa (`rung4_serializado: true`), por lo que la latencia media coincide
  con la de reposo.
- Escalón 7 en el lote 1 (`rung5_cloud`): 29 invocaciones reales, media
  **1 555 ms**, máximo 30 780 ms (los 5 intentos facturables devolvieron 404
  → coste 0,00 €). Coincide con `METRICS.vlmCloudMeanMs = 1555 ms`
  (`video/src/scenes.ts`).

## Tabla comparativa por escalón

Coste por 1000 páginas asumiendo el perfil real del corpus (94,2 % resuelto
en escalón 1). La columna «si todo llegara aquí» es el coste hipotético si
cada página se procesase por ese escalón, para comparar escalones entre sí.

| Escalón | Motor | Latencia p50 / p95 | Coste por 1000 páginas (perfil real 94,2 % texto) | Si cada página llegara a este escalón | Fuente / etiqueta |
|---|---|---|---|---|---|
| 4 — VLM local | PaddleOCR-VL 1.6 Q8, llama-server 4 hilos, CPU (8 hilos online), sin GPU | **3 942 ms / 4 388 ms** (serial, n=8); 6 110 ms / 6 329 ms (concurrente c=2, n=5) [medido hoy]; 33,9 s de media en el lote 1 real con 28 invocaciones [medido antes] | **0,00 €** (solo coste marginal de electricidad, <0,001 € ver `docs/capacidad_y_coste.md` §2) [estimado] | ~4 s × 1 000 ≈ 1,1 h de CPU, 0,00 € (serial, servidor caliente) [estimado] | Latencia: **[medido hoy 2026-09-20]** con `uv run python scripts/bench_vlm_local.py`; refuerzo lote 1 [medido antes] |
| 5 — TypeSafe System One | `jev-latest`, juicio tipado sobre texto ya extraído (nunca OCR) | ~560 ms por decisión [estimado, cifra de `video/src/scenes.ts`]; sin clave aquí, no medible | ~0,04 $/Mtok [estimado, cifra citada en `video/src/scenes.ts`]; con decisiones tipadas (~300 tok lectura+salida por decisión) ≈ **0,01 $ ≈ 0,01 € por 1000 páginas** si solo llega el 5,8 % de cola ≈ 0,0007 € | 1000 páginas × ~300 tok ≈ 0,3 Mtok ≈ **0,01 $ ≈ 0,01 €** [estimado] | **[no medido]** (sin `TYPESAFE_API_KEY`); precio y latencia **[estimado]** (cifra de código, no de facturación) |
| 7 — VLM cloud (>25B) | Endpoint OpenAI-compatible, default `gpt-4o-mini` | **1 555 ms** de media, máx 30,8 s en el lote 1 (n=29) [medido antes, `video/data_lote1.json`/`data_dryrun.json` → `METRICS.vlmCloudMeanMs`]; ~3 s por página era la estimación de partida [estimado] | GPT-4o-mini: 0,15 $/M tok entrada + 0,60 $/M tok salida (OpenAI, precio público; cita 2026-09-20) ⇒ con 1 273 tok entrada (imagen) + ~230 salida por página ≈ 0,0002 + 0,00014 ≈ **0,33 $ ≈ 0,30 € por 1000 páginas** [estimado] | Igual que la columna anterior: ≈ 0,30 € por 1000 páginas [estimado] | Latencia **[medido antes]** (lote 1, 29 llamadas reales); precio **[estimado]**, sin `OPENAI_API_KEY` aquí |

Notas de la tabla:

- Tokens de entrada del escalón 4/7 constantes en 1 273 (dominan los de
  imagen); el tiempo crece sobre todo con los de salida [medido antes,
  `docs/benchmarks_extraccion.md`].
- El escalón 5 no genera texto, solo decisiones tipadas; su coste por
  «página» depende del número de preguntas tipadas por lectura, no del
  tamaño del documento [estimado].
- El «~34 s/página» del lote 1 y de la medición de las 04:41 [medido antes]
  fue contención de CPU con el runner activo; hoy, con el servidor en
  reposo, el mismo modelo da **p50 3,9 s / p95 4,4 s** [medido hoy]. Para
  dimensionar capacidad usar la cifra de reposo; para planificar ventanas
  de proceso nocturno junto al runner, la de carga (~34 s).

## Coste de las 500 facturas del corpus por estrategia

Perfil real medido: 471 páginas escalón 1 + 29 páginas que llegan a escalón 4.
Columna «si todo cloud»: coste si se enviara el corpus entero a un VLM cloud
sin escalera.

| Estrategia | Desglose | Coste total 500 facturas | Fuente |
|---|---|---|---|
| Solo escalón 1 (texto vectorial) | 471 resueltas gratis; 29 quedan sin extraer | **0,00 €** [medido antes, dry-run] | `video/data_dryrun.json` |
| Escalera completa (recomendada: 1→2→3→4, cloud solo escalada) | 471 gratis + 29 × escalón 4 (0,00 €) + 0 llamadas cloud facturables (lote 1: 5 intentos cloud, todos 404) | **0,00 €** [medido antes, lote 1 T14 coste total 0,00 €] | `video/data_lote1.json` |
| Todo por escalón 4 | 500 × ~4 s = ~33 min de CPU en reposo (0,00 €) | **0,00 €** | [estimado] con p50 de hoy |
| Todo por escalón 7 (cloud) | 500 × ~1 273 tok entrada + ~230 salida ≈ 0,64 Mtok in + 0,115 Mtok out ≈ 0,096 + 0,069 ≈ **0,165 $ ≈ 0,15 €** | **≈ 0,15 €** [estimado] | precio OpenAI citado arriba (2026-09-20) |
| Escalón 5 (TypeSafe) sobre las 29 escaneadas (como segunda opinión tipada) | 29 decisiones × ~300 tok ≈ 0,009 Mtok ≈ **0,0004 $ ≈ 0,0003 €** | **≈ 0,00 €** (céntimos redondeados a 0) | [estimado] con 0,04 $/Mtok de `video/src/scenes.ts` |

## Recomendación (escalera: local primero, cloud solo escalada)

1. **El cuello de botella es latencia, no coste.** Con la mezcla real
   (94,2 % texto vectorial), el escalón 4 solo recibe ~6 % de las páginas:
   en el lote 1 real fueron 28 invocaciones × ~34 s ≈ 16 min de VLM local,
   tolerable en flujo nocturno. Su coste es 0,00 € frente a ~0,15 € del
   mismo volumen por cloud — la decisión escalón 4 vs 7 es de latencia,
   privacidad (los documentos no salen de la máquina) y principio
   «resolver localmente todo lo que se pueda», no de dinero.
2. **Escalón 7 solo como último recurso y solo en escalada.** Su lectura es
   «otro candidato», nunca respuesta automática (docs/report/architecture.typ).
   En el lote 1 real: 0 lecturas cloud facturables. Si el corpus creciera a
   10 000 facturas/mes todo-por-cloud serían ~3 € [estimado] — barato, pero
   innecesario cuando el escalón 4 cubre el 100 % de las escaneadas gratis.
3. **Escalón 5 (TypeSafe) como segunda opinión tipada, no como OCR.** Sin
   clave en esta máquina no se ejecuta; cuando la haya, su rol es decidir
   sobre texto ya extraído (¿es factura?, ¿tiene CIF?, ¿es legible?) para
   reducir la cola de ESCALAR, no para leer páginas. Coste marginal
   [estimado] despreciable.
4. **Dimensión de capacidad.** Con p50 3,9 s/página en reposo y concurrencia
   2 (17-26 páginas/min [medido hoy]), un solo i5-12400 sin GPU drena el
   5,8 % escaneado de 10 000 facturas (~580 páginas) en ~22-34 min
   [estimado, rango anclado a las dos corridas de hoy]. Para volúmenes
   muy superiores, subir concurrencia del servidor o escalar horizontal con
   más máquinas; nunca enviar por defecto a cloud.

## Procesos y limpieza

- No se arrancó ningún `llama-server` durante esta tarea: el proceso que
  atendía `127.0.0.1:8080` (PID 60766, iniciado 2026-09-20 04:27,
  desdemonizado, PPID 1) ya corría antes de empezar y se dejó exactamente
  como estaba (ningún proceso abierto por esta sesión que haya que cerrar).
