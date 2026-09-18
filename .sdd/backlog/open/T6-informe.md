# T6 · Generador de albertitos_plan.pdf
assignee: W3
priority: p2

## Objetivo
`src/albertitos/report.py`: generar `albertitos_plan.pdf` (Arquitectura + 2–5
ADRs) desde datos medidos en `.sdd/`, no desde texto hardcodeado.

## Secciones requeridas (hackathon.maisa.ai)
- **Arquitectura**: componentes, flujo de datos y estado, reparto agentes/
  modelos/personas, trazabilidad y recuperación de fallos.
- **ADRs / trade-offs** (2–5): contexto, alternativas, decisión, consecuencias,
  evidencia. ADRs previstos: D-001 escalera de extracción, D-002 PaddleOCR-VL q8
  en CPU, D-03 reglas-como-datos (v3→v4), D-04 política NO_PAGAR/ESCALAR,
  D-05 revisión humana no bloqueante.

## Reglas duras
- Los números de coste/throughput salen de evidencia medida; lo estimado va
  marcado como estimado.
- El PDF se regenera con un comando: `uv run python -m albertitos.report`.

## Criterios de aceptación
- Genera un PDF válido de prueba con datos sembrados.
- Test: el PDF se genera y tiene ≥2 páginas y las secciones Arquitectura/ADRs.
- `uv run pytest` y `uv run ruff check .` en verde.
