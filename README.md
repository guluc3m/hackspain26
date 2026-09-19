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
  extract/          escalera de 7 escalones por página, cache y plausibilidad
    rungs/          1 texto (pypdf) · 2 raster+QR (pypdfium2+zxing) · 3 tesseract
                    4 VLM local (llama-server, temp 0) · 5 TypeSafe (solo juicios)
                    6 Firecrawl · 7 VLM cloud (solo candidato)
  parse/            features → campos: todos los candidatos se conservan
  rules/            motor puro y determinista + 8 reglas + maestros (CSV/Excel)
  store/            SQLite (WAL) + ledger JSONL append-only
  api/              FastAPI: comparte types, store y motor con el pipeline
master/             datos maestros y thresholds de reglas (versionados)
frontend/           Vue 3 + Vite (TS, pnpm): Dashboard (cola de revisión),
                    Invoices (facturas + carpeta) y Logs (buscador de entradas)
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
uv run filemaid run --lote caja-de-alberto/facturas --out outcomes.jsonl
uv run filemaid emit               # re-emite outcomes desde el store
uv run filemaid serve              # API + UI de revisión
uv run filemaid clean              # borra store.db (pide confirmación)
uv run pytest                        # tests
uv run ruff check src tests          # lint
pnpm --dir frontend install          # dependencias de la UI
pnpm --dir frontend dev_syncth       # UI con datos sintéticos de referencia
pnpm --dir frontend build_syncth     # build de la UI sintética
```

### Modo sintético y UI

La UI consume los datos de la base de datos (sqlite) que expone el backend.
Mientras esa conexión no existe, los targets `*_syncth` ejecutan la interfaz
con una referencia sintética de esa base (`src/mock/data.ts`): decisiones con
ID asignado y entradas de log mínimas (solo tipo + IDs; el detalle vive en las
tablas). La conexión real queda vacía a propósito en `src/api.ts`.

El backend (`uv run filemaid serve`) expone la API y sirve la UI construida
en `frontend/dist`.

### Limpiar el estado (`clean`)

Borra estado en disco para empezar de cero. Respeta `FILEMAID_DATA` (por
defecto `data/`). Por defecto borra el store; pide confirmación salvo `-y`.

```sh
uv run filemaid clean              # store.db + WAL/SHM
uv run filemaid clean -y           # sin confirmación
uv run filemaid clean --all -y     # store + cache + pages + ledger
uv run filemaid clean --cache --pages --ledger -y
```

| Flag | Borra |
| --- | --- |
| (ninguno) | `store.db` (y `-wal`/`-shm`) |
| `--cache` | cache de extracción (`data/cache`) |
| `--pages` | páginas rasterizadas (`data/pages`) |
| `--ledger` | ledger append-only (`data/ledger.jsonl`) |
| `--all` | todo lo anterior |
| `--yes`, `-y` | omite la confirmación |

Regla de oro (docs/normas.md): ante duda razonable, escalar antes que pagar.
El motor es puro: mismos inputs + misma config ⇒ misma salida, byte a byte.
