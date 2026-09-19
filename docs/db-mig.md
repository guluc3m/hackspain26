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
| `rules/report.py`, `run.py` | `index.html`, `facturas/<uuid>.html`, `detalle.jsonl`, `outcomes.jsonl`; resumen de conteos y latencias impreso en CLI, derivable de decisiones conservadas. |
| `frontend/src/api.ts`, `views/LogsView.vue`, `InvoiceTable.vue`, `desktop/app.py` | La conexión real y los motores del puente estaban sin implementar; el visor filtraba datos sintéticos por factura y tipo, con botón «logs». No había logs de UI reales que migrar. Se conecta el visor al backend real; los targets `*_syncth` conservan su función de demo. |

No se guardan claves, cabeceras Authorization ni el diccionario runtime de configuración que contiene secretos. Los payloads del documento/proveedor son datos no confiados, no instrucciones. No se altera la frontera `NO_PAGAR`/`ESCALAR`.

## Motor y seam

PouchDB JS 9 local, adaptador LevelDB, en `FILEMAID_DATA/pouchdb`. Python ejecuta un puente Node finito por operación bajo un bloqueo interproceso que abarca apertura hasta cierre. No hay servidor CouchDB, MongoDB ni fallback. PouchDB es la única persistencia runtime, incluida caché, logs y configuración; no se crean bases SQLite ni ledgers JSONL. Los JSONL de resultados son exports, no almacenamiento interno. Las imágenes y copias de trabajo son descartables y recuperables desde los adjuntos.

Modo standalone: PouchDB local y VLM local o endpoint explícito. Modo servidor: la misma base local intercambia documentos y adjuntos con otro PouchDB mediante el servicio FastAPI; el servicio también aloja el escalador VLM. La UI exige elegir modo al arrancar y permite reconfigurarlo. No se añaden prompts al procesamiento batch.

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
| local | `_local/runtime-settings` | modo, URL sync, URL VLM y modelo. Configuración específica del dispositivo; nunca se replica. |

Campos JSON/texto hasta 256 KiB se guardan inline. Valores mayores se serializan en UTF-8 JSON (o bytes, sin `repr`) y se sustituyen por referencia a artifact (`payload_ref`, con encoding). La lectura los reconstruye. Fragmentación evita cargar PDFs enteros en el canal IPC base64; se comprueban SHA-256 y longitud al leer. Cada artifact se publica solo después de sus blobs. Adjuntos huérfanos tras un crash son inocuos; no se purgan automáticamente porque podrían pertenecer a trabajo en curso.

Los sobres offloaded conservan `type`, `stage`, `page`, `run_id`, `fields_id` cuando existen, y `result` para decisiones; son metadatos de consulta, no un segundo resultado. Las respuestas HTTP se archivan como bytes originales, incluidas respuestas inválidas o de error, sin reinterpretar NaN ni ocultar el fallo de persistencia. Nunca se adjuntan cabeceras de autenticación.

## Consultas, índices y acceso

Índice primario `_id`: `allDocs` por prefijo para tipos y scans. Vista versionada `_design/trace-v1`, `by_file`: clave `[file_id, kind, timestamp, _id]`; `by_invoice`: `[invoice_id, kind, timestamp, _id]`. Las consultas esperan actualización (nunca `stale=ok` ni `update_after`). Las lecturas de detalle usan claves exactas; el filtro de logs por factura usa basename exacto, no coincidencia parcial. Logs con texto libre y paginación se filtran después de recuperar referencias de eventos, no blobs.

FastAPI expone trazas y artefactos, además del contrato de facturas/logs que consume Vue. El botón «logs» conserva el basename; el detalle usa file_key para evitar la ambigüedad del UUID antiguo. El visor muestra IDs/referencias y resúmenes; artefactos solo se descargan bajo petición. Desktop usa el mismo FastAPI local para la conexión real, sin replicar PouchDB en el navegador.

El reprocesado acepta `file_key` y rechaza con 409 un basename ambiguo; restaura el original desde adjuntos PouchDB con reemplazo atómico. Los logs siguen agrupando por basename exacto por contrato del visor. Las reglas de revisión/override preexistentes no se rediseñan en esta migración.

## Inmutabilidad, fallos y conflictos

Nunca se actualiza ni borra un documento de dominio; `_rev` no es histórico de negocio. Reprocesar crea nuevo scan y nueva decisión. Repetir un `put` del mismo `_id` y contenido es idempotente; un 409 con contenido distinto es error, nunca last-write-wins. Todos los resultados individuales se esperan; no se interpreta un `bulkDocs` HTTP exitoso como éxito de cada fila. No se ofrece edición de `_rev`, `new_edits=false`, borrado ni replicación desde la API.

La vista se versiona, no se muta sobre lecturas en vuelo. Se rechazan lecturas con `_conflicts`; replicación externa/manual no está soportada y requiere reconciliación explícita sin borrar decisiones. Compaction no elimina historia porque cada decisión es un documento independiente.

Los escalones se guardan al terminar, antes de iniciar el siguiente. Si falla una página posterior, las páginas/escalones anteriores permanecen. El original se captura antes de extracción; las imágenes se aíslan por scan. La decisión se publica después de fields/evidencia y nunca se sobrescribe. Una caída del servidor deja la evidencia local disponible para sincronizar más tarde; los errores de sincronización se muestran, no se transforman en decisiones.

## Instalación y operación

Desde el repositorio: `uv run -- npm ci --prefix src/filemaid/store/pouchdb`, después `uv run filemaid serve` (app) o `uv run filemaid server` (sync + VLM). Node >=20 en PATH. Estado y temporales bajo FILEMAID_DATA, nunca `/tmp`. Backup: detener escritores y copiar el directorio PouchDB completo. `clean` solo elimina workspaces descartables; no elimina la base ni la caché persistida.

### Verificación de la migración

`tests/test_pouch_persistence.py`, `test_pouch_boundaries.py`, `test_pouch_identity.py` ejercitan el motor JS real: aliases, recuperación sin fichero original, fragmentación concurrente, colisiones, payloads grandes, degradación explícita, fallo parcial y enlace exacto de informes/reprocesado. Revisión adversarial adicional: conflictos de revisiones introducidos externamente, límites exactos y bloqueo entre procesos. No se promete replicación externa automática.

Referencias: [PouchDB API](https://pouchdb.com/api.html), [conflictos y append-only](https://pouchdb.com/guides/conflicts.html). Sin dependencia de un servidor CouchDB.
