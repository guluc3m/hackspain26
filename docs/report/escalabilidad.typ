#import "lib.typ": *
// Datos generados por filemaid.metrics — números medidos del ledger.
#import "escalabilidad_datos.typ": hardware, hardwareRam, dryrunTextoUsable, dryrunThroughput, dryrunLatenciaRung1, dryrunLatenciaRung2, perfilCarga, resultadosLote1, impactoFix

// Etiquetas de trazabilidad: cada cifra dice de dónde viene.
#let m = chip([medido], fill: teal, text-fill: paper)
#let mbc = chip([medido bajo carga], fill: rgb("#fff8e1"))
#let e = chip([estimado], fill: sand)
#let nm = chip([no medido], fill: rgb("#fbe9e7"), text-fill: red)

// Fila de tabla: magnitud | valor | etiqueta.
#let fila(mag, valor, etiq) = (mag, valor, etiq)
#let tabla-etiquetada(..filas, cols: (32%, 44%, auto)) = table(
  columns: cols,
  stroke: 0.9pt + ink,
  inset: (x: 8pt, y: 6.5pt),
  table.header(
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [MAGNITUD])),
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [VALOR])),
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [ETIQUETA])),
  ),
  ..filas.pos().map(((mag, valor, etiq)) => (
    table.cell(text(weight: 700, mag)),
    table.cell(valor),
    table.cell(etiq),
  )).flatten(),
)

= Escalabilidad y coste

La escalabilidad de filemaid no se afirma: se mide. Esta sección recoge los
números reales de la máquina de la demo (hardware, throughput por escalón,
límites prácticos) y el coste de operación, con cada cifra etiquetada:
#m = corrida real con fuente en el repo; #e = derivado con supuestos
explícitos; #nm = sin credenciales, nunca corrido. Fuentes:
`docs/report/escalabilidad_datos.typ` (generado por `filemaid.metrics`),
`docs/capacidad_y_coste.md`, `docs/benchmarks_extraccion.md` y
`video/data_lote1.json` (lote 1 real).

== Hardware y límites medidos

#tabla-etiquetada(
  fila([CPU], [8 núcleos (i5-12400), sin GPU ni `\/dev\/dri`], m),
  fila([RAM], [16 GB físicos; el informe del ledger reporta 12 GB visibles al proceso], m),
  fila([Modelo OCR local], [PaddleOCR-VL 1.6 Q8 vía llama-server, ~1,1 GB en disco, 4 hilos, KV cache q8_0], m),
  fila([Llamadas VLM concurrentes], [1 — el escalón 4 corre serializado], m),
  fila([Resiliencia], [4 drills automatizados PASS / 0 FAIL (proveedor caído, backoff 429, crash con reanudación, ledger corrupto)], m),
)

El factor limitante no es la CPU: es el número de páginas que caen al escalón
4 (VLM local, serializado, ~34 s por página).

== Throughput por escalón

Corpus de 500 facturas (dry-run de escalones 1–2 y lote 1 real):

#table(
  columns: (24%, 30%, 17%, auto),
  align: (left, center, center, right + horizon),
  stroke: 0.9pt + ink,
  inset: (x: 8pt, y: 6pt),
  table.header(
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [ESCALÓN])),
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [LATENCIA MEDIA])),
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [P95])),
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [ETIQUETA])),
  ),
  [1 · pypdf (capa de texto)], [0,4 ms], [2,0 ms], m,
  [2 · rasterizado + QR (pypdfium2+zxing)], [42,1 ms], [73,0 ms], m,
  [3 · Tesseract], [—], [—], nm,
  [4 · VLM local (PaddleOCR-VL)], [33,9 s (n=28, lote 1)], [60,1 s], mbc,
  [5 · TypeSafe Jev], [—], [—], nm,
  [6 · Firecrawl], [—], [—], nm,
  [7 · VLM cloud], [1,55 s (n=29, intentos 404 sin facturar)], [30,8 s], mbc,
)

Los escalones 3, 5 y 6 son _stubs_ sin dependencias o credenciales en esta
máquina: la escalera los salta (`skipped:stub`) y el lote nunca se detiene. La
latencia del escalón 7 corresponde a intentos fallidos con 404: no representa
la inferencia real; su precio de lista se estima en la sección de coste.

=== Throughput extremo a extremo

- *Dry-run escalón 1*: #dryrunThroughput.first() files/s — 3,57 s de wall para
  500 archivos #m (`video/data_dryrun.json`).
- *Lote 1 real* (escalera completa: 94,2 % de texto usable + 29 páginas
  raster→VLM): 500 archivos en ~120 s ⇒ *4,16 files/s* #m
  (`video/data_lote1.json`).
- *Perfil de carga* (UI + 2 runners simultáneos): peor p95 7,7 ms,
  108,7–110,0 files/s por runner, 0 fallos #m (`perfil-carga.json`).

=== Límite práctico de esta máquina

Con la mezcla medida (94,2 % resuelto en escalón 1, 5,8 % cae al VLM local):

$ "files/s" approx frac(1, 0.942 dot t_1 + 0.058 dot (t_"1,2" + t_4)) approx
frac(1, 0.0004 + 0.058 dot 33.9) approx 0.51 "files/s" ⇒ approx 1\,820 "archivos/h" $
#h(1fr)#e

