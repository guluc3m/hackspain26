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

## Sesión 6 — T16 cerrado (commit e97c2ad)

- UI demo-ready contra el store REAL del lote 1: symlink `.sdd/lote1` →
  /home/deploy/fleet/w1/.sdd (SOLO LECTURA) o `ALBERTITOS_STORE`.
  Para la demo: `ALBERTITOS_STORE=.sdd/lote1/ledger uv run uvicorn
  albertitos.ui.app:app` → Operaciones con estado del runner medido,
  Facturas con filtro/búsqueda/paginación, Revisión con los escalados reales
  (paginada, imágenes reales), Reglas v3 real, Salud con llama-server +
  drills.
- Lector extendido al formato real del runner (rule_codes string, event=
  decision); overrides SIEMPRE al .sdd local, jamás al store externo.
- Importante para quien integre: el store de W1 es objetivo móvil (al
  cerrar T16: 515 líneas de ledger, 60 ESCALAR, 24 en cola de revisión con
  imagen) — los tests validan consistencia interna del render, no números
  congelados.
- Flaky ajeno detectado: tests/test_run.py::test_archivo_con_timeout... (T8,
  W2) falla ~1 de cada N corridas de suite por timing (verde en solitario
  3/3); avisado en el ticket cerrado para W2.

## Sesión 7 — T20 cerrado (commit 12f4b2a)

- `docs/report/DEFENSA.md`: guion 10 min (demo 2' → arquitectura 2' →
  trazabilidad/escala/coste 4' → resiliencia 2') con SOLO cifras medidas y
  fuente citada al pie (12 ficheros de .sdd/metrics/); checklist operativo
  (symlink lote1 + ALBERTITOS_STORE + uvicorn + typst + drills + validador)
  y plan B si algo falla en vivo.
- Corrección de datos: el ticket citaba «31 s/página» para rung 4; la
  medición real de lote1.json es media 15,8 s / máx 33,7 s (n=9) — el guion
  usa la medición real.
- Test: DEFENSA.md validada (secciones, checklist, fuentes existentes,
  números contra JSON). 187 passed, ruff limpio.

## Sesión 8 — T23 cerrado (commit 4894e44)

- Perfil de carga MEDIDO del régimen completo (`.sdd/metrics/perfil-carga.json`):
  UI real (lote 1, 500 facturas) + 2 runners concurrentes (limit 50, stores
  temporales) + llama-server up → UI p95 < 12 ms, 108-110 files/s por runner,
  RSS 96/38 MB, 8 GB RAM libres, 0 ROJOS. Concurrencia soportada MEDIDA;
  límite práctico estimado: CPU en rung 3/4 (~1 core/runner serializado),
  no la RAM. Párrafo en escalabilidad.typ (PDF recompilado).
- `albertitos.perfil`: re-ejecutable (`python -m albertitos.perfil`), /proc
  para RSS/CPU sin psutil; runners sobre COPIAS temporales jamás el store real.
- DEFENSA.md sincronizado con lote1.json post-fix T18 (433/22/45 final);
  test dinámico: el guion debe citar la medición actual (si lote1.json
  evoluciona, el test avisa para actualizar el guion).

## Sesión 9 — T26 cerrado (commit 3efc265) — BONUS

- Resumen ejecutivo para Alberto (`albertitos.resumen`, HTML+PDF desde el
  store real): «Hoy se pagan 433 facturas por 2.331.130,43 EUR» (suma EXACTA
  vía file_id→pedido→maestro Pedidos_2026), motivos de NO_PAGAR en llano,
  escaladas por importe, avisos (2 duplicados, 3 fantasmas). Sin datos ⇒
  PENDIENTE, jamás ceros falsos. Hojas trampa del maestro ignoradas+avisadas.
- Ejecutar: `uv run python -m albertitos.resumen --store-root .sdd/lote1
  --maestro <caja>/FINAL_v7_DEFINITIVO_ahorasi.xlsx`.
- El eslabón importe: el ledger real no guarda importes; el join honesto es
  vía pedido (store.db) × maestro. Las PAGAR sin pedido/entrada se listan
  como aviso y no se suman.

## Sesión 10 — T28 cerrado (commit d59a605)

- Simulacro de defensa (`albertitos.simulacro`, 15/15 PASS): el guion
  contrastado contra la medición ACTUAL + demo preparada (5 pantallas 200
  in-process, resumen ejecutivo regenerado, store SOLO LECTURA).
- Capturó 3 desincronizaciones reales en el primer intento (outcomes
  pre-fix, p95 desactualizado, resumen ausente) — el guion se actualizó con
  la medición actual, jamás al revés.
