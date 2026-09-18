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
generados por `uv run python -m albertitos.metrics`):

$ "coste lote" = "extracción CPU" ("horas" × "€/h") + "llamadas cloud" ("nº" × "€/llamada") + "tokens agentes" ("1k" × "€") $

#import "escalabilidad_datos.typ": *

#table(
  columns: (auto, auto, auto),
  table.header([Término], [Valor], [Estado]),
  [Extracción CPU (horas × €/h)], [#formulaCoste.extraccion_cpu.at(0)], [#formulaCoste.extraccion_cpu.at(1)],
  [Llamadas cloud (nº × €/llamada)], [#formulaCoste.llamadas_cloud.at(0)], [#formulaCoste.llamadas_cloud.at(1)],
  [Tokens de agentes], [#formulaCoste.tokens_agentes.at(0)], [#formulaCoste.tokens_agentes.at(1)],
  [Coste por archivo], [#costePorArchivo.at(0)], [#costePorArchivo.at(1)],
  [Coste del lote de referencia], [#costePorLote.at(0)], [#costePorLote.at(1)],
)

Los precios unitarios viven en la configuración de métricas (no en código de
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
  ..extractores.keys().map(k => ([#k], [#extractores.at(k).at(0) #emph[(#extractores.at(k).at(1))]])),
)
]

== Rendimiento medido por rung

#table(
  columns: (auto, auto, auto, auto),
  table.header([Rung], [Latencia media], [p95], [Estado]),
  ..latenciasPorRung.pairs().map(((k, v)) => ([#k], [#v.at(0)], [#v.at(1)], [#v.at(2)])),
)

Throughput medido: #archivosPorSegundo.at(0) archivos/s
#emph[(#archivosPorSegundo.at(1))]; el límite secuencial lo marca el rung más
lento (#rungMasLento.at(0)): #limiteThroughput.at(0)
#emph[(#limiteThroughput.at(1))]. Hardware: #hardware.at(0),
#hardwareRam.at(0) #emph[(#hardwareRam.at(1))].

== Escalado

El procesamiento por factura es independiente del resto
(_embarrassingly parallelizable_): las colas entre extracción, _parser_ y
decisión permiten escalar cada bloque horizontalmente. Los límites prácticos
del despliegue actual son el _sidecar_ `llama-server` (presupuesto fijo de
hilos que los agentes no deben acaparar) y la cuota del proveedor en la nube,
cuyos fallos (429, _timeouts_) se degradan a peldaños inferiores sin parar el
lote — los reintentos y omisiones de la tabla lo reflejan.

== Capacidad y coste pendientes de medición (T8/T10)

- Facturas por segundo del _runner_ de lote (T8) y resultados del _dry-run_
  del corpus (T10): *PENDIENTE-MEDICIÓN*. La fórmula de coste de arriba ya
  separa medido de estimado; cuando T8/T10 escriban su evidencia al ledger,
  regenerar con `uv run python -m albertitos.metrics` rellena estos huecos.
- Presupuesto de tiempo esperado por página OCR local en CPU (8 núcleos):
  10-30 s según complejidad (tablas son el caso lento) — #emph[estimado del
  fabricante, pendiente de medición en producción].
