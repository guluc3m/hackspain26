# albertitos

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
src/albertitos/
  types.py          contrato: ExtractionFeature, ExtractionField, Decision...
  config.py         rutas de estado (data/, nunca /tmp) y config de extracción
  pipeline.py       worker: lote idempotente y resumable (clave: sha+stage+version+config)
  run.py            CLI: run | emit | serve | reprocess
  extract/          escalera de 5 escalones por página, cache y plausibilidad
    rungs/          1 texto (pypdf) · 2 raster+QR (pypdfium2+zxing) · 3 tesseract
                    4 VLM local (llama-server, temp 0) · 5 VLM cloud (solo candidato)
  parse/            features → campos: todos los candidatos se conservan
  rules/            motor puro y determinista + 8 reglas + maestros (CSV/Excel)
  store/            SQLite (WAL) + ledger JSONL append-only
  api/              FastAPI: comparte types, store y motor con el pipeline
master/             datos maestros y thresholds de reglas (versionados)
frontend/           Svelte + Vite (TS): Operaciones, Facturas, Revisión, Reglas, Impacto, Salud
```

## Uso

```sh
uv sync                              # entorno (Python 3.13, user-space)
uv run albertitos run --lote caja-de-alberto/facturas --out outcomes.jsonl
uv run albertitos emit               # re-emite outcomes desde el store
uv run albertitos serve              # API + UI de revisión
uv run pytest                        # tests
uv run ruff check src tests          # lint
```

Regla de oro (docs/normas.md): ante duda razonable, escalar antes que pagar.
El motor es puro: mismos inputs + misma config ⇒ misma salida, byte a byte.