- Para la defensa: `uv run python -m albertitos.simulacro` antes de cada
  ensayo; si algo sale ROJO, se actualiza el guion con la medición nueva.

## Sesión 11 — T30 cerrado (commit fd11670) — BONUS

- Plan por dinero en riesgo: los 45 escalados priorizados por importe con
  suma acumulada y % cubierto; "para_cubrir_80_pct" = mínimo k de facturas
  que cubren el 80 % del dinero en juego. Demo real: 116 163,14 € en riesgo,
  con 3 facturas se cubre el 80 % (encabeza la outlier de 84 700 €).
- Aditivo puro: resumen ejecutivo (T26) enriquecido; motor y reglas intactos.
- Submodule caja-de-alberto inicializado user-space en este worktree (W1 lo
  necesitaba); queda 1 flaky de timing en test_drill_rung4_live (W1, verde
  en suite completa) — documentado.

## Sesión 11 — T30 y T31 cerrados (commits fd11670 integrado + 61d2009)

- T30 (BONUS): plan por dinero en riesgo en el resumen de Alberto —
  escaladas por importe desc con suma acumulada y % cubierto; «revisando las
  N primeras cubres el 80 %». Sin tocar el motor.
- T31: telemetría continua — Escalera por rung (n/p50/p95/%/descarte/coste
  en ventanas corrida+histórico), stats VLM de primera (cache hit/miss
  literal, truncado, coste facturable rung 5), sonda llama-server
  (/metrics Prometheus con caché 60 s) y EventChain encadenada con hash +
  pantalla Actividad con verificación anti-manipulación.
- Flaky ajeno recurrente: test_drill_rung4_live (T24, W1) falla ~1 de cada N
  corridas de suite por contention (verde en solitario); documentado.
- Al cierre: 261 passed, ruff limpio, sin secretos.

## Sesión 12 — T34 cerrado (commit 4c50d5f) — p0 Modo Alberto

- iniciar.sh (raíz): arranque de UN paso, idempotente, con comprobaciones
  de requisitos en español y apertura de navegador. Probado en vivo y por
  test (arranque + idempotencia).
- UI entera en lenguaje llano: rungs/extractores/stages/drills traducidos
  con tooltips para el detalle técnico; inicio = la operación de Alberto
  («lo que te toca hoy: X por € Y»); confirmaciones con consecuencias;
  /ayuda con glosario; /resumen-ejecutivo sin terminal. Test anti-jerga
  (rung1-5/WAL fuera de tooltips no aparecen).
- Compat del suite: presentacion.py (T32) cae al store del lote 1; test de
  imágenes de Revisión tolera la cola vaciada por W1 (post-reprocesado);
  DEFENSA.md fuente [3] actualizada a la realidad del store.
- Al cierre: 272 passed, ruff limpio, sin secretos.

## Sesión 13 — T34 integrado y T37 (cierre de entrega) — commit b813790

- T34 integrado en main (junto a T35 app escritorio y T36 presentación de
  W2). Arreglos de integración que tocó el merge: test de telemetría a los
  encabezados llano nuevos; test de imágenes de Revisión tolera la cola
  vaciada por W1 (post-reprocesado, degradación honesta); DEFENSA.md fuente
  [3] actualizada; presentacion.py (T32/W2) cae al store del lote 1 real si
  no hay store local (fallback de 1 línea, aditivo).
- T37 (p0) — cierre de entrega:
  · escalabilidad_datos.typ regenerado con los orígenes nuevos (T18
    impacto-fix: 108 reprocesados, 86 NO_PAGAR→PAGAR, 0 regresiones, OK;
    T23 perfil: peor p95 7,7 ms, 108-110 files/s, 0 ROJOS; distribución
    final 433/22/45). PDF recompilado: 14 páginas, verificado con pypdf.
  · Repo de entrega re-staged con los outcomes DEFINITIVOS post-fix:
    validador 500/500 OK, exactamente outcomes.jsonl + albertitos_plan.pdf
    (lote 2 llega a las 16:00 UTC ⇒ re-staging con el mismo comando).
  · .sdd/metrics/entrega.json (ACTA, commitada): sha256+bytes de cada
    entregable, reglas v3.0-2026-09-19 / runner-1.1.0, distribución
    original (347/108/45) y final (433/22/45), impacto T18 y checklist de
    defensa (simulacro 15/15 PASS, refrescado).
  · Higiene de secretos sobre lo que se copia: limpia.
- Tests nuevos (test_entrega.py, 3): estructura del acta, sha256 cuadran
  contra el repo real, repo válido y sin secretos.
- Al cierre: 288 passed, ruff limpio, sin secretos.
