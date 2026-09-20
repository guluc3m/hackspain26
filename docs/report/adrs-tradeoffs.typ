#import "lib.typ": *

= ADRs y trade-offs

#adr(
  [Motor de reglas determinista, con reglas como configuración],
  contexto: [La norma de negocio exige decisiones reproducibles y auditables:
    pagar solo si el NIF y el IBAN cruzan con el maestro, el pedido existe y
    cuadra, el IVA está bien calculado y la fecha es válida. Ante duda
    razonable, ESCALAR.],
  alternativas: [LLM que decida directamente sobre el texto de la factura;
    reglas hardcodeadas acopladas a la extracción; reglas en YAML sin versionado
    ni snapshot.],
  decision: [La decisión final la toma un motor de reglas en código,
    determinista y puro, pero configurable y modificable. Los umbrales de
    confianza son configuración versionada por campo y extractor; cada decisión
    guarda un snapshot (umbrales). Añadir una regla no toca extracción y
    viceversa; cambiar la política exige ADR.],
  consecuencias: [Determinismo y explicabilidad completos (cada resultado lista
    las reglas aplicadas y la configuración usada); el reprocesado tras un
    cambio de datos (regla v4, maestro actualizado) funciona desde el diseño, no
    como parche.],
)

#adr(
  [Extracción en dos bloques: _features_ y _parser_],
  contexto: [Las facturas llegan como PDF nativos y escaneados, con QRs en
    algunas legislaciones. Cada campo debe poder rastrearse hasta su origen en
    el documento. Los umbrales iniciales del _rung_ 3 se fijaron SIN medición.],
  alternativas: [Un único modelo end-to-end que devuelva los campos con
    trazabilidad; OCR monolítico con plantillas fijas por proveedor; mantener
    los umbrales a ojo.],
  decision: [Bloque de extracción produce _features_ tipadas (texto, tablas, QR,
    OCR) y un _parser_ independiente las convierte en campos con valores
    múltiples, cada uno con extractor y nivel de confianza. Umbrales del rung 3
    CALIBRADOS con el corpus real, elegidos en el hueco bimodal de las
    distribuciones medidas.],
  consecuencias: [Más piezas que operar, pero cada extractor es sustituible y
    comparable; el 94,2 % del corpus resuelve por texto (peldaño casi gratis) y
    el 89,7 % de las páginas OCR pasa el gate con los 3 escaneos ilegibles a
    revisión.],
)

#pagebreak()

#adr(
  [Pipeline desacoplada],
  contexto: [El procesamiento por factura es independiente del resto: el
    problema es _embarrassingly parallelizable_ y hay que absorber lotes de
    archivos. El ERP del usuario está fuera del alcance del reto: solo se exige
    la costura de integración.],
  alternativas: [Monolito secuencial; repartir en microservicios desde el
    inicio; integrar el ERP de verdad dentro del pipeline.],
  decision: [Pipeline en Python con colas entre bloques de extracción, _parser_
    y decisión, de modo que cada bloque escale horizontalmente de forma
    independiente y un fallo del proveedor de LLM no bloquee el resto. El ERP se
    toca SOLO a través de una costura de adaptador; ningún módulo del pipeline
    conoce el ERP concreto.],
  consecuencias: [Infraestructura algo mayor que un script secuencial; a cambio,
    escalado por bloque, reintentos aislados y recuperación sin duplicados
    (idempotencia por _invoice id_ y por (sha256, stage, versión)), y el día de
    mañana se conecta un ERP real sin tocar reglas ni extracción.],
)


#adr(
  [Almacén documental PouchDB + replicación nativa a CouchDB, en lugar de una
    BBDD relacional],
  contexto: [El plan inicial era una BBDD relacional (SQLite local y Postgres en
    servidor, o equivalentes). Pero lo que el sistema conserva no encaja en
    tablas: los artefactos escaneados de cada documento (PDF original, PNG,
    intermedios), los logs semiestructurados de cada escalón de la escalera, el
    propio fichero, y además decisiones, candidatos y overrides con procedencia.
    La forma es heterogénea, anidada y evoluciona por documento; referenciar los
    binarios por ruta externa rompía la trazabilidad y la reanudación. El
    sistema corre 24/7 sin supervisión, debe sobrevivir a reinicios y a caídas
    de red, y el histórico debe poder replicarse entre dispositivos.],
  alternativas: [SQLite relacional + ledger JSONL _append-only_ (el diseño
    original); Postgres en servidor con tablas normalizadas; almacén de objetos
    (S3/MinIO) para binarios + SQL solo para metadatos; base documental embebida
    con replicación nativa (PouchDB local + CouchDB).],
  decision: [Se adopta un almacén documental: PouchDB 9 embebido (adaptador
    LevelDB) como única persistencia _runtime_ local, y un conector de
    replicación nativa contra una instancia CouchDB en la nube preexistente. Los
    binarios se guardan como adjuntos fragmentados (< 1 MiB) enlazados por
    documento, nunca por ruta externa; features, campos, decisiones, caché,
    eventos y overrides son documentos JSON con ID determinista, y los logs
    semiestructurados y la configuración local viven en el mismo motor. Los
    _exports_ son proyecciones, no el almacén. La sincronización es la
    replicación nativa de CouchDB (revisiones, adjuntos y _checkpoints_), no un
    protocolo propio.],
  consecuencias: [Un único motor cubre documentos, binarios, logs y caché, y la
    sincronización local↔nube es replicación de serie, sin ETL ni esquema de
    migración. A cambio se renuncia a _joins_, restricciones y transacciones
    multi-documento: la consistencia se apoya en IDs deterministas,
    inmutabilidad y detección de conflictos _fail-closed_ (nunca
    _last-write-wins_), y las consultas usan vistas versionadas por prefijo.
    Exige Node ≥ 20 y un puente acotado Python→JS. El histórico relacional
    anterior se conserva como enlace de compatibilidad, nunca como clave única
    de fichero.],
)

