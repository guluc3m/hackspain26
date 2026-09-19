#import "lib.typ": *

= ADRs y trade-offs

#adr([Motor de reglas determinista, con reglas como configuración],
  contexto: [La norma de negocio exige decisiones reproducibles y auditables: pagar solo si el NIF y el IBAN cruzan con el maestro, el pedido existe y cuadra, el IVA está bien calculado y la fecha es válida. Ante duda razonable, ESCALAR.],
  alternativas: [LLM que decida directamente sobre el texto de la factura; reglas hardcodeadas acopladas a la extracción; reglas en YAML sin versionado ni snapshot.],
  decision: [La decisión final la toma un motor de reglas en código, determinista y puro, pero configurable y modificable. Los umbrales de confianza son configuración versionada por campo y extractor; cada decisión guarda un snapshot (umbrales). Añadir una regla no toca extracción y viceversa; cambiar la política exige ADR.],
  consecuencias: [Determinismo y explicabilidad completos (cada resultado lista las reglas aplicadas y la configuración usada); el reprocesado tras un cambio de datos (regla v4, maestro actualizado) funciona desde el diseño, no como parche.],
)

#adr([Extracción en dos bloques: _features_ y _parser_],
  contexto: [Las facturas llegan como PDF nativos y escaneados, con QRs en algunas legislaciones. Cada campo debe poder rastrearse hasta su origen en el documento. Los umbrales iniciales del rung 3 (word-conf 60, cobertura 0.5) se fijaron SIN medición.],
  alternativas: [Un único modelo end-to-end que devuelva los campos con trazabilidad; OCR monolítico con plantillas fijas por proveedor; mantener los umbrales a ojo.],
  decision: [Bloque de extracción produce _features_ tipadas (texto, tablas, QR, OCR) y un _parser_ independiente las convierte en campos con valores múltiples, cada uno con extractor y nivel de confianza. Umbrales del rung 3 CALIBRADOS con el corpus real: `tesseract_min_word_conf = 40.0` y `tesseract_min_field_coverage = 0.4` (config `extract-v2`), elegidos en el hueco bimodal de las distribuciones medidas.],
  consecuencias: [Más piezas que operar, pero cada extractor es sustituible y comparable; el 94,2 % del corpus resuelve por texto (peldaño casi gratis) y el 89,7 % de las páginas OCR pasa el gate con los 3 escaneos ilegibles a revisión.],
)

#adr([Pipeline Python desacoplada; ERP fuera de scope con costura de adaptador],
  contexto: [El procesamiento por factura es independiente del resto: el problema es _embarrassingly parallelizable_ y hay que absorber lotes de archivos. El ERP del usuario está fuera del alcance del reto: solo se exige la costura de integración.],
  alternativas: [Monolito secuencial; repartir en microservicios desde el inicio; integrar el ERP de verdad dentro del pipeline.],
  decision: [Pipeline en Python con colas entre bloques de extracción, _parser_ y decisión, de modo que cada bloque escale horizontalmente de forma independiente y un fallo del proveedor de LLM no bloquee el resto. El ERP se toca SOLO a través de una costura de adaptador (`ERP_STATE_PENDING` consulta el estado del pedido vía interfaz intercambiable); ningún módulo del pipeline conoce el ERP concreto.],
  consecuencias: [Infraestructura algo mayor que un script secuencial; a cambio, escalado por bloque, reintentos aislados y recuperación sin duplicados (idempotencia por _invoice id_ y por (sha256, stage, versión)), y el día de mañana se conecta un ERP real sin tocar reglas ni extracción.],
)


// TODO: ADR de UI