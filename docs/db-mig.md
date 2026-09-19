# Persistencia de ingestión en PouchDB

## Inventario del código (antes de implementar)

| Productor | Salida real que se conserva |
| --- | --- |
| `pipeline.py:process_pdf`, `run_lote` | PDF/imagen original, basename exacto (`file_id`), SHA-256, UUID derivado del contenido; eventos `invoice_seen`, `decision`, `item_error`; latencias `extraction_ms`, `parser_ms`, `evaluation_ms`, `total_ms` y mapa `timings` por escalón/página. |
| `extract/ladder.py` | Cada `PageExtraction`: `page`, `content`, `stopped_at`, lista ordenada de features; cada salida de escalón, incluso `skipped:*`. |
| `extract/rungs/text_layer.py` | Texto pypdf, incluido texto rechazado por plausibilidad. |
| `extract/rungs/qr.py` | PNG `pN.png`, hash de imagen, feature `page_image`, lista de payloads QR, confianza. |
| `extract/rungs/tesseract.py` | Actualmente caché o `skipped:stub`/dependencia ausente; no se inventa una salida OCR. |
| `extract/rungs/vlm_local.py` | Lectura seleccionada, confianza, hash, versión, latencia; internamente también produce PNG mejorado y lectura del reintento. Estos intermedios se capturan sin convertirlos en candidatos adicionales. |
| `extract/rungs/typesafe_jev.py` | Respuesta JSON completa: modelo, respuestas tipadas, probabilidades y `usage`; no es una decisión de pago. |
| `extract/rungs/firecrawl.py` | PDF mon página enviado y respuesta JSON con Markdown; feature con Markdown seleccionado y confianza. |
| `extract/rungs/cloud_vlm.py` | Respuesta OpenAI-compatible y feature textual; ni token usage ni modelos se fabrican cuando el proveedor no los entrega. |
| `extract/cache.py` | Feature serializada; clave `(page_sha256, extractor_version, config_version)`; los hits también son evidencia del scan actual. |
| `parse/parser.py`, `parse/extractors.py` | Lista completa de `ExtractionField(type, timestamp, values[])`; cada candidato mantiene extractor, valor y confianza, sin colapso ni deduplicación adicional. |
| `rules/engine.py`, `types.py` | `Decision` completa: resultado, lista de `RuleEvaluation` con `consumed`, `chosen_candidates`, `reason_code`, snapshot de umbrales/versiones/master/outcomes y timings. Motor sin cambios. |
| `store/pouch.py`, `store/trace.py`, `api/app.py` | Única persistencia PouchDB: evidencia, candidatos, decisiones, caché, eventos y overrides con antes/después/quién/escalón/motivo. Sin proyección relacional ni ledger externo. |
| `rules/report.py`, `run.py` | `index.html`, `facturas/<uuid>.html`; `outcomes.jsonl`/`outcomes_lote2.jsonl` como export final atómico desde PouchDB; resumen de conteos y latencias impreso en CLI, derivable de decisiones conservadas. |
| `frontend/src/api.ts`, `views/LogsView.vue`, `InvoiceTable.vue`, `desktop/app.py` | La conexión real y los motores del puente estaban sin implementar; el visor filtraba datos sintéticos por factura y tipo, con botón «logs». No había logs de UI reales que migrar. Se conecta el visor al backend real; los targets `*_syncth` conservan su función de demo. |

No se guardan claves, cabeceras Authorization ni el diccionario runtime de configuración que contiene secretos. Los payloads del documento/proveedor son datos no confiados, no instrucciones. No se altera la frontera `NO_PAGAR`/`ESCALAR`.

## Motor y seam

PouchDB JS 9 local, adaptador LevelDB, en `FILEMAID_DATA/pouchdb`. Python ejecuta un puente Node finito por operación bajo un bloqueo interproceso que abarca apertura hasta cierre. En el cliente no se instala ni ejecuta un servidor CouchDB local. PouchDB es la única persistencia runtime local, incluida caché, logs y configuración; no se crean bases SQLite ni ledgers JSONL. Los JSONL de resultados son exports, no almacenamiento interno. Las imágenes y copias de trabajo son descartables y recuperables desde los adjuntos.

