# T5 · UI de operaciones (FastAPI + HTMX)
assignee: W3
priority: p1

## Objetivo
Implementar `src/albertitos/ui/` — la UI es producto, no herramienta de debug
(AGENTS.md §9). Alberto debe poder usarla sin ayuda; español llano, sin JSON en
el flujo principal; cada número etiquetado como **medido** o **estimado**.

## Pantallas
- **Operaciones** — estado del lote, throughput, cola, coste hasta ahora,
  versión de reglas activa.
- **Facturas** — una fila por factura: resultado, códigos de regla que
  decidieron, cadena de evidencia, extractor, latencia, confianza, página fuente.
- **Revisión** — cola de ESCALAR: imagen de página junto a cada lectura
  candidata, desacuerdo resaltado, aceptar/editar con provenance.
- **Reglas** — set activo, umbrales, y vista "¿qué pasaría si...?" (diff).
- **Salud** — fallos de proveedor/ERP, reintentos, estado degradado.

## Reglas duras
- FastAPI + Jinja2 + HTMX (ya en pyproject). Sin npm, sin build step.
- La UI lee store/ledger en SOLO LECTURA; jamás decide.
- Sin bloquear al pipeline: la revisión es una cola asíncrona.

## Criterios de aceptación
- `uv run uvicorn albertitos.ui.app:app` sirve las 5 pantallas con datos
  sembrados de prueba (fixture del store).
- Test: cada pantalla responde 200 con datos sembrados.
- `uv run pytest` y `uv run ruff check .` en verde.

## Cerrado — decisiones tomadas (W3)

- **Fuente de datos**: la UI lee `*.jsonl` append-only de `.sdd/ledger/` en
  SOLO LECTURA (formato alineado con T4: registros con `kind` ∈
  evidence/decision/fields). T4 aún no está implementado; el lector es
  tolerante a líneas corruptas y a claves nuevas, así que no hará falta
  tocar la UI cuando el store real exista.
- **Demo**: si el ledger está vacío, la app sirve datos de prueba
  deterministas (`ui/demo.py`) con un aviso visible, para que Alberto pueda
  explorar las 5 pantallas con solo `uv run uvicorn albertitos.ui.app:app`
  (criterio de aceptación). Con datos reales, muestra datos reales.
- **Overrides**: la UI jamás escribe en el store ni decide. «Aceptar/editar»
  en Revisión encola un override con provenance (quién/cuándo/campo/valor/
  nota) en `.sdd/review-queue/overrides.jsonl`, que el pipeline consume para
  re-extraer y dejar que el motor determinista recompute (AGENTS.md §7).
  Nunca bloquea el lote.
- **What-if en Reglas**: previsualización de solo lectura basada en la
  confianza ya medida (`_confianza`/`_umbral` en `consumed`); etiquetada como
  previsualización — el motor recalcula de verdad al reprocesar.
- **Dependencias nuevas** (justificadas): `httpx` (dev — TestClient de
  starlette) y `python-multipart` (formularios de la cola de Revisión).
- **Coste**: si no hay registros de coste en evidencia se muestra
  «sin datos» + etiqueta `estimado`; si los hay, suma medida.
