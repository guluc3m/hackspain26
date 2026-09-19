# Auditoría de requisitos — Maisa «500 Sombras de Alberto»

**Proyecto:** filemaid · **Repo:** `/home/deploy/hackspain26` · **Rama:** `feat/remotion-polish` · **Commit:** `867748b` («Ingesta por carpeta, vigilante de escritorio, revisión humana con replicación selectiva y UI Typst»)
**Fecha:** 2026-09-19 · **Alcance:** solo lectura; verificación con comandos puntuales (sin full-suite).

Fuentes de requisitos: https://hackathon.maisa.ai/ (transcripción completa en `caja-de-alberto/README.md`, que es el enunciado oficial) y el contrato interno `AGENTS.md`. La spec autoritativa es `docs/report/architecture.typ`.

---

## 1. Entregables (contrato §1 de AGENTS.md)

El repo de **entrega** debe ser un repositorio público **separado** cuya raíz contenga **exactamente** 3 ficheros: `outcomes.jsonl`, `outcomes_lote2.jsonl`, `albertitos_plan.pdf` (AGENTS.md §1). Ninguno de los tres existe aún.

| Entregable | Estado | Evidencia |
|---|---|---|
| `outcomes.jsonl` | ❌ No existe | `find . -name 'outcomes*.jsonl'` (excluyendo `.venv`/`data/`) → 0 resultados. Los únicos `outcomes.jsonl` del árbol son artefactos de tests bajo `data/pytest-*` y `data/pouch-cli-smoke/outcomes.jsonl` (1 línea, fixture con `{"file_id": "Factura real ñ.PDF", "result": "ESCALAR"}`), no entregables. |
| `outcomes_lote2.jsonl` | ❌ No existe | Misma búsqueda → 0 resultados. |
| `albertitos_plan.pdf` | ❌ No compilado | `docs/report/.gitignore` ignora `*.pdf`; no hay PDF en el repo. La **fuente** `docs/report/albertitos_plan.typ` ✅ existe (100 líneas) con instrucciones de compilación (`typst compile --font-path fonts albertitos_plan.typ`, `docs/report/README.md`). `typst` no está en PATH en esta máquina. |

### 1.1 Formato del JSONL — mecanismo verificado en código ✅

`export_outcomes` (`src/filemaid/pipeline.py:570-600`) garantiza por construcción el formato exigido:
- una línea por decisión: `{"file_id": ..., "result": ...}` — sin campos extra;
- `file_id` = basename exacto (rechaza rutas: `if Path(file_id).name != file_id → RuntimeError`, línea 585);
- `result ∈ {PAGAR, NO_PAGAR, ESCALAR}` (línea 588) y sin duplicados (línea 590);
- **cobertura completa y exacta**: `if seen != set(expected) → RuntimeError` (línea 594) — no exporta un lote incompleto (`batch_result.status != "complete"` → error, línea 573-574);
- escritura atómica (temp + rename, `write_outcomes`, líneas 556-568).
- Re-emisión sin reprocesar: `uv run filemaid emit --out outcomes.jsonl [--batch-id ...]` (`src/filemaid/run.py:36-40,119-123`).

### 1.2 Cobertura esperada vs lotes reales (conteos verificados)

| Lote | Directorio | PDFs reales | JSONL esperado |
|---|---|---|---|
| Lote 1 | `caja-de-alberto/facturas/` | **500** | 500 líneas, 1 por PDF |
| Lote 2 | `caja-de-alberto/facturas_primin/` | **40** | 40 líneas, 1 por PDF |

- `caja-de-alberto` es el submódulo oficial del reto (`.gitmodules` → `500-sombras-de-alberto`).
- Todos los ficheros en ambos directorios terminan en `.pdf` (0 excepciones); **0 nombres compartidos** entre lotes (`comm -12` → 0).
- ⚠️ **No se puede validar aún la coincidencia `file_id`↔PDF** porque no existe ningún JSONL real de una corrida completa: la validación binaria del hackathon fallará hoy. Acción: correr el lote 1 y el lote 2 (o `filemaid emit`) y contrastar los `file_id` contra `ls` de cada directorio.

---