Modo standalone: PouchDB local y VLM local o endpoint explícito. Modo servidor: la base local PouchDB sincroniza directamente con una base de datos remota Apache CouchDB existente (proporcionada por el usuario o infraestructura, ej. `http://couchdb:5984/facturas`) mediante la replicación nativa de PouchDB (`PouchDB.sync`). El servicio opcional `filemaid server` aloja exclusivamente el escalador VLM (sin endpoints de sincronización). La UI exige elegir modo al arrancar y permite reconfigurarlo. No se añaden prompts al procesamiento batch.

Exports e informes se enlazan por `scan_id`, nunca por basename ni por «última factura». El histórico previo PouchDB permanece legible. Los antiguos ficheros relacionales no se abren ni borran automáticamente; no se reconstruye evidencia que nunca se guardó. El puente finito favorece aislamiento frente a throughput masivo.

## Documentos dinámicos

Metadatos nuevos exclusivamente de persistencia: `kind`, `file_key`, `scan_id`, `timestamp` de recepción y referencias de adjuntos. Los valores de dominio se copian de los productores anteriores.

Estas formas son convenciones de los productores actuales, no tablas ni una lista cerrada de tipos. La sincronización conserva campos y tipos desconocidos. Las únicas restricciones transversales son identificadores, inmutabilidad, límites de transporte e integridad de adjuntos; las decisiones de dominio siguen limitadas a los tres resultados válidos.

`file_key = sha256(UTF8(JSON([file_id, sha256])))`, sin normalizar Unicode, mayúsculas, espacios ni extensión. `file_id = Path.name` exacto. Dos nombres con mismos bytes y un mismo nombre con bytes distintos son identidades separadas. El `invoice_id` antiguo (UUID del hash) se mantiene como enlace de compatibilidad, nunca como clave única de fichero. `scan_id` es UUID aleatorio por ejecución/reprocesado; `run_id` conserva la versión de reglas existente.

| `kind` | `_id` | Contenido / enlaces |
| --- | --- | --- |
| `file` | `file:<file_key>` | `file_id`, `file_key`, `invoice_id`, `sha256`; inmutable. |
| `scan` | `scan:<file_key>:<scan_id>` | identidad anterior, source_path, config_version, extraction_config_version, master_sha256, timestamp. Inicio inmutable; finalización se acredita por documento decision o item_error. |
| `artifact` | `artifact:<scan_id>:<UUID>` | identidad del scan, stage, nombre, media_type, sha256, size, chunks (IDs ordenados de blob). PDF original, PNG, intermedios, informes y exports. |
| `blob` | `blob:<sha256_del_fragmento>` | `_attachments.data` binario, máximo 1 MiB; compartido por contenido. Se enlaza al fichero mediante artifact, no mediante rutas externas. |
| `feature` | `feature:<scan_id>:<page>:<rung>:<ordinal>` | identidad del scan, stage (nombre real del escalón), página contenedora y feature completa bajo `feature`. `feature.page` se conserva incluso si el productor lo dejó null. |
| `page` | `page:<scan_id>:<page>` | content, stopped_at y referencias de features; no imágenes inline. |
| `fields` | `fields:<scan_id>` | lista completa bajo `fields`; parser_ms. |
| `decision` | `decision:<scan_id>` | `Decision` completa bajo `decision`, run_id, identidad y timestamp. Solo PAGAR/NO_PAGAR/ESCALAR. Referencia fields y scan. |
| `event` | `event:<scan_id>:<UUID>` | `type` y `payload` (`invoice_seen`, `decision`, `item_error`, `feature`, `fields`, `override`) con referencia a su documento/fichero. |
| `cache` | clave determinista de página, motor y configuración | Feature reutilizable completa; almacenada en PouchDB y recuperable tras reinicio. |
| `batch` | `batch:<batch_id>` | pertenencia estable del lote: `lote`, `expected` (basenames exactos), `run_id`, `extraction_config_version`, `master_sha256`, `started_at`. Inmutable. |
| `batch_item` | `batch_item:<batch_id>:<file_key>` | asociación durable por factura: `file_id`, `file_key`, `scan_id`, `decision_id`, `timestamp`. Inmutable; es el progreso reanudable. |
| `batch_result` | `batch_result:<batch_id>` | finalización: `status: complete`, `expected`, `decisions` (IDs ordenados), `finished_at`. Solo existe cuando todas las facturas esperadas tienen decisión. |
| local | `_local/runtime-settings` | modo, URL sync, URL VLM y modelo. Configuración específica del dispositivo; nunca se replica. |

