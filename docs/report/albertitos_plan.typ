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
    (name: "Henry Díaz Bordón", email: "henrydiazbordon@gmail.com"),
  ),
)

#include "architecture.typ"
#include "implementation.typ"
#include "escalabilidad.typ"

= ADRs y trade-offs

#adr([Motor de reglas determinista, con reglas como configuración versionada (v3 → v4)],
  status: "ACEPTADA",
  contexto: [La norma de negocio exige decisiones reproducibles y auditables: pagar solo si el NIF y el IBAN cruzan con el maestro, el pedido existe y cuadra, el IVA está bien calculado y la fecha es válida. Ante duda razonable, ESCALAR. El lote 2 traerá la regla v4 cargada como DATOS, sin tocar el motor.],
  alternativas: [LLM que decida directamente sobre el texto de la factura; reglas hardcodeadas acopladas a la extracción; reglas en YAML sin versionado ni snapshot.],
  decision: [La decisión final la toma un motor de reglas en código (`TOTALS_MUST_MATCH`, `ERP_STATE_PENDING`, ...) — determinista y puro: mismos campos + misma configuración ⇒ misma salida byte a byte. Los umbrales de confianza son CONFIGURACIÓN versionada por campo y extractor; cada decisión guarda un snapshot (umbrales). Añadir una regla no toca extracción y viceversa; cambiar la política exige ADR.],
  consecuencias: [Determinismo y explicabilidad completos (cada resultado lista las reglas aplicadas y la configuración usada); el reprocesado tras un cambio de datos (regla v4, maestro actualizado) funciona desde el diseño, no como parche.],
  evidencia: [Cada decisión registra rule_verdicts con códigos y consumed, config_snapshot con umbrales (T3/T4); la pantalla Reglas previsualiza el efecto de cambiar un umbral sobre evidencia ya medida (T5); el validador de contrato (T9) comprueba el outcomes.jsonl contra los PDF exactos.],
)

#adr([Extracción en dos bloques: _features_ y _parser_ — calibrada con el corpus (T10)],
  status: "ACEPTADA",
  contexto: [Las facturas llegan como PDF nativos y escaneados, con QRs en algunas legislaciones. Cada campo debe poder rastrearse hasta su origen en el documento. Los umbrales iniciales del rung 3 (word-conf 60, cobertura 0.5) se fijaron SIN medición.],
  alternativas: [Un único modelo end-to-end que devuelva los campos con trazabilidad; OCR monolítico con plantillas fijas por proveedor; mantener los umbrales a ojo.],
  decision: [Bloque de extracción produce _features_ tipadas (texto, tablas, QR, OCR) y un _parser_ independiente las convierte en campos con valores múltiples, cada uno con extractor y nivel de confianza. Umbrales del rung 3 CALIBRADOS con el corpus real: `tesseract_min_word_conf = 40.0` y `tesseract_min_field_coverage = 0.4` (config `extract-v2`), elegidos en el hueco bimodal de las distribuciones medidas.],
  consecuencias: [Más piezas que operar, pero cada extractor es sustituible y comparable; el 94,2 % del corpus resuelve por texto (peldaño casi gratis) y el 89,7 % de las páginas OCR pasa el gate con los 3 escaneos ilegibles (§11) a revisión — exactamente los que la doctrina anuncia.],
  evidencia: [`.sdd/metrics/corpus-dryrun.json` (T10): 471/500 texto usable (94,2 %), 29 a raster, 0 solo-QR, 0 errores; latencias rung 1 media 0,4 ms / p95 2,0 ms y rung 2 media 42,1 ms / p95 73,0 ms; throughput rung 1 medido 2 636 archivos/s. `.sdd/metrics/calibracion/calibracion-rung3.json`: word-conf 40.0 deja debajo solo los 3 ilegibles (89,7 % pasa), cobertura 0.4 deja el 100 % de las capas de texto por encima. Explotación en la sección Escalabilidad (generada desde el store).],
)

