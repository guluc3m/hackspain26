# filemaid

Sistema de decisión para las facturas de Alberto: lee PDFs, extrae campos y decide
si cada factura se puede pagar — `PAGAR`, `NO_PAGAR` o `ESCALAR` — con evidencia
y trazabilidad en cada paso.

```
PDF ──▶ EXTRACCIÓN ──▶ FEATURES ──▶ PARSER ──▶ CAMPOS ──▶ MOTOR DE REGLAS ──▶ RESULTADO
                                                               │
                                                     evidencia + config ──▶ STORE ──▶ UI
```

## Estructura

```
src/filemaid/
  types.py          contrato: ExtractionFeature, ExtractionField, Decision...
  config.py         rutas de estado (data/, nunca /tmp) y config de extracción
  pipeline.py       worker: lote idempotente y resumable (clave: sha+stage+version+config)
  run.py            CLI: run | emit | serve | reprocess | clean
  engines/          los dos motores de la arquitectura (llamadas sin definir)
    extraction.py   bloque de extracción: features -> campos (extract/ + parse/)
    decision.py     bloque de decisión: campos -> resultado (rules/)
  desktop/          ventana nativa (pywebview): puente JS -> motores
  extract/          escalera de 7 escalones por página, cache y plausibilidad
    rungs/          1 texto (pypdf) · 2 raster+QR (pypdfium2+zxing) · 3 tesseract
                    4 VLM local (llama-server, temp 0) · 5 TypeSafe (solo juicios)
                    6 Firecrawl · 7 VLM cloud (solo candidato)
  parse/            features → campos: todos los candidatos se conservan
  rules/            motor puro y determinista + 8 reglas + maestros (CSV/Excel)
  store/            PouchDB JS local: datos, adjuntos, caché, eventos y configuración
  api/              FastAPI: comparte types, store y motor con el pipeline
  server.py         escalador y servicio VLM remoto dedicado (sin sincronización)
master/             datos maestros y thresholds de reglas (versionados)
frontend/           Vue 3 + Vite (TS, pnpm): Dashboard (cola de revisión),
                    Invoices (facturas + carpeta) y Logs (buscador de entradas,
                    filtrables por factura desde cada fila)
```

TypeSafe (`jev-latest`, escalón 5) evalúa el texto disponible de la página con
preguntas `noul`, `score` y `choice`. Conserva respuestas, modelo y uso como
`typed_evidence`: no genera OCR, no convierte probabilidades en campos de factura,
no autoriza pagos y nunca detiene el respaldo de Firecrawl. Sin clave o sin texto
previo se omite explícitamente; una imagen en base64 no equivale a píxeles leídos
por este servicio. Los indicios OCR son locales a cada página, incluso si su
confianza es baja. El endpoint y modelo explícitos de `rungs.typesafe_jev` priman
sobre los defaults globales. La llamada real debe verificarse con credenciales;
esta descripción no afirma una ejecución en vivo exitosa.
La caché identifica página, motor y configuración; si cambia el OCR previo de una
misma página sin cambiar la configuración, el juicio cacheado puede quedar obsoleto.

## Uso

```sh
uv sync                              # entorno (Python 3.13, user-space)
uv run -- npm ci --prefix src/filemaid/store/pouchdb  # motor PouchDB; requiere Node >=20
uv run filemaid run --lote caja-de-alberto/facturas --out outcomes.jsonl
uv run filemaid emit               # re-emite outcomes desde el store
uv run filemaid serve              # API de revisión
uv run filemaid server             # servicio VLM remoto dedicado, puerto 8001
uv run pytest                        # tests
uv run ruff check src tests          # lint
uv run -- npx pnpm --dir frontend install
uv run -- npx pnpm --dir frontend build   # UI real, servida por FastAPI
uv run -- npx pnpm --dir frontend dev_syncth  # demo sintética opcional
uv sync --extra desktop              # pywebview para la ventana nativa
uv run albertitos-desktop            # ventana nativa con la misma UI
```