## 2. Rúbrica

### 2.1 Producto, arquitectura y ADRs — 35 pts · Estado global: ⚠️

✅ **Arquitectura documentada y razonada**: `docs/report/architecture.typ` (147 líneas) cubre extracción (escalera de 7 escalones calibrada por página, con coste/latencia por escalón), parser resiliente multilingüe con `values[]` sin colapsar, motor de reglas con thresholds configurables, persistencia PouchDB/CouchDB con revisión humana y replicación selectiva, modos standalone/servidor y retroalimentación.

✅ **ADRs con la estructura exigida**: `docs/report/albertitos_plan.typ` contiene **8 ADRs**, cada uno con `contexto` / `alternativas` / `decisión` / `consecuencias` / `evidencia` y estado: motor determinista con reglas como config (v3→v4), features/parser con calibración T10, pipeline desacoplado + costura ERP, persistencia en BD, rung cloud + revisión no bloqueante, selección de candidato con provenance (ADR-06), app de escritorio pywebview (ADR-07), `outcomes.on_fail` (ADR-08). El requisito dice «2–5 ADRs»: 8 **excede** el rango (probablemente válido como mínimo, pero conviene confirmar o consolidar) — ⚠️.

❌ **El PDF de entrega no está compilado** (§1).

⚠️ **Divergencias ADR↔código detectadas** (riesgo en defensa):
- **ADR-06** afirma que las reglas (`ORDER_AMOUNT_MATCHES`, `TOTALS_MUST_MATCH`, `IVA_CONSISTENT`, `IBAN_MATCHES_MASTER`) evalúan **todos** los candidatos del campo citando el que matchea. En el código, las reglas consumen `ctx.pick_coded(...)` → `escoger()` (`src/filemaid/rules/escoger.py:199+`), que colapsa el campo a **un** candidato por puntuación (confianza × peso) con auditoría por candidato (`CandidateAudit`). No hay regla `ORDER_AMOUNT_MATCHES` (inexistente en `master/rules.yaml` y `src/filemaid/rules/rules.py`; el cruce de importe vive dentro de `OrderBelongsToSupplier`, `rules.py:110-152`). El motor declarado es `runner-1.1.0` con esta semántica o no se ha aplicado al código actual: **conciliar antes de defender**.
- **Evidencia citada no presente en el repo**: los ADRs citan `.sdd/metrics/corpus-dryrun.json`, `.sdd/metrics/drills.json`, `.sdd/metrics/impacto-fix-colapso.json`, `.sdd/metrics/auditoria-trampas.md`… pero **el directorio `.sdd/` no existe** (`ls .sdd` → no such file). Los números sí están volcados en `docs/report/escalabilidad_datos.typ`, pero los ficheros fuente no son verificables por el jurado.
- AGENTS.md describe una escalera de **5** escalones; `architecture.typ` (spec que gana) y el código (`src/filemaid/extract/rungs/`: text_layer, qr, tesseract, vlm_local, typesafe_jev, firecrawl, cloud_vlm) tienen **7**. AGENTS quedó desactualizado (menor).

### 2.2 Trazabilidad y observabilidad — 20 pts · Estado global: ✅ (falta demo de una decisión real)

✅ **Cadena completa input→resultado trazable en código**:
1. **Input**: PDF → features por página con engine+versión+latencia (`ExtractionFeature`, `src/filemaid/types.py`; rungs en `src/filemaid/extract/rungs/`).
2. **Evidencia**: candidatos múltiples conservados por campo con extractor y confianza (`ExtractionField.values[]`, types.py:110); colapso con auditoría por candidato (`Selection.audit`, `escoger.py:189-260`).
3. **Reglas**: cada regla devuelve verdicto PASS/FAIL/UNKNOWN con motivo, valores consumidos y provenance `extractor@confianza` (`rules.py`: p. ej. `NIF_IN_MASTER` líneas 40-58, `IBAN_MATCHES_MASTER` 60-94, `ORDER_BELONGS_TO_SUPPLIER` 96-152).
4. **Resultado**: `Decision` con `rule_verdicts`, `rule_outcomes` y snapshot de configuración (`engine.py:35-56`, `config.py:81-94` incluye `master_sha256`, `rule_outcomes`), persistida inmutable en PouchDB.