#adr([Pipeline Python desacoplada; ERP fuera de scope con costura de adaptador],
  status: "ACEPTADA",
  contexto: [El procesamiento por factura es independiente del resto: el problema es _embarrassingly parallelizable_ y hay que absorber lotes de 500 y 40 archivos. El ERP del usuario está fuera del alcance del reto: solo se exige la costura de integración.],
  alternativas: [Monolito secuencial; repartir en microservicios desde el inicio; integrar el ERP de verdad dentro del pipeline.],
  decision: [Pipeline en Python con colas entre bloques de extracción, _parser_ y decisión, de modo que cada bloque escale horizontalmente de forma independiente y un fallo del proveedor de LLM no bloquee el resto. El ERP se toca SOLO a través de una costura de adaptador (`ERP_STATE_PENDING` consulta el estado del pedido vía interfaz intercambiable); ningún módulo del pipeline conoce el ERP concreto.],
  consecuencias: [Infraestructura algo mayor que un script secuencial; a cambio, escalado por bloque, reintentos aislados y recuperación sin duplicados (idempotencia por _invoice id_ y por (sha256, stage, versión)), y el día de mañana se conecta un ERP real sin tocar reglas ni extracción.],
  evidencia: [El pipeline actual conserva evidencia por escalón y decisiones por scan en PouchDB. Los tests de persistencia cubren fallos parciales, recuperación de originales, inmutabilidad y enlace exacto de informes; las mediciones históricas del runner anterior no describen el coste del puente Node actual.],
)

#adr([Trazabilidad e histórico en base de datos],
  status: "ACEPTADA",
  contexto: [Muchas legislaciones exigen conservar histórico de facturas y decisiones; Alberto necesita reproducir cualquier decisión y alimentar futuros entrenamientos con los casos escalados.],
  alternativas: [Logs planos, doble almacenamiento relacional/documental, servidor CouchDB local en cada cliente, guardar solo el resultado final.],
  decision: [PouchDB JS local como único motor cliente: documentos dinámicos con todos los candidatos, eventos, caché y decisiones inmutables; adjuntos fragmentados para artefactos. Modo servidor mediante replicación nativa PouchDB a una base de datos remota CouchDB existente, sin instalar CouchDB localmente. Escalador VLM independiente alojado en FastAPI. Configuración local excluida del intercambio.],
  consecuencias: [Un motor y esquema dinámico local, con recuperación sin ficheros originales. Sincronización transparente PouchDB<->CouchDB con gestión de revisiones; conflictos de contenido operan en modo fail-closed sin resolución silenciosa. El modo se elige en la UI sin bloquear el batch.],
  evidencia: [Contrato en docs/db-mig.md; pruebas de ingestión y recuperación en tests/test_pouch_persistence.py y tests/test_pouch_identity.py; replicación contra Apache CouchDB real en tests/test_couchdb_replication.py.],
)

#adr([Rung 5 en la nube: deepseek-v4.1-flash; revisión humana no bloqueante],
  status: "ACEPTADA",
  contexto: [Las páginas que no superan tesseract + VLM local necesitan una lectura de escalada. El servidor de IA local del usuario está CAÍDO: los modelos Qwen3.8-27B y qwen-next-flash están VETADOS en todos los roles (regla del usuario, no negociable). La escalada nunca puede bloquear el lote 24/7.],
  alternativas: [Qwen3.8-27B-Vision (preset `claude-opus-4-5`) — vetado: servidor caído; mantener todo local y degradar; bloquear el ítem hasta que un humano lea.],
  decision: [Rung 5 = modelo cloud de visión `deepseek-v4.1-flash`, SOLO para páginas que fallen tesseract + VLM local. Su lectura es OTRO candidato con confianza, jamás respuesta automática: los extractores proponen, las REGLAS deciden. El ítem resuelve ESCALAR y entra en una cola de revisión asíncrona en la UI; la corrección humana es un override con provenance que solo afecta a la extracción, y el motor determinista recalcula.],
  consecuencias: [El lote avanza mientras el humano duerme; coste marginal solo en las páginas difíciles, cacheado por página para no re-facturar. La calidad depende de un proveedor externo, cuyos fallos (429, timeouts) degradan sin parar y se reflejan en Salud.],
  evidencia: [DRILLS MEDIDOS (`.sdd/metrics/drills.json`, T12): `rung5-provider-caido` PASS — el proveedor no responde tras 3 intentos y la página entra en cola de revisión con motivo en evidencia, el lote sigue; `backoff-429` PASS — Retry-After respetado, 0 llamadas extra. Cola de revisión en la UI con imagen de página junto a cada lectura candidata y desacuerdo resaltado (T5/T7); overrides encolados con provenance en `.sdd/review-queue/`; números de la cola de revisión de la corrida real: PENDIENTE-MEDICIÓN(T14). Decisión registrada en `docs/decisiones/DECISIONS.md` y AGENTS §13.],
)