### Modo sintético y UI

La ventana nativa sirve el front construido (`frontend/dist`) mediante el mismo
FastAPI local que la versión web, en un puerto loopback asignado por el SO.
El puente histórico `extraer`/`decidir` no participa en esta conexión.
En desarrollo: `ALBERTITOS_UI_URL=http://127.0.0.1:5173 uv run albertitos-desktop`.

El lanzador fuerza el backend QT cuando está disponible (sin sondeo GTK).
Las sondas del sistema que escriben en stderr durante el arranque (Vulkan
«Failed to detect any valid GPUs», libva) se capturan y se descartan; solo se
muestran como diagnóstico si la ventana no llega a abrirse. En máquinas con
ICD de Vulkan instalados (p. ej. mesa-vulkan-drivers, paquete del sistema)
la sonda ni siquiera se produce.

La UI real consulta facturas, decisiones y logs persistidos en PouchDB. El botón
«logs» aplica un filtro por basename exacto; los detalles conservan todos los
candidatos. `uv run filemaid serve` sirve la API y `frontend/dist`.
Los targets `*_syncth` siguen disponibles para la demo sin datos reales.

La UI pregunta **Standalone** o **Servidor** en cada arranque. Configuración
permite editar la URL completa de la base de datos CouchDB remota (ej. `http://couchdb:5984/facturas`),
el endpoint VLM (base OpenAI-compatible `/v1`, independiente de CouchDB; en blanco usa el sidecar local)
y modelo. Los valores se guardan únicamente en PouchDB local; no se replican.
En modo servidor, la confirmación realiza una sincronización PouchDB<->CouchDB nativa y los cambios
se sincronizan periódicamente y tras los scans. El cliente usa PouchDB LevelDB local sin instalar ni requerir
CouchDB localmente. Un fallo mantiene los datos locales y muestra el error; no sustituye el resultado de las reglas.

### Sincronización con CouchDB y servicio VLM

La sincronización entre dispositivos se realiza mediante replicación nativa PouchDB a una base de datos remota Apache CouchDB existente (proporcionada por el usuario o infraestructura central, ej. `http://couchdb:5984/facturas`).
El cliente no requiere instalar CouchDB localmente: PouchDB (LevelDB) gestiona la persistencia local y replica bidireccionalmente contra CouchDB.

Para autenticación con CouchDB:
- Variables de entorno de credenciales básicas: `FILEMAID_COUCHDB_USER` y `FILEMAID_COUCHDB_PASSWORD`.
- O alternativamente token Bearer: `FILEMAID_SYNC_TOKEN`.

Para el servicio VLM (`server.py`), el comando `filemaid server` aloja exclusivamente el escalador VLM:
```sh
FILEMAID_DATA=data/servidor uv run filemaid server --host 127.0.0.1 --port 8001
```
En el servidor VLM, configure `FILEMAID_SERVER_TOKEN` para proteger el acceso. En clientes o upstream VLM use `FILEMAID_VLM_KEY` o el token correspondiente. El endpoint VLM es totalmente independiente de la base de datos CouchDB (nunca se deduce de `sync_url`).
PouchDB es el único almacén runtime, en `FILEMAID_DATA/pouchdb`; no hay fallback
ni persistencia relacional. Los documentos tienen esquema dinámico; decisiones y
artefactos históricos son inmutables. Esquema, sincronización y límites:
[docs/db-mig.md](docs/db-mig.md).

### Limpiar workspaces (`clean`)

`uv run filemaid clean` elimina únicamente copias temporales y páginas de trabajo,
con confirmación salvo `-y`. No borra PouchDB, caché, configuración ni evidencias.
Los JSONL y HTML escritos explícitamente por `run`, `emit` y `report` son exports.

Regla de oro (docs/normas.md): ante duda razonable, escalar antes que pagar.
El motor es puro: mismos inputs + misma config ⇒ misma salida, byte a byte.