✅ **Señales de operación**: API `GET /api/salud`, `/api/jobs`, `/api/logs`, `/api/trazas`, `/api/artefactos/{id}` (`src/filemaid/api/app.py:305-390`); UI con pestañas Dashboard/Ingest/Invoices/Review/Logs (`frontend/src/nav.ts`); informe HTML con drivers «FAIL→ESCALAR» (`src/filemaid/rules/report.py:195-199,456-460`).

⚠️ **Pendiente**: la rúbrica pide «seguir UNA decisión real» — hay que ejercitarlo en la demo sobre una factura concreta (requiere una corrida; hoy no hay datos de lote real en el repo, solo `data/*` de tests).

### 2.3 Escalabilidad y coste — 25 pts · Estado global: ❌ (datos medidos existen, la sección está vacía)

- ❌ **`docs/report/escalabilidad.typ` está VACÍO** (23 bytes: solo el encabezado `= Escalabilidad y coste`). Es la sección incluida en el PDF de entrega (`albertitos_plan.typ:25`) → el entregable no respondería «¿cuántos archivos por segundo, con qué hardware, cómo calculáis el coste?».
- ✅ **Datos medidos disponibles para explotar**: `docs/report/escalabilidad_datos.typ` (generado por `filemaid.metrics`) contiene: hardware 8 núcleos / 12 GB RAM (medido); dry-run del corpus T10 (471/500 texto usable = 94,2 %; latencias rung 1 media 0,4 ms / p95 2,0 ms; rung 2 media 42,1 ms / p95 73,0 ms; throughput rung 1: 2 636 archivos/s; wall 3,57 s para 500); calibración rung 3 (word-conf 40,0 → 89,7 % OCR pasa); perfil de carga T23 (UI+2 runners: peor p95 7,7 ms, 108,7-110 files/s por runner); lote 1: 4,16 archivos/s, distribución 433/22/45.
- ⚠️ **Fórmula de coste incompleta**: `formulaCoste` en `escalabilidad_datos.typ` tiene electricidad «estimado» a 0,0000 EUR, llamadas cloud «medido×precio estimado» y tokens de agentes «sin datos»; `costePorArchivo`/`costePorLote` = «sin datos». Falta la fórmula explícita y una medición real del coste cloud.
- ⚠️ **Nuevos tipos de archivo**: la respuesta estratégica existe a medias (extractores por escalón sustituibles, reglas desacopladas de extracción, ADR-03), pero el conector real solo lee PDFs: no hay soporte xlsx ni email. El cargador de maestros solo lee CSV (`master.py:52-97`), no el Excel de la Caja (`FINAL_v7_DEFINITIVO_ahorasi.xlsx`).

### 2.4 Resiliencia y recuperación — 10 pts · Estado global: ✅

✅ **Estado en disco**: PouchDB JS local (LevelDB) como única fuente (evidencia, caché, eventos, decisiones inmutables, adjuntos fragmentados); configuración en documentos `_local` no replicados (`architecture.typ` «Modos de ejecución»; `src/filemaid/store/`). Nunca `/tmp` (AGENTS §8).

✅ **Idempotencia / dedup**: caché por página con clave `(page_sha256, extractor_version, config_version)` (AGENTS §3; `src/filemaid/extract/cache.py`); `batch_result` persistido por `batch_id` determinista — reejecutar un lote completo es no-op y reexporta (`pipeline.py:146-167`); export atómico y solo con lote completo.

✅ **Reanudación**: `run_lote` documentado «reanudable» (pipeline.py:147); CLI `filemaid reprocess` (run.py:56,154-156) y `POST /api/reprocesar/{file_id}` (app.py:346); tests de persistencia, replicación y recuperación: `tests/test_pouch_persistence.py`, `test_pouch_identity.py`, `test_couchdb_replication.py`, `test_dispute_sync.py`, `test_cache_pouch.py` (41 ficheros de tests, 287 tests en total).

