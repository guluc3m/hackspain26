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