Campos JSON/texto hasta 256 KiB se guardan inline. Valores mayores se serializan en UTF-8 JSON (o bytes, sin `repr`) y se sustituyen por referencia a artifact (`payload_ref`, con encoding). La lectura los reconstruye. Fragmentación evita cargar PDFs enteros en el canal IPC base64; se comprueban SHA-256 y longitud al leer. Cada artifact se publica solo después de sus blobs. Adjuntos huérfanos tras un crash son inocuos; no se purgan automáticamente porque podrían pertenecer a trabajo en curso.

Los sobres offloaded conservan `type`, `stage`, `page`, `run_id`, `fields_id` cuando existen, y `result` para decisiones; son metadatos de consulta, no un segundo resultado. Las respuestas HTTP se archivan como bytes originales, incluidas respuestas inválidas o de error, sin reinterpretar NaN ni ocultar el fallo de persistencia. Nunca se adjuntan cabeceras de autenticación.

## Consultas, índices y acceso

Índice primario `_id`: `allDocs` por prefijo para tipos y scans. Vista versionada `_design/trace-v1`, `by_file`: clave `[file_id, kind, timestamp, _id]`; `by_invoice`: `[invoice_id, kind, timestamp, _id]`. Las consultas esperan actualización (nunca `stale=ok` ni `update_after`). Las lecturas de detalle usan claves exactas; el filtro de logs por factura usa basename exacto, no coincidencia parcial. Logs con texto libre y paginación se filtran después de recuperar referencias de eventos, no blobs.

FastAPI expone trazas y artefactos, además del contrato de facturas/logs que consume Vue. El botón «logs» conserva el basename; el detalle usa file_key para evitar la ambigüedad del UUID antiguo. El visor muestra IDs/referencias y resúmenes; artefactos solo se descargan bajo petición. Desktop usa el mismo FastAPI local para la conexión real, sin replicar PouchDB en el navegador.

El reprocesado acepta `file_key` y rechaza con 409 un basename ambiguo; restaura el original desde adjuntos PouchDB con reemplazo atómico. Los logs siguen agrupando por basename exacto por contrato del visor. Las reglas de revisión/override preexistentes no se rediseñan en esta migración.

## Inmutabilidad, fallos y conflictos

Nunca se actualiza ni borra un documento de dominio; `_rev` no es histórico de negocio. Reprocesar crea nuevo scan y nueva decisión. Repetir un `put` del mismo `_id` y contenido es idempotente; un 409 con contenido distinto es error, nunca last-write-wins. Todos los resultados individuales se esperan; no se interpreta un `bulkDocs` HTTP exitoso como éxito de cada fila. No se ofrece edición de `_rev`, `new_edits=false`, borrado ni replicación desde la API.

La vista se versiona, no se muta sobre lecturas en vuelo. Se rechazan lecturas con `_conflicts`. La sincronización soportada es la replicación nativa PouchDB <-> CouchDB descrita abajo. Los conflictos nativos de CouchDB nunca se fusionan silenciosamente: cualquier conflicto detiene el flujo o se marca como error (fail-closed). Compaction no elimina historia porque cada decisión es un documento independiente.
Los escalones se guardan al terminar, antes de iniciar el siguiente. Si falla una página posterior, las páginas/escalones anteriores permanecen. El original se captura antes de extracción; las imágenes se aíslan por scan. La decisión se publica después de fields/evidencia y nunca se sobrescribe. Una caída del servidor deja la evidencia local disponible para sincronizar más tarde; los errores de sincronización se muestran, no se transforman en decisiones.