#adr([Selección de candidato con provenance — evaluar TODOS los candidatos del campo (ADR-06)],
  status: "ACEPTADA",
  contexto: [El parser conserva TODOS los candidatos de cada campo (doctrine §2), pero las facturas traen líneas «Subtotal» y «TOTAL A PAGAR»: ambos son candidatos del campo `total`. La auditoría del lote 1 real (T17) midió que el motor colapsaba `values[]` con el PRIMER candidato (el Subtotal) y lo comparaba contra el importe CON IVA del maestro: 87 de los 108 NO_PAGAR eran FALSOS (un candidato de total sí matcheaba con tolerancia 0,01), 14 genuinos. Colapsar sin registrar cuál se eligió y por qué viola §2 y producía NO_PAGAR definitivos con desacuerdo de evidencia — que por §6 deberían escalar, nunca pagar ni bloquear por un artefacto.],
  alternativas: [1er candidato (comportamiento previo, bug); candidato de máxima confianza global (la confianza es del EXTRACTOR, no de qué línea es); cualquiera-matchea sin provenance; escalar siempre que haya varios candidatos (todo el corpus con Subtotal+TOTAL escalaría: coste humano injustificado cuando los candidatos concuerdan).],
  decision: [Las reglas que comparan un campo contra el maestro (`ORDER_AMOUNT_MATCHES`, `TOTALS_MUST_MATCH`, `IVA_CONSISTENT`, `IBAN_MATCHES_MASTER`) evalúan TODOS los candidatos del campo: exactamente uno matchea dentro de tolerancia ⇒ PASS citando ESE candidato (provenance extractor + value + feature_ref en `consumed`); varios matchean ⇒ PASS con nota de ambigüedad benigna (concuerdan entre sí); ninguno ⇒ FAIL (los genuinos no cambian). PROHIBIDO que un PASS previo pase a FAIL por este cambio. Motor `runner-1.1.0`.],
  consecuencias: [Los falsos NO_PAGAR desaparecen sin tocar extracción ni política (cambio solo en el colapso del motor); cada veredicto registra el candidato elegido y los desacuerdos, alimentando Revisión e Impacto; el NO_PAGAR definitivo se reserva para violaciones reales, como exige §6. Riesgo controlado: la evaluación de varios candidatos es O(n) por campo, coste medido en el reprocesado del lote.],
  evidencia: [Auditoría T17 (`.sdd/metrics/auditoria-trampas.md`): 87/108 falsos con la firma exacta (candidato [1409.4, 1705.37], maestro 1705.37); reprocesado del lote 1 con diff medido `.sdd/metrics/impacto-fix-colapso.json` — 87 NO_PAGAR→PAGAR, 14 genuinos se mantienen NO_PAGAR, 0 regresiones; tests del motor con candidatos Subtotal+TOTAL, ninguno y varios matcheando (T18).],
)