✅ **Degradación**: cada escalón registra `skipped:<reason>` y cae al siguiente sin parar el lote (p. ej. `cloud_vlm.py`: `_skip("standalone-no-remote")`; modo standalone jamás contacta remoto, `architecture.typ`); lectura cloud como candidato extra, nunca respuesta automática.

⚠️ **Proveedor caído / rate-limit**: la excepción HTTP se captura y la página degrada (`cloud_vlm.py:113-117`), pero **no hay backoff/Retry-After implementado en el código actual** — el drill `backoff-429` PASS citado en el ADR-05 respaldaba una implementación cuya evidencia (`.sdd/metrics/drills.json`) no está en el repo. Verificar si la política de reintentos vive en otra capa o reintroducirla.

### 2.5 Calidad de ejecución — 10 pts · Estado global: ✅

✅ Arranque de un paso: `./run.sh [app|vlm|desktop]` + `start.py` (stdlib only, sincroniza uv, deps Node de PouchDB, build de UI) — idempotente y sin relanzamientos.
✅ App de escritorio multiplataforma con pywebview compartiendo la misma UI Vue y el mismo motor (`src/filemaid/desktop/app.py`; ADR-07).
✅ 287 tests en 41 ficheros; comprobación puntual ejecutada en esta auditoría: `pytest tests/test_rules_engine.py tests/test_cli_run.py` → **18 passed** en 0,25 s.
✅ UI en español con cola de revisión, reglas visibles y ayuda contextual; informe HTML explicando la frontera NO_PAGAR/ESCALAR.

### 2.6 Bonus: una mejora para Alberto (+10) — Estado global: ⚠️

Candidatos reales implementados: **app de escritorio** (ADR-07, `desktop/app.py`), **vigilante de carpeta** (ingesta continua, `desktop/watcher.py`, `tests/test_desktop_watcher.py`), **revisión humana con replicación selectiva** (D-003 en `docs/decisiones/DECISIONS.md`; retención fail-closed de facturas disputadas). ⚠️ La rúbrica pide «detectado, **implementado y mostrado**»: falta el «mostrado» — el vídeo está en marcha (`video/` con Remotion, en esta rama, aún sin render) y la demo requiere la app funcionando. Elegir UNA mejora como narrativa principal del bonus.

---

## 3. Lote 2 «sorpresa» (sábado)

Requisitos según el enunciado (`caja-de-alberto/README.md`, Makefile del ERP) y estado:

| Requisito | Estado | Evidencia y brecha |
|---|---|---|
| +40 facturas nuevas | ⚠️ Datos presentes, sin procesar | `caja-de-alberto/facturas_primin/` = 40 PDFs (verificados). Sin `outcomes_lote2.jsonl` (§1). |
| ERP actualizado | ⚠️ Datos presentes, sin consumir | `caja-de-alberto/erp_export_lote2.csv` (40 asientos + cabecera; incluye estados `PAGADA`/`PENDIENTE`), `pedidos_nuevos.csv` (39 pedidos PO-2026-05xx), `proveedores_nuevos.csv` (4 proveedores); ERP simulado en `caja-de-alberto/alberto_erp.py` (puerto 8009, `make erp-lote2`). **El código de filemaid solo carga maestros de CSV propio** (`master/pedidos.csv`, `master/proveedores.csv`; `master.py:52-97`) — no hay cliente HTTP del ERP ni consumo del export del lote 2. La «costura de adaptador» del ADR-03 no está implementada como integración real. |
| Conservar trabajo | ✅ Por diseño | Idempotencia por `(sha256, stage, engine_version, config_version)` y `batch_result` persistido; las 500 decisiones del lote 1 sobreviven reinicios en PouchDB (§2.4). |
| Reprocesar tras el cambio | ✅ Mecanismo | `filemaid reprocess` (CLI) + `POST /api/reprocesar/{file_id}`; el recálculo es determinista con el mismo motor. Falta ensayarlo con los datos del sábado. |
| Regla nueva (v4) | ❌ No preparada | El plan lo anuncia («la regla v4 cargada como DATOS», ADR-01) y el mecanismo existe (reglas habilitadas en `master/rules.yaml`), pero hoy solo están las 8 reglas v3.0-2026-09-19. No hay borrador ni plan de la regla del sábado. |
| Frontera NO_PAGAR/ESCALAR como datos | ✅ | `outcomes.on_fail` en `master/rules.yaml` (NIF/IBAN → ESCALAR); validación que impide que una regla rota pague (`config.py:62-74`; probado en `tests/test_rules_engine.py`). |