El lote 1 real rindió mejor (4,16 files/s ≈ 14 400 archivos/h equivalentes
#m) porque solo 28 de 500 páginas invocaron el VLM y el resto del pipeline
solapa con esa espera. Cota conservadora para planificación: *4–14 mil
archivos/h con la mezcla actual* #e, límites anclados a datos medidos.

== Fórmula de coste

$ "coste" = f_"texto" dot 0 + f_"ocr" dot t_"VLM" dot P_"(W)" dot frac("€/kWh", 3\,600\,000) + sum_("llamadas cloud") "precio"_"llamada" $

donde $f_"texto"$ = fracción resuelta sin OCR (0,942 #m), $f_"ocr"$ =
fracción que cae al escalón 4 (0,058 #m), $t_"VLM"$ = 33,9 s CPU por página
#m, $P_"(W)"$ = potencia del paquete (no medible sin root: se usa el TDP del
i5-12400, 65 W, como cota superior #e) y €/kWh = 0,15 €/kWh de referencia
doméstica España #e.

=== Local (escalones 1–4): 0 € de software

Todo local y sin licencias de pago: el coste marginal de software es *cero*.
El único coste real es energía, y es eléctricamente despreciable:

#tabla-etiquetada(
  fila([Coste software por archivo], [*0,00 €* — 0 llamadas cloud facturables en el lote 1], m),
  fila([Energía del lote 1 (500 facturas, ~120 s a 65 W)], [0,0022 kWh ⇒ 0,00033 €], e),
  fila([Energía por archivo (mezcla 94,2 % texto)], [≈ 6,5 × 10⁻⁷ €], e),
  fila([Energía a 10 000 facturas], [del orden de 0,005 €], e),
)

El coste real de la vía local es tiempo de máquina, no dinero.

=== Cloud: nº de llamadas × precio de llamada

#tabla-etiquetada(
  fila([Lote 1 real (500 facturas, 29 páginas raster)], [*0,00 €* — 0 lecturas facturables; 5 intentos devolvieron 404 sin facturar], m),
  fila([gpt-4o-mini, precio de lista], [0,15 \$ / 1M tokens entrada + 0,60 \$ / 1M salida ⇒ ≈ 0,0002–0,0003 \$ por página (1273 tokens de imagen + ~230 de salida medidos)], e),
  fila([Si las 29 páginas raster del lote 1 hubieran ido a cloud], [29 × 0,0003 \$ ≈ 0,009 \$ ≈ 0,008 €], e),
  fila([Si el corpus completo (1000 páginas) fuera a cloud], [≈ 0,30 € por 1000 páginas], e),
)

La decisión entre escalón 4 y 7 no es de dinero (diferencia en céntimos a
escala de 500 PDFs/mes): es de latencia y privacidad — con el escalón 4 los
documentos no salen de la máquina.

== Plan de volumen: 1k / 10k / 100k

El cuello de botella es el escalón 4 (~34 s/página, serializado #m). Los
escalones 1–2 son CPU-local puro a 2 636 files/s #m; el 4 se paraleliza con
réplicas de llama-server; los 5–7 son llamadas HTTP que paralelizan
trivialmente (limitadas por rate-limit del proveedor).

#table(
  columns: (11%, 20%, 26%, auto),
  align: (center, center, center, left),
  stroke: 0.9pt + ink,
  inset: (x: 8pt, y: 6.5pt),
  table.header(
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [VOLUMEN])),
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [PÁGS. AL ESCALÓN 4])),
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [TIEMPO ESTIMADO])),
    table.cell(fill: ink, text(font: display-font, size: 7.5pt, fill: paper, tracking: 0.06em, [PLAN])),
  ),
  [1 000], [~58 páginas #e], [~33 min en serie #e], [Esta máquina tal cual: 1 proceso, 1 llama-server, sin cambios.],
  [10 000], [~580 páginas #e], [~5,5 h en serie #e; ~1,4 h con 4 réplicas de llama-server #e], [Paralelizar el escalón 4 (réplicas del sidecar o cola de procesos); los escalones 1–2 no necesitan nada.],
  [100 000], [~5 800 páginas #e], [~2,3 días en serie #e; ~14 h con 4 réplicas #e], [(a) Máquina dedicada 16 núcleos/32 GB + 8 réplicas VLM #e; (b) desviar el excedente al escalón 7 solo para el pico: 5 800 páginas × 0,0003 \$ ≈ 1,7 \$ #e — la vía cloud es 3 órdenes de magnitud más barata en €/página que amortizar hardware, pero envía datos fuera.],
)

Supuestos #e: misma mezcla 94,2/5,8 %; latencia VLM estable (con contención
se degrada); una factura = 1 página.

== Cómo se añaden nuevos tipos de archivo

Añadir soporte para un formato nuevo (xlsx, email, imágenes) *no toca las
reglas*: la extracción y la decisión están desacopladas por diseño (ADR-02).

- Cada escalón es un módulo con `NAME` + `extract(PageContext)` registrado en
  `_RUNGS` (`src/filemaid/extract/ladder.py`): añadir un tipo de archivo =
  añadir un escalón o adaptar el rasterizador; el bucle de la escalera no se
  toca #m (estructura del código).
- Un escalón sin dependencia (sin binario, sin clave) devuelve
  `skipped:<razón>` y la escalera continúa: el lote nunca se detiene #m
  (drills de resiliencia 4/4 PASS en `.sdd/metrics/drills.json`).
- Las imágenes (png/jpg) entran directo al escalón 2 #m (`extract_page_any`).
- El texto crudo nunca sale a la red desde escalones locales sin
  `remote_rungs_enabled` #m (`remote_allowed`).
- Para un _parser_ de un formato nuevo: extender el bloque de _features_
  (producir campos con extractor y nivel de confianza) y añadir los umbrales
  de confianza del nuevo extractor como CONFIGURACIÓN versionada por campo
  (ADR-01); el motor de reglas consume campos, no formatos, así que las 8
  reglas del motor siguen intactas.
