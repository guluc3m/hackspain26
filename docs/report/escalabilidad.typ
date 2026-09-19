= Escalabilidad y coste

Los datos de esta sección se generan desde el store con
`uv run python -m albertitos.report_data` (archivo `datos.typ`, NO editar a
mano). Cada cifra indica si es #emph[medida] o si aún #emph[sin datos medidos]
— jamás se publica un número inventado.

#import "datos.typ": *

#table(
  columns: (auto, auto, auto),
  table.header([Métrica], [Valor], [Estado]),
  [Facturas decididas], [#facturasDecididas.at(0)], [#facturasDecididas.at(1)],
  [Resultados PAGAR / NO_PAGAR / ESCALAR],
    [#conteoResultados.PAGAR.at(0) / #conteoResultados.NO_PAGAR.at(0) / #conteoResultados.ESCALAR.at(0)],
    [medido],
  [Páginas con evidencia de extracción], [#paginasExtraccion.at(0)], [#paginasExtraccion.at(1)],
  [Latencia media por registro de evidencia], [#latenciaMedia.at(0)], [#latenciaMedia.at(1)],
  [Coste acumulado], [#costeAcumulado.at(0)], [#costeAcumulado.at(1)],
  [Versión del set de reglas activa], [#versionReglas.at(0)], [#versionReglas.at(1)],
  [Reintentos registrados], [#reintentos.at(0)], [#reintentos.at(1)],
  [Peldaños omitidos (extractor ausente)], [#omisiones.at(0)], [#omisiones.at(1)],
  [Fallos de proveedor], [#erroresProveedor.at(0)], [#erroresProveedor.at(1)],
)

== Reparto de coste por extractor

La fórmula de coste es explícita (datos de `escalabilidad_datos.typ`,
generados por `uv run python -m albertitos.metrics`). La CPU local es gratis
salvo electricidad (estimada: kWh = horas × potencia × €/kWh); el coste real
por llamada cloud (nº × €/llamada) se mide en la corrida (T14):

$ "coste lote" = "electricidad" ("h" × "kW" × "€/kWh"; "estimado") + "llamadas cloud" ("nº" × "€/llamada") + "tokens agentes" ("1k" × "€") $

#import "escalabilidad_datos.typ": *

#table(
  columns: (auto, auto, auto),
  table.header([Término], [Valor], [Estado]),
  [Electricidad CPU (h × kW × €/kWh)], [#formulaCoste.electricidad_cpu.at(0)], [#formulaCoste.electricidad_cpu.at(1)],
  [Llamadas cloud (nº × €/llamada)], [#formulaCoste.llamadas_cloud.at(0)], [#formulaCoste.llamadas_cloud.at(1)],
  [Tokens de agentes], [#formulaCoste.tokens_agentes.at(0)], [#formulaCoste.tokens_agentes.at(1)],
  [Coste por archivo], [#costePorArchivo.at(0)], [#costePorArchivo.at(1)],
  [Coste del lote de referencia], [#costePorLote.at(0)], [#costePorLote.at(1)],
)

Las llamadas cloud del lote real se medirán en la corrida (T14) — el dry-run
(T10) no las factura porque solo cubre rungs 1–2. Los precios unitarios viven
en la configuración de métricas (no en código de
decisión) y cada uno lleva su etiqueta de origen. El coste marginal se
concentra en el peldaño de VLM en la nube (rung 5), que solo se factura para
páginas que no superan tesseract + VLM local; su resultado se cachea por
`(page_sha256, extractor_version, config_version)`, así que una re-ejecución
24/7 no vuelve a facturar. Los peldaños locales (texto, QR, tesseract, VLM q8
en CPU) tienen coste marginal nulo.

#if extractores.len() > 0 [
#table(
  columns: (auto, auto),
  table.header([Extractor], [Registros de evidencia]),
  ..extractores.keys().map(k => ([#k], [#extractores.at(k).at(0) #emph[(#extractores.at(k).at(1))]])).flatten(),
)
]

#if latenciasPorRung.len() > 0 [
== Rendimiento medido por rung

#table(
  columns: (auto, auto, auto, auto),
  table.header([Rung], [Latencia media], [p95], [Estado]),
  ..latenciasPorRung.pairs().map(p => ([#p.at(0)], [#p.at(1).at(0)], [#p.at(1).at(1)], [#p.at(1).at(2)])).flatten(),
)

Throughput medido: #archivosPorSegundo.at(0) archivos/s
#emph[(#archivosPorSegundo.at(1))]; el límite secuencial lo marca el rung más
lento (#rungMasLento.at(0)): #limiteThroughput.at(0)
#emph[(#limiteThroughput.at(1))]. Hardware: #hardware.at(0),
#hardwareRam.at(0) #emph[(#hardwareRam.at(1))].
]

== Dry-run del corpus real (T10, medido)

Fuente citada: `.sdd/metrics/corpus-dryrun.json` (+ evidencia línea a línea en
`.sdd/metrics/evidence-dryrun.jsonl`). Dry-run de los 500 PDFs reales, rungs
1–2, idempotente, concurrencia 2 — *el dry-run no decide, solo mide extracción*.

#table(
  columns: (auto, auto),
  table.header([Ruta de la escalera], [Archivos]),
  ..dryrunRutas.pairs().map(p => ([#p.at(0)], [#p.at(1) #emph[(medido)]])).flatten(),
)

- Capa de texto usable (rung 1): #dryrunTextoUsable.at(0) #emph[(#dryrunTextoUsable.at(1))].
- Latencia rung 1: media #dryrunLatenciaRung1.at(0), p95 #dryrunLatenciaRung1.at(1).
- Latencia rung 2 (raster+QR): media #dryrunLatenciaRung2.at(0), p95 #dryrunLatenciaRung2.at(1).
- Throughput rung 1: #dryrunThroughput.at(0) archivos/s (2 workers)
  #emph[(#dryrunThroughput.at(1))]; pared total #dryrunWall.at(0)
  #emph[(#dryrunWall.at(1))].

== Calibración del rung 3 (T10, medido sobre el corpus)

Fuente citada: `.sdd/metrics/calibracion/calibracion-rung3.json` (motivación
completa en `.sdd/metrics/calibracion.md`). Se midieron las DOS partes del
gate sobre las 29 páginas OCR y las 493 capas de texto únicas.

- Cobertura de campos: #calibracionCoberturaTexto.at(0) —
  #calibracionCoberturaOcr.at(0) #emph[(#calibracionCoberturaOcr.at(1))].
- Decisión calibrada (config `extract-v2`): #calibracionDecision.at(0)
  #emph[(#calibracionDecision.at(1))]. La distribución de word-conf es
  bimodal: con umbral 40.0 pasan las 26 páginas legibles y quedan debajo
  exactamente los 3 escaneos ilegibles que anuncia la doctrina (§11).

== Drills de resiliencia (T12, medidos sin red real)

Fuente citada: `.sdd/metrics/drills.json`. Resumen: #drillsResumen.at(0)
#emph[(#drillsResumen.at(1))].

#table(
  columns: (auto, auto),
  table.header([Drill], [Resultado]),
  ..drillsPorNombre.pairs().map(p => ([#p.at(0)], [#p.at(1)])).flatten(),
)

== Lote 1 y reprocesado (T14/T13)

- Resultados del lote 1 (500 PDFs, corrida completa): #resultadosLote1.at(0)
  #emph[(#resultadosLote1.at(1))].
- Exactitud sobre la referencia privada: #exactitudLote1.at(0)
  #emph[(#exactitudLote1.at(1))].
- Reprocesado tras cambio de reglas/datos: #impactoReprocesado.at(0)
  #emph[(#impactoReprocesado.at(1))].

== Perfil de carga del sistema completo (T23, medido)

Fuente citada: `.sdd/metrics/perfil-carga.json` (generado con
`uv run python -m albertitos.perfil`): régimen completo en esta caja —
la UI sirviendo el lote 1 real (500 facturas) mientras **2 runners
concurrentes** (`--limit 50`, stores temporales) procesan con llama-server
up. Resultado medido: la UI sigue respondiendo (peor p95 de las 5 pantallas
< 12 ms), 108–110 archivos/s por runner, RSS ~96 MB (UI) / ~38 MB (runner),
8 GB RAM libres de 12 — **concurrencia soportada medida, 0 ROJOS**.

- Límite práctico en esta caja (8 cores / 12 GB): rung 4 serializado ocupa
  ≈1 core por runner; el régimen cómodo estimado es ~4-6 runners + UI
  (extrapolación, etiquetada ESTIMADO — el medido es el régimen de 2 runners
  + UI sin degradación).
- La RAM NO es el cuello (RSS por componente ≈ 38–96 MB, sobran GB): con más
  RAM el régimen no cambia; el límite es CPU en rung 3/4. La fórmula de coste
  de arriba queda intacta.

== Escalado

El procesamiento por factura es independiente del resto
(_embarrassingly parallelizable_): las colas entre extracción, _parser_ y
decisión permiten escalar cada bloque horizontalmente. Los límites prácticos
del despliegue actual son el _sidecar_ `llama-server` (presupuesto fijo de
hilos que los agentes no deben acaparar) y la cuota del proveedor en la nube,
cuyos fallos (429, _timeouts_) se degradan a peldaños inferiores sin parar el
lote — los reintentos y omisiones de la tabla lo reflejan.

== Capacidad y coste pendientes de medición (T8/T14)

- Facturas por segundo del _runner_ de lote (T8) y coste por factura del lote
  real: #facturasPorSegundo.at(0) / #costePorFactura.at(0)
  #emph[(#facturasPorSegundo.at(1))]. Se medirán en la corrida real (T14).
- Presupuesto de tiempo por página OCR local en CPU: 10-30 s según complejidad
  — #emph[estimado del fabricante, pendiente de medición en producción].