---

## 4. Veredicto por entregable (resumen ejecutivo)

| # | Requisito | Estado |
|---|---|---|
| 1 | `outcomes.jsonl` (500 líneas, formato correcto) | ❌ Generar y contrastar file_ids |
| 2 | `outcomes_lote2.jsonl` (40 líneas) | ❌ Generar y contrastar file_ids |
| 3 | `albertitos_plan.pdf` (arquitectura + ADRs) | ❌ Compilar (fuente completa ✅, 8 ADRs > rango 2-5 ⚠️) |
| 4 | Producto/arquitectura/ADRs (35) | ⚠️ Sólido; conciliar ADR-06 con el motor; evidencia `.sdd/` ausente |
| 5 | Trazabilidad (20) | ✅ Cadena completa en código; ensayar «una decisión» en demo |
| 6 | Escalabilidad y coste (25) | ❌ Sección vacía pese a haber datos medidos que explotar |
| 7 | Resiliencia (10) | ✅ Salvo backoff-429 no verificable en código/repo |
| 8 | Calidad de ejecución (10) | ✅ |
| 9 | Bonus (+10) | ⚠️ Implementado; falta «mostrarlo» |
| 10 | Lote 2 sorpresa | ⚠️ Datos listos; falta consumir ERP del lote 2, procesar y preparar regla v4 |

---

## 5. Acciones pendientes priorizadas

| Prio | Acción | Impacto |
|---|---|---|
| **P0** | Ejecutar el lote 1 (`.venv/bin/filemaid run --lote caja-de-alberto/facturas --out outcomes.jsonl` (o `uv run filemaid run …`)) y contrastar 500 `file_id` contra `ls caja-de-alberto/facturas/` | Sin esto la validación binaria del hackathon falla (no hay premio) |
| **P0** | Ejecutar el lote 2 (`facturas_primin`) → `outcomes_lote2.jsonl` (40 líneas) y contrastar file_ids | Ídem |
| **P0** | Escribir `docs/report/escalabilidad.typ` consumiendo `escalabilidad_datos.typ` (throughput, hardware, fórmula de coste, límites, plan de nuevos tipos) + medir coste cloud real | Criterio de 25 pts hoy en blanco |
| **P0** | Compilar `albertitos_plan.pdf` (`typst compile --font-path fonts docs/report/albertitos_plan.typ`) | Entregable obligatorio |
| **P1** | Conciliar ADR-06 con `escoger()`: o el motor evalúa todos los candidatos con provenance, o el ADR describe la semántica real de puntuación+auditoría | Riesgo de credibilidad en defensa (35 pts) |
| **P1** | Regenerar/incluir la evidencia citada (`.sdd/metrics/*.json`) en el repo o en el anexo del PDF | Los ADRs citan ficheros inexistentes |
| **P1** | Ensayar el día del lote 2: arrancar `make erp-lote2`, ingestar `facturas_primin`, reprocesar, y tener un borrador de «regla v4 como datos» | «Cómo diseñasteis el cambio, el reprocesado y los límites» |
| **P1** | Implementar/verificar backoff + Retry-After en el rung cloud y re-ejecutar los drills con resultados en el repo | Criterio de resiliencia (10 pts) y coherencia con ADR-05 |
| **P2** | Ensayar la trazabilidad de UNA decisión real end-to-end en la demo (factura → evidencia → reglas → resultado) | 20 pts de trazabilidad |
| **P2** | Renderizar el vídeo (Remotion, `video/`) y elegir la mejora del bonus a mostrar | Bonus +10 |
| **P2** | Decidir sobre el nº de ADRs (consolidar a 2-5 o defender 8) y actualizar AGENTS.md (5→7 escalones) | Pulido |
| **P3** | Conector maestro xlsx (hoy solo CSV) si se quiere cubrir el Excel de la Caja en la demo | Robustez de producto |
