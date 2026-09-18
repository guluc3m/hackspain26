#import "lib.typ": *

#show: conf.with(
  event: [MAISA · HACKSPAIN 2026],
  challenge: "500 Sombras de Alberto",
  title: [ALBERTITOS PLAN],
  subtitle: [Arquitectura, decisiones de diseño y trade-offs del sistema de decisión de facturas],
  place: [ETSIT UPM · MADRID],
  date: [Entrega · dom 20 sep 2026 · 11:00],
  chips: ([FACTURA], [DECISIÓN], [TRAZA]),
  logo: "img/gul-logo.svg",
  team: [guluc3m],
  teamId: none,
  repo: "https://github.com/guluc3m/hackspain26",
  authors: (
    (name: "Luis Daniel Casais Mezquida", email: "luisdaniel.casais@alumnos.uc3m.es"),
    (name: "Albert Giurgiu", email: "fedesito@posteo.es"),
    (name: "Jorge Adrian Saghin Dudulea", email: "zanajorgesaghin@gmail.com"),
  ),
)

#include "architecture.typ"
#include "implementation.typ"
#include "escalabilidad.typ"

= ADRs y trade-offs

#adr([Motor de reglas determinista para la decisión],
  status: "ACEPTADA",
  contexto: [La norma de negocio exige decisiones reproducibles y auditables: pagar solo si el NIF y el IBAN cruzan con el maestro, el pedido existe y cuadra, el IVA está bien calculado y la fecha es válida. Ante duda razonable, ESCALAR.],
  alternativas: [LLM que decida directamente sobre el texto de la factura; modelo de ML entrenado con histórico propio (no disponible en el hackathon).],
  decision: [La decisión final la toma un motor de reglas en código (`TOTALS_MUST_MATCH`, `ERP_STATE_PENDING`, ...), con _thresholds_ de confianza configurables por campo y extractor. El LLM solo extrae, nunca decide.],
  consecuencias: [Determinismo y explicabilidad completos (cada resultado lista las reglas aplicadas y la configuración usada); a cambio, cada norma nueva requiere código y las reglas dependen del país/administración.],
  evidencia: [Resultado JSONL con `file_id`, `result`, reglas disparadas y confianza de cada campo extraído.],
)

#adr([Extracción en dos bloques: _features_ y _parser_],
  status: "ACEPTADA",
  contexto: [Las facturas llegan como PDF nativos y escaneados, con QRs en algunas legislaciones. Cada campo debe poder rastrearse hasta su origen en el documento.],
  alternativas: [Un único modelo end-to-end que devuelva los campos con trazabilidad; OCR monolítico con plantillas fijas por proveedor.],
  decision: [Bloque de extracción produce _features_ tipadas (texto, tablas, QR, OCR) y un _parser_ independiente las convierte en campos con valores múltiples, cada uno con extractor y nivel de confianza. Los campos son dinámicos para soportar legislaciones distintas.],
  consecuencias: [Más piezas que operar, pero cada extractor es sustituible y comparable; se puede reemplazar todo el bloque por un modelo si demuestra trazabilidad equivalente.],
  evidencia: [`ExtractionFeature` y `ExtractionField` con lista de valores por campo (extractor, valor, confianza).],
)

#adr([Pipeline Python desacoplada por colas],
  status: "ACEPTADA",
  contexto: [El procesamiento por factura es independiente del resto: el problema es _embarrassingly parallelizable_ y hay que absorber lotes de 500 y 40 archivos.],
  alternativas: [Monolito secuencial; repartir en microservicios desde el inicio.],
  decision: [Pipeline en Python con colas entre bloques de extracción, _parser_ y decisión, de modo que cada bloque escale horizontalmente de forma independiente y un fallo del proveedor de LLM no bloquee el resto.],
  consecuencias: [Infraestructura algo mayor que un script secuencial; a cambio, escalado por bloque, reintentos aislados y recuperación sin duplicados (idempotencia por _invoice id_).],
  evidencia: [Medición de archivos por segundo y coste por lote; prueba de fallo del proveedor con reencolado.],
)

#adr([Trazabilidad e histórico en base de datos],
  status: "ACEPTADA",
  contexto: [Muchas legislaciones exigen conservar histórico de facturas y decisiones; Alberto necesita reproducir cualquier decisión y alimentar futuros entrenamientos con los casos escalados.],
  alternativas: [Logs planos en ficheros; guardar solo el resultado final en el JSONL.],
  decision: [Cada paso del proceso persiste _logs_, datos intermedios y resultados en la base de datos; las resoluciones de los casos escalados se guardan para reentrenamiento y auditoría.],
  consecuencias: [Almacenamiento creciente y necesidad de retención; a cambio, trazabilidad completa input → evidencia → decisión y base para mejoras futuras.],
  evidencia: [Consulta por _invoice id_ que recupera features, campos, reglas y decisión con su configuración del momento.],
)