#adr([App de escritorio multiplataforma: pywebview, NO Electron (ADR-07)],
  status: "ACEPTADA",
  contexto: [El requisito del usuario: que funcione también en Windows y Mac, con integración de app «tipo Electron o similar». Alberto usa la app desde Linux, pero la demo debe portarse a otros escritorios.],
  alternativas: [Electron (runtime ~200 MB, toolchain Node adicional, empaquetado por OS); PWA sola (requiere navegador abierto); app nativa por OS (tres codebases).],
  decision: [pywebview aloja la misma UI Vue que el navegador. FastAPI arranca en un hilo sobre loopback y puerto efímero. La UI solicita modo local/servidor y configura los endpoints sin duplicar el motor de reglas.],
  consecuencias: [La ventana es opcional, pero Node es requerido por PouchDB. La misma UI sirve a navegador y ventana con selección de modo al inicio. La distribución firmada por OS requiere verificación específica; el bloqueo actual de persistencia usa fcntl en Linux.],
  evidencia: [src/filemaid/desktop/app.py comparte create_app con el servidor local; tests/test_engines_desktop.py cubre el arranque y la selección de backend de ventana. La verificación de la UI web se hace contra el mismo frontend construido.],
)

#adr([Resultado configurable por regla: `outcomes.on_fail` (FAIL → NO_PAGAR/ESCALAR) (ADR-08)],
  status: "ACEPTADA",
  contexto: [La doctrina §6 fija que un `FAIL` es un negativo definitivo y un `UNKNOWN` es duda razonable, pero no toda regla incumplida debe descartar la factura para siempre: un NIF o un IBAN que no cruzan con el maestro pueden ser un proveedor nuevo que un humano sí puede admitir. Con la frontera cableada en el motor (`FAIL ⇒ NO_PAGAR`), atender ese caso exigía excepciones por regla en código, justo lo que la arquitectura prohíbe (política como DATOS).],
  alternativas: [Excepciones hardcodeadas por regla en el motor (toca código por cada matiz de política); un único flag global (no permite que unas reglas escalen y otras no); dejar todo `FAIL ⇒ NO_PAGAR` (bloquea definitivamente proveedores legítimos y llena de falsos negativos la cola humana); cualquier veredicto, incluido `PAGAR`, al gusto (peligroso: una regla rota jamás debe pagar).],
  decision: [`outcomes.default` (por defecto `NO_PAGAR`) y `outcomes.on_fail.<RULE_CODE>` (`NO_PAGAR` o `ESCALAR`) en `rules.yaml`, configuración versionada. El motor resuelve cada `FAIL` al resultado configurado para su regla; `PAGAR` queda prohibido y la carga de la config lo rechaza con `ValueError`. La agregación resultante (algún FAIL→NO_PAGAR ⇒ NO_PAGAR; si no, FAIL→ESCALAR/UNKNOWN/sin reglas ⇒ ESCALAR; si no ⇒ PAGAR) conserva el determinismo y la pureza. El snapshot de cada decisión incluye `rule_outcomes` (resultado resuelto por regla), y el informe/API lo exponen. Se configura `NIF_IN_MASTER` e `IBAN_MATCHES_MASTER` como `ESCALAR`; el resto sigue `NO_PAGAR`.],
  consecuencias: [La frontera `NO_PAGAR`/`ESCALAR` pasa a ser DATOS auditables por decisión sin tocar código; reproducir por qué un `FAIL` escaló o no es posible desde el snapshot. El coste humano sube donde se elige escalar (los proveedores fuera de maestro ya no se descartan en solitario) — decisión consciente y reversible por config. El default `NO_PAGAR` mantiene estable el comportamiento de las reglas no declaradas.],
  evidencia: [Tests (tests/test_rules_engine.py): `on_fail` configurable ⇒ FAIL escala; sin config ⇒ NO_PAGAR; `PAGAR` y un default inválido son rechazados; el snapshot incluye `rule_outcomes`. test_report.py: un `FAIL→ESCALAR` aparece como driver de `ESCALAR` con leyenda «FAIL→ESCALAR», no como negativo definitivo. Artefactos: `master/rules.yaml`, `config.py`, `engine.py`, `report.py`, `api/app.py`.],
)

