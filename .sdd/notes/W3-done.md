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

## Sesión 3 — T11 cerrado (commit 02ec526)

- PDF de entrega compilado con la plantilla Typst del equipo (11 páginas,
  5 ADRs) y SIN commitarlo: va solo al repo de entrega (lo prepara el
  supervisor con docs/report/albertitos_plan.pdf ya compilado en el worktree).
- ADRs reflejan decisiones reales: reglas-como-datos v3→v4, ERP fuera de
  scope (costura de adaptador), rung 5 = deepseek-v4.1-flash (Qwen vetado),
  revisión humana no bloqueante.
- T8 (runner) y T10 (dry-run) aún sin datos: sus huecos en el informe quedan
  como PENDIENTE-MEDICIÓN/ESTIMADO; cuando escriban evidencia al ledger,
  regenerar con `uv run python -m albertitos.report_data` + `-m albertitos.metrics`
  y recompilar (`cd docs/report && ~/.local/bin/typst compile --font-path fonts albertitos_plan.typ`).

## Sesión 4 — T12 cerrado (commit a943fab)

- Drills de resiliencia (`albertitos.drills`, 4/4 PASS, medidos en
  .sdd/metrics/drills.json): rung 5 caído → ESCALAR sin abortar; 429 con
  Retry-After → backoff respetado y 0 llamadas extra; crash del runner real
  (`run_batch` + Store) a mitad de lote → reanudación sin duplicados;
  ledger corrupto → tolerado sin inventar nada. La defensa de resiliencia
  (10 pts de la rúbrica) tiene ensayo real con números.
- `scripts/stage_delivery.sh`: staging del repo de entrega (3 archivos,
  idempotente, valida antes de copiar, escanea secretos, falla limpio).
- Para la defensa: `uv run python -m albertitos.drills` reproduce los 4
  ensayos en segundos, sin red.

## Sesión 5 — T15 cerrado (commit ba3c7dc)

- Informe con TODA la evidencia medida disponible: T10 (dry-run 471/29/0-QR,
  calibración extract-v2), T12 (drills 4/4) — fuente citada archivo a archivo
  en escalabilidad.typ y en los ADRs (extracción, pipeline, rung 5/revisión).
- Placeholders SOLO para T14 (corrida real: resultados, exactitud, cola de
  revisión, llamadas cloud) vía bindings PENDIENTE-MEDICIÓN(T14); impacto
  T13 igual. Fórmula de coste: CPU gratis salvo electricidad (estimada).
- PDF compilado (13 páginas) en el worktree, no commitado.
- Cuando T14 escriba outcomes.jsonl y su evidencia: regenerar con
  `uv run python -m albertitos.report_data && uv run python -m albertitos.metrics`
  y recompilar (`cd docs/report && ~/.local/bin/typst compile --font-path fonts albertitos_plan.typ`).
  El flujo data→.typ ya lee esos orígenes (tests en verde).
