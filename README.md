# albertitos

Sistema de decisión para las facturas de Alberto: lee PDFs, extrae campos y decide
si cada factura se puede pagar — `PAGAR`, `NO_PAGAR` o `ESCALAR` — con evidencia
y trazabilidad en cada paso.

```
PDF ──▶ EXTRACCIÓN ──▶ FEATURES ──▶ PARSER ──▶ CAMPOS ──▶ MOTOR DE REGLAS ──▶ RESULTADO
                                                               │
                                                     evidencia + config ──▶ STORE ──▶ UI
```

Los extractores proponen; las **reglas deciden**. Ningún modelo emite el resultado.

## Uso

Requisito único: [`uv`](https://docs.astral.sh/uv/).

```sh
./iniciar.sh          # abre la app en ventana nativa (o navegador), puerto 8000
```

Sin argumentos, sin terminal que aprender. Idempotente: si ya está encendido, solo abre.

## Lote

```sh
uv run python -m albertitos.run --facturas <dir> --outcomes outcomes.jsonl
```

Salida: un JSONL con `{"file_id": "<nombre exacto del PDF>", "result": "..."}` y
validación de contrato automática al cubrir el lote completo. Reanudable: reutiliza
evidencia previa por `(sha256, stage, engine_version, config_version)`.

## UI

Seis secciones en español llano: **Operaciones** (estado del lote, coste),
**Facturas** (resultado + cadena de evidencia por fila), **Revisión** (cola de
escaladas, imagen junto a cada lectura candidata), **Reglas** (umbral activo y
diff), **Impacto** (reprocesado y antes/después), **Salud** (proveedores y reintentos).

## Desarrollo

```sh
uv run pytest          # suite completa
uv run ruff check .    # lint
```

Estructura: `src/albertitos/extract/` (escalera de extracción por página),
`src/albertitos/parse/` (parser de campos), `src/albertitos/rules/` (motor + YAML
de umbrales), `src/albertitos/store.py` (SQLite + ledger JSONL), `src/albertitos/ui/`
(FastAPI), `tools/` (auditoría y métricas), `archivos-limpios/` (corpus adversarial
con trampas nombradas).

Más contexto: `AGENTS.md` (contrato del sistema), `docs/report/architecture.typ`
(especificación autoritativa), `docs/decisiones/DECISIONS.md` (ADR).