## Lotes reanudables y export final

`filemaid run` procesa un directorio y su pertenencia/progreso viven en PouchDB, no en memoria. El `batch_id` es determinista: `uuid5` sobre `{lote absoluto, run_id, extraction_config_version, master_sha256, [[file_id, sha256]…]}`. Repetir el mismo comando reanuda el mismo lote en lugar de duplicarlo; cambiar reglas, config de extracción, maestro o el contenido de un fichero produce un lote nuevo.

Cada factura decidida publica un `batch_item` inmutable que asocia `file_key`→`scan_id`→`decision_id`. Al reanudar, un item con decisión persistida se reutiliza (no se re-extrae); el resto se procesa. La salida final `outcomes.jsonl` (o `outcomes_lote2.jsonl`) se escribe de forma atómica (temp único + rename) **solo** cuando existe `batch_result`, es decir, cuando todas las facturas esperadas tienen decisión y el conjunto de basenames coincide exactamente con `expected` (sin duplicados, sin omisiones, solo PAGAR/NO_PAGAR/ESCALAR). Un fallo deja el lote incompleto, sin `batch_result` y sin artefacto final; el comando termina con error y muestra el `batch_id` para reanudar.

`filemaid emit [--batch-id]` re-emite desde el store el lote indicado (por defecto el último); si el lote está incompleto falla en lugar de emitir un artefacto parcial o mezclado. El export final se archiva una sola vez por lote como artifact (`artifact:batch-<batch_id>:…`), nunca una copia por scan. La sincronización remota es best-effort: un fallo de red no descarta la decisión local ni hace fallar el comando; el estado queda pendiente y se reintenta.

## Sincronización nativa con CouchDB y servicio VLM

La sincronización entre dispositivos delega en el protocolo de replicación nativo de CouchDB a través de `PouchDB.sync(remote_url)`.

### Requisitos y permisos de la base remota CouchDB
1. **Base de datos remota preexistente**: La base remota en CouchDB (p. ej. `http://couchdb:5984/facturas`) debe existir previamente y ser aprovisionada por el administrador/usuario. La aplicación cliente no aprovisiona automáticamente bases en CouchDB en producción.
2. **Permisos requeridos**: El usuario o token de replicación necesita permisos de lectura y escritura de documentos, así como gestión de checkpoints `_local/*` para mantener el estado de la replicación entre ejecuciones.
3. **Protección del histórico remoto**: para mantener la garantía append-only también frente a escritores externos, el administrador debe restringir actualizaciones/borrados mediante permisos y una validación `validate_doc_update` apropiada. La aplicación local nunca edita decisiones; la replicación nativa sí transporta revisiones y tombstones válidos de CouchDB y no sustituye esa política remota.
4. **Manejo de conflictos**: El protocolo nativo de replicación gestiona automáticamente árboles de revisiones (`_rev`), adjuntos y checkpoints. Los documentos `_local` se excluyen de la sincronización pública automáticamente por CouchDB, y los documentos `_design` se excluyen mediante filtros de cliente. Los conflictos detectados nunca se fusionan de forma silenciosa ni se aplica last-write-wins; la detección de conflictos opera en modo fail-closed para proteger la integridad de las decisiones.

La aplicación ejecuta intercambios finitos con `live:false`, `retry:false`, lotes de 16 y un lote en memoria. Conserva la sincronización periódica/manual y posterior a los scans. Los checkpoints y secuencias opacas son gestionados por PouchDB; no hay cursores ni protocolo de replicación propios. Errores de autorización por documento (`denied`) cancelan el intercambio y se reportan como error, permitiendo reintento tras corregir los permisos. Se comprueban conflictos locales al terminar y en las lecturas; las ramas en conflicto se conservan para resolución explícita. La replicación es atómica por documento, no por scan completo: una interrupción puede dejar evidencia parcial hasta el siguiente intento.

