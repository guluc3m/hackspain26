# W3 — resumen de sesión (worker/w3)

## Tickets cerrados

- **T5 · UI de operaciones** (commit 5277a62): 5 pantallas (Operaciones,
  Facturas, Revisión, Reglas, Salud) con FastAPI + Jinja2 + HTMX, en español
  llano, todo número etiquetado medido/estimado. Lectura SOLO LECTURA de
  `.sdd/ledger/*.jsonl`; con ledger vacío sirve datos de prueba marcados
  (criterio de aceptación: `uv run uvicorn albertitos.ui.app:app` verificado
  con curl, 5×200). Overrides de revisión encolados con provenance en
  `.sdd/review-queue/overrides.jsonl`, jamás escritos en el store; la decisión
  la recalcula el motor determinista. 14 tests.
- **T6 · Informe** (commit da5245a): PDF de entrega vía plantilla Typst del
  equipo. `albertitos.report_data` genera `docs/report/datos.typ` desde el
  ledger (cada métrica: medido / sin datos — jamás inventadas);
  `implementation.typ` y `escalabilidad.typ` completados; typst 0.13.1
  user-space compila 9 páginas con arquitectura + implementación +
  escalabilidad + 4 ADRs. 4 tests del flujo store→datos.

## Incidencias / decisiones

- Llegó a mitad de sesión un merge de main (AGENTS §13, T6 revisado hacia
  plantilla Typst, tickets actualizados). Resuelto en commit 5d2ee9f: se
  tomó main para docs compartidos, pyproject combinado (python-multipart +
  httpx dev). El generador PDF paralelo inicial de T6 se descartó según el
  ticket revisado.
- T4 (store real de W2) aún no existe: la UI y report_data leen el formato
  JSONL de ledger documentado (kind ∈ evidence/decision/fields), tolerante a
  líneas corruptas; no hará falta tocarlos cuando el store real esté.
- Dependencias nuevas justificadas: httpx (dev, TestClient),
  python-multipart (formularios de Revisión).

## Pendiente (fuera de mi scope)

- T1-T4 quedan abiertos (W1/W2). Cuando el pipeline produzca decisiones
  reales, `uv run python -m albertitos.report_data` + typst compile
  regenerará el informe con cifras medidas.

## Sesión 2 — T9 cerrado (commit aba502e)

- `albertitos.metrics`: métricas medidas por rung (media/p95), throughput
  medido, límite secuencial estimado, hardware medido, fórmula de coste
  explícita con términos separados y etiquetados (lo sin medir ⇒ «sin datos»).
- Salidas: `.sdd/metrics/metrics.json` (regenerable) y
  `docs/report/escalabilidad_datos.typ`, importado por `escalabilidad.typ`;
  PDF de la plantilla compila con las tablas nuevas (10 páginas).
- `python -m albertitos.validate`: validador de contrato de outcomes.jsonl
  (exit 0/1, reporte de diferencias; probado con fixture de 500 facturas,
  duplicados, file_id normalizados/con ruta y results inválidos).
- Nota para quien integre: `.sdd/metrics/metrics.json` es estado regenerable
  (no commitado); el binario typst no participa en tests.