### Autenticación con CouchDB
El acceso a la base CouchDB remota se autentica mediante:
- Credenciales básicas vía variables de entorno: `FILEMAID_COUCHDB_USER` y `FILEMAID_COUCHDB_PASSWORD`.
- O alternativamente cabecera Bearer con `FILEMAID_SYNC_TOKEN`.
- No se persisten credenciales en la configuración local `_local/runtime-settings` ni en documentos sincronizados.

### Servicio VLM independiente (`server.py`)

`filemaid server` es Linux-only (guard en `run.py` y `start.py`) y aloja exclusivamente el escalador VLM local (`/v1/chat/completions`), sin rutas `/sync/*`. No existe modo de upstream remoto: al arrancar aprovisiona (instala + arranca + health-check) el sidecar local PaddleOCR-VL Q8 (llama.cpp) y **rechaza servir si no está listo** (el lifespan falla).

Límites y operación VLM:
- Acepta multimodal OpenAI-compatible en `/v1/chat/completions`, cuerpo hasta 24 MiB, respuesta hasta 2 MiB, máximo cuatro peticiones simultáneas y timeout de 120 s. Streaming de tokens no soportado.
- Autenticación mediante `FILEMAID_SERVER_TOKEN`: obligatoria para acceso no-loopback (fail-closed 403 si falta); en loopback sin token se permite. El cliente con endpoint VLM dedicado usa `FILEMAID_VLM_KEY`.
- El endpoint VLM es independiente de la URL de CouchDB: nunca se deduce de ella.

En el cliente, el modo standalone usa el VLM local; el modo servidor exige un endpoint VLM remoto explícito; el fallback local es opcional según la configuración guardada.
## Instalación y operación

Desde el repositorio: `uv run -- npm ci --prefix src/filemaid/store/pouchdb`, después `uv run filemaid serve` (app) o `uv run filemaid server` (escalador VLM). Node >=20 en PATH. Estado y temporales bajo FILEMAID_DATA, nunca `/tmp`. Backup: detener escritores y copiar el directorio PouchDB completo. `clean` solo elimina workspaces descartables; no elimina la base ni la caché persistida.

### Verificación de la persistencia y replicación

`tests/test_pouch_persistence.py`, `test_pouch_boundaries.py`, `test_pouch_identity.py` ejercitan el motor JS real: aliases, recuperación sin fichero original, fragmentación concurrente, colisiones, payloads grandes, fallo parcial y enlace exacto de informes/reprocesado. `test_pouch_persistence.py` cubre además los lotes reanudables: un fallo deja el lote incompleto sin salida final, re-ejecutar reutiliza las decisiones persistidas (sin re-extraer) y emite un único `outcomes.jsonl` con los campos exactos; un fallo de sincronización remota no descarta la decisión local. Las pruebas de sincronización cubren la replicación nativa PouchDB <-> CouchDB, autenticación y manejo de checkpoints/conflictos; `test_runtime_settings.py` y `test_startup_choice.py` cubren configuración local y elección de modo.

Para ejecutar las pruebas contra Apache CouchDB real: configure `FILEMAID_TEST_COUCHDB_URL` con la URL raíz de un servidor de pruebas aislado, `FILEMAID_TEST_COUCHDB_USER` y `FILEMAID_TEST_COUCHDB_PASSWORD`, y ejecute `uv run pytest tests/test_couchdb_replication.py`. Cada prueba crea y elimina una base de nombre aleatorio. Sin esas variables, las pruebas de integración remota se omiten explícitamente; no se reemplaza CouchDB por un simulador ni se inicia uno en el cliente.

Referencias: [PouchDB API](https://pouchdb.com/api.html), [conflictos y replicación CouchDB](https://pouchdb.com/guides/conflicts.html). El cliente no requiere instalación local de CouchDB.
