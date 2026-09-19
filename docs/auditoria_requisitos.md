# Auditoría de requisitos — Maisa «500 Sombras de Alberto»

**Proyecto:** filemaid · **Repo:** `/home/deploy/hackspain26` · **Rama:** `feat/remotion-polish` · **Commit:** `59489fa` («UI: menos clics en el flujo frecuente…»)
**Fecha:** 2026-09-19 (22:57 UTC) · **Alcance:** solo lectura; verificación con comandos puntuales (sin full-suite). No se ha tocado código fuente.

**Respecto a la auditoría anterior (commit `867748b`)** han entrado 8 commits (`git log 867748b..HEAD --oneline`): vídeo Remotion de 3 min + auditoría previa (`bd15555`), capturas reales de UI (`626b7b2`), ADR-06 alineado con `escoger()` y escalera de 7 en AGENTS (`94a17da`), escena de producto del vídeo (`e4ee7b6`), benchmarks local vs remoto (`cf94452`), reintento de notificación ESCALAR en watcher (`12a735f`), doc de capacidad y coste (`7c88594`) y pulido de UI (`59489fa`).

**Cambio más importante desde la última auditoría:** el lote 1 ya está **corrido y validado end-to-end** (evidencia real trackeada en `video/`), el ADR-06 está **conciliado con el código**, existe **evidencia medible en el repo** (`.sdd/metrics/` + `video/data_*.json`) y hay **documentos de capacidad/coste/benchmarks** escritos. Lo que sigue crítico: los 3 entregables no están en la raíz del repo de entrega, la sección `escalabilidad.typ` sigue vacía (la página 7 del PDF sale en blanco) y el lote 2 no está ensayado.

---

## 1. Entregables (contrato §1 de AGENTS.md)

El repo de **entrega** debe ser un repositorio público **separado** cuya raíz contenga **exactamente** 3 ficheros: `outcomes.jsonl`, `outcomes_lote2.jsonl`, `albertitos_plan.pdf` (AGENTS.md §1). Estado actual (`find . -name 'outcomes*.jsonl' -not -path './.venv/*' -not -path './data/*'` → 0 resultados en raíz; `ls docs/report/albertitos_plan.pdf` → existe):

| Entregable | Estado | Evidencia |
|---|---|---|
| `outcomes.jsonl` | 🟡 **Contenido validado, fichero aún no en raíz** 🆕 | El lote 1 real está corrido y su salida trackeada en `video/data_outcomes_lote1.jsonl` (500 líneas, **verificado**: `jsonl: 500, pdfs: 500, match: True` contra `ls caja-de-alberto/facturas/`; distribución `PAGAR: 433, NO_PAGAR: 22, ESCALAR: 45`, consistente con `video/data_lote1.json`). Bastan `uv run filemaid emit --out outcomes.jsonl` (re-emisión desde el store, sin reprocesar; `run.py:36-40,115`) o copiar el JSONL validado. La ruta de raíz sigue vacía → la validación binaria del hackathon fallaría hoy. |
| `outcomes_lote2.jsonl` | ❌ No existe | Misma búsqueda → 0 resultados. `caja-de-alberto/facturas_primin/` = 40 PDFs (verificado). El lote 2 no se ha corrido. |
| `albertitos_plan.pdf` | ✅ **Compilado** 🆕 (con una sección vacía, ver §2.3) | `docs/report/albertitos_plan.pdf` existe (106 647 bytes, 13 páginas PDF 1.7, compilado 2026-09-19 22:49; gitignored por `docs/report/.gitignore` → **ojo: no viaja en git**, hay que compilarlo en la máquina de entrega). Texto extraído con pypdf: portada, arquitectura, implementación, ADRs (ADR-06/08 presentes). `typst` ahora está en PATH (`/home/deploy/.local/bin/typst`) → reproducible con `typst compile --font-path fonts albertitos_plan.typ`. |

### 1.1 Formato del JSONL — mecanismo verificado en código ✅ (sin cambios)

`export_outcomes` (`src/filemaid/pipeline.py`, bloque re-leído en esta auditoría) garantiza por construcción el formato exigido:
- una línea por decisión: `{"file_id": ..., "result": ...}` — sin campos extra (el JSONL de evidencia del lote 1 lleva campos extra porque es volcado de diagnóstico; el export los elimina);
- `file_id` = basename exacto (`Path(file_id).name != file_id → RuntimeError`);
- `result ∈ {PAGAR, NO_PAGAR, ESCALAR}`, sin duplicados;
- **cobertura completa y exacta**: `if seen != set(expected) → RuntimeError`; lote incompleto no exporta (`status != "complete"` → error);
- escritura atómica (temp + `os.replace`, `write_outcomes`).

### 1.2 Cobertura esperada vs lotes reales (conteos verificados)

| Lote | Directorio | PDFs reales | JSONL esperado | Estado |
|---|---|---|---|---|
| Lote 1 | `caja-de-alberto/facturas/` | **500** | 500 líneas | ✅ Corrido y contrastado (match 500/500, ver §1) |
| Lote 2 | `caja-de-alberto/facturas_primin/` | **40** | 40 líneas | ❌ Sin correr |

- `caja-de-alberto` es el submódulo oficial del reto (`.gitmodules` → `500-sombras-de-alberto`).
- ✅ **Resuelto desde la auditoría anterior:** la coincidencia `file_id`↔PDF ya está contrastada para el lote 1 (script Python sobre `video/data_outcomes_lote1.jsonl` vs `ls facturas/` → `match: True`). Queda contrastar lo mismo para el lote 2 cuando se corra.

---

## 2. Rúbrica

### 2.1 Producto, arquitectura y ADRs — 35 pts · Estado global: ✅ (mejora: era ⚠️)

✅ **Arquitectura documentada y razonada**: `docs/report/architecture.typ` (147 líneas) — escalera de 7 escalones calibrada por página, parser resiliente multilingüe con `values[]`, motor de reglas con thresholds configurables, persistencia PouchDB/CouchDB con revisión humana y replicación selectiva, modos standalone/servidor.

✅ **ADRs con la estructura exigida**: `docs/report/albertitos_plan.typ` contiene **8 ADRs** (`grep -c '#adr('` → 8), cada uno con contexto/alternativas/decisión/consecuencias/evidencia y estado. 🆕 El propio PDF ahora defiende explícitamente el exceso de rango (línea 101: «Los 8 ADRs anteriores son ADICIONES INCREMENTALES… el jurado puede leer los ADR-01–05 como el núcleo y los ADR-06–08 como extensiones») — la objeción «8 > 2–5» queda mitigada con texto.

🆕 ✅ **ADR-06 conciliado con el código** (era ❌ divergencia; resuelto en commit `94a17da`): el ADR ahora describe la semántica real — colapso a UN candidato por puntuación (confianza × peso, config `seleccion`), `CandidateAudit` de los descartados, y el veredicto decide sobre ese candidato elegido, no sobre «todos». Verificado contra el código: `OrderBelongsToSupplier` (`rules.py:94-146`) consume `ctx.pick_coded("total", 0.7)` → `escoger()` y cruza el importe con `amounts_match(total, order.importe, TOLERANCE_EUR)`. Coherente.

🆕 ✅ **Evidencia citada verificable en el repo** (era ❌; mayoritariamente resuelto): `.sdd/` existe ahora (`git log -- .sdd` → commit `4378540`) con `.sdd/metrics/corpus-dryrun.json`, `calibracion/calibracion-rung3.json`, `calibracion.md/log`, `evidence-dryrun.jsonl`, `dryrun.log`. Los drills y el impacto del fix están trackeados como `video/data_drills.json` y `video/data_impacto.json` (el ADR-05 y ADR-06 citan ya `video/data_*.json`). **Matiz**: los ADRs y `escalabilidad_datos.typ` siguen citando `.sdd/metrics/drills.json`, `impacto-fix-colapso.json`, `auditoria-trampas.md` y `perfil-carga.json`, que **no existen** en `.sdd/metrics/` (`ls` verificado) — los datos reales viven en `video/data_*.json`. Cita muerta menor, arreglable con un renombre o una línea de alias.

❌ **La sección de escalabilidad del PDF sale vacía** (ver §2.3): página 7 del PDF compilado contiene solo el título «3 Escalabilidad y coste».

⚠️ Menor: ADR-05 cita «AGENTS §13», pero `grep -n '## 13' AGENTS.md` no encuentra esa sección (AGENTS sí documenta la escalera de 7 en §3 — 🆕 resuelto desde la auditoría previa, que detectaba «5 escalones» desactualizados).

### 2.2 Trazabilidad y observabilidad — 20 pts · Estado global: ✅ (mejora: ya hay decisión real ejercitada)

✅ **Cadena completa input→resultado trazable en código** (re-verificada):
1. **Input**: PDF → features por página con engine+versión+latencia (`ExtractionFeature`, `src/filemaid/types.py`; 7 rungs en `src/filemaid/extract/rungs/`).
2. **Evidencia**: candidatos múltiples conservados por campo (`ExtractionField.values[]`); colapso con auditoría por candidato (`Selection.audit`, `escoger.py`).
3. **Reglas**: verdictos PASS/FAIL/UNKNOWN con motivo, valores consumidos y provenance `extractor@confianza` (`rules.py`: `NifInMaster:37`, `IbanMatchesMaster:56`, `OrderBelongsToSupplier:94`, …; `RULE_CODES` con las 8 reglas v3).
4. **Resultado**: `Decision` con `rule_verdicts`, `rule_outcomes` y snapshot de configuración (`master_sha256`, `rule_outcomes`), persistida inmutable en PouchDB.

🆕 ✅ **«Una decisión real» ya está ejercitada y documentada** (era ⚠️): la traza de `factura_8801.pdf` (duplicada → `NO_DOUBLE_PAYMENT:FAIL` ⇒ NO_PAGAR, con su history) y el reprocesado medido (`video/data_impacto.json`: 108 re-deciden con `runner-1.1.0`, 86 NO_PAGAR→PAGAR, 0 regresiones, validador OK, 155,5 files/s en warm cache) constituyen la demo de trazabilidad; además el vídeo (escena 5) la muestra. Señales de operación intactas: `/api/salud`, `/api/jobs`, `/api/logs`, `/api/trazas`, `/api/artefactos/{id}`, `/api/reprocesar/{file_id}` (`api/app.py`, endpooints verificados por grep).

⚠️ Nota de provenance detectada 🆕: las filas de `video/data_outcomes_lote1.jsonl` listan 13 códigos de regla (incluidos `ORDER_AMOUNT_MATCHES`, `NO_EMBEDDED_INSTRUCTIONS`, `PROVEEDOR_FANTASMA`, `AMOUNT_OUTLIER`, `PEDIDO_EN_REVISION` con `engine_version: runner-1.0.0`), pero el motor actual (`RULE_CODES`, `rules.py:320`) declara **8 reglas** y no existe `ORDER_AMOUNT_MATCHES` ni en `master/rules.yaml` ni en `rules.py`: el cruce de importe vive **dentro** de `OrderBelongsToSupplier`. Es evidencia del motor 1.0.0 previo al refactor; el entregable no se afecta (el export solo escribe `file_id`+`result`), pero conviene regenerar/etiquetar la evidencia con el motor actual antes de defenderla.

### 2.3 Escalabilidad y coste — 25 pts · Estado global: ⚠️ (mejora: era ❌; falta volcarlo al entregable)

- ❌ **`docs/report/escalabilidad.typ` sigue VACÍO** (23 bytes: solo `= Escalabilidad y coste`; `wc -c` verificado). Como `albertitos_plan.typ:25` lo incluye, la **página 7 del PDF de entrega está en blanco** (verificado extrayendo el texto de la página 7 con pypdf). El entregable sigue sin responder en su PDF «¿cuántos archivos por segundo, con qué hardware, cómo calculáis el coste?».
- 🆕 ✅ **El contenido ahora EXISTE, escrito y medido, fuera del Typst**:
  - `docs/capacidad_y_coste.md` (10 KB): hardware medido (8 núcleos/16 GB, VLM local PaddleOCR-VL), throughput por escalón (rung 1: 0,4 ms media / 2 636 files/s; rung 2: 42,1 ms; rung 4: 33,9 s media bajo carga, n=28; rung 7: n=29 con 404, no representativo), fórmula de coste explícita (energía con TDP 65 W como cota, tarifa 0,15 €/kWh; coste cloud de lista etiquetado [estimado]), coste lote 1 = 0,00 € medido, límite operativo 4–14 k archivos/h, **plan de volumen 1k/10k/100k** con réplicas de llama-server, y respuesta a nuevos tipos de archivo (escalones sustituibles en `_RUNGS`).
  - `docs/benchmarks_extraccion.md` (9,5 KB): comparativa local vs remoto de los escalones 4/5/7 con metodología y etiquetas [medido]/[estimado]/[no medido].
- ✅ Datos generados por `filemaid.metrics` en `docs/report/escalabilidad_datos.typ` (dry-run T10: 94,2 % texto usable; calibración rung 3; drills 4/4; T23 perfil de carga; resultados lote 1) — listos para consumirse desde `escalabilidad.typ`.
- ⚠️ **Nuevos tipos de archivo**: respuesta estratégica completa en el doc nuevo; el conector real sigue limitado a PDFs/imágenes y el cargador de maestros solo lee CSV (`master.py`), no el Excel de la Caja (`FINAL_v7_DEFINITIVO_ahorasi.xlsx`).

**Lectura:** el criterio de 25 pts pasa de «en blanco» a «escrito pero no entregado». Volcar ~1 página resumen a `escalabilidad.typ` y recompilar es la acción de mayor relación esfuerzo/impacto que queda.

### 2.4 Resiliencia y recuperación — 10 pts · Estado global: ✅ (mejora: el drill 429 ahora tiene evidencia en el repo, pero el código actual no implementa el retry)

✅ **Estado en disco**: PouchDB JS local (LevelDB) como única fuente; config en `_local` no replicada. Nunca `/tmp`.
✅ **Idempotencia/dedup**: caché por página `(page_sha256, extractor_version, config_version)`; `batch_result` por `batch_id` determinista — reejecutar es no-op; export atómico solo con lote completo. 🆕 Ejercitado en real: drill `crash-reanudacion` PASS (2 decididos tras crash, 3 tras reanudar, 0 duplicados; `video/data_drills.json`).
✅ **Reanudación**: `run_lote` reanudable; `filemaid reprocess` + `POST /api/reprocesar/{file_id}`; 40 ficheros de tests (persistencia, replicación, recuperación).
✅ **Degradación**: cada rung registra `skipped:<reason>` y cae al siguiente; cloud jamás respuesta automática.
🆕 ⚠️ **Backoff/Retry-After en el rung cloud**: la evidencia medida AHORA está en el repo (`video/data_drills.json`, trackeado: `backoff-429` PASS — 429×2 con Retry-After, 3 llamadas exactas, delays aplicados; `rung5-provider-caido` PASS — 3 intentos y cola de revisión). **Pero** el código actual de `src/filemaid/extract/rungs/cloud_vlm.py` hace **una única `httpx.post` sin reintentos** (leído completo en esta auditoría: `except Exception → _skip("cloud-vlm-error:…")`), y no hay política de retry en ninguna otra capa de `src/filemaid/extract/` (grep verificado). Los drills se midieron el 2026-09-18 contra una implementación que no está en el árbol actual → **o se reintroduce el retry en el rung, o el ADR-05/drill dejan de corresponder al código** antes de la defensa. Nota aparte: 🆕 commit `12a735f` añadió reintento de notificación ESCALAR en el watcher de escritorio ( `_RETRY_NOTIF_S = 30.0`, con test de regresión) — mejora real de resiliencia de producto, distinta del retry HTTP.

### 2.5 Calidad de ejecución — 10 pts · Estado global: ✅

✅ Arranque de un paso: `./run.sh [app|vlm|desktop]` + `start.py` (stdlib only) — idempotente.
✅ App de escritorio pywebview compartiendo UI Vue y motor (`desktop/app.py`; ADR-07). 🆕 El watcher reintenta notificaciones fallidas en la misma sesión (`12a735f`).
✅ 🆕 **Pulido de flujo frecuente** (`59489fa`): sync en topbar, auto-refresco, confirmación directa en revisión y CTA inteligente post-ingesta (134 insertions en `App.vue`, `IngestView`, `InvoicesView`, `ReviewView`) — reduce fricción en la demo.
✅ 40 ficheros de tests; comprobación puntual ejecutada en esta auditoría: `pytest tests/test_rules_engine.py` → **17 passed** en 0,22 s.
✅ UI en español con cola de revisión, reglas visibles e informe HTML de la frontera NO_PAGAR/ESCALAR.

### 2.6 Bonus: una mejora para Alberto (+10) — Estado global: ✅ (mejora: era ⚠️; falta solo elegir narrativa)

🆕 ✅ **El vídeo está renderizado**: `video/out/filemaid.mp4` — **180,0 s exactos** (verificado del átomo `mvhd`: duration 180000 ms, timescale 1000), 6,4 MB, 8 escenas con métricas medidas (guion en `video/GUION.md`), incluye capturas reales de la UI (`e4ee7b6`, `626b7b2`) y stills exportados (`video/out/still-*.png`). La mejora (app de escritorio + vigilante + revisión humana) está **implementada y mostrada**. Pendiente menor: decidir qué mejora se narra como bonus principal (recomendado: vigilante + notificación ESCALAR, es la más diferencial).

---

## 3. Lote 2 «sorpresa» (sábado)

Requisitos según el enunciado (`caja-de-alberto/README.md`, Makefile del ERP) y estado — **sin cambios sustanciales desde la auditoría anterior, salvo que el mecanismo de reprocesado ya está probado en real con el lote 1**:

| Requisito | Estado | Evidencia y brecha |
|---|---|---|
| +40 facturas nuevas | ⚠️ Datos presentes, sin procesar | `caja-de-alberto/facturas_primin/` = 40 PDFs (verificado). Sin `outcomes_lote2.jsonl`. |
| ERP actualizado | ⚠️ Datos presentes, sin consumir | `erp_export_lote2.csv` (41 líneas), `pedidos_nuevos.csv` (40), `proveedores_nuevos.csv` (5), ERP simulado `alberto_erp.py` (`make erp-lote2`, verificado en el Makefile). **Sigue sin existir cliente HTTP del ERP ni carga de los maestros nuevos**: `master/` solo tiene `pedidos.csv` y `proveedores.csv` propios, y grep de `erp_export|alberto_erp|8009` en `src/filemaid` → 0 resultados. La costura del ADR-03 sigue siendo conceptual. |
| Conservar trabajo | ✅ Por diseño **y probado** | Idempotencia por `(sha256, stage, engine_version, config_version)`; 🆕 el drill `crash-reanudacion` PASS demuestra la reanudación sin duplicados sobre datos reales. |
| Reprocesar tras el cambio | ✅ **Ejercitado en real** 🆕 | `filemaid reprocess` + API; el reprocesado del lote 1 tras el fix ADR-06 (108 facturas, 86 → PAGAR, 0 regresiones, 155,5 files/s warm) está medido en `video/data_impacto.json`. Falta ensayarlo con los datos del sábado. |
| Regla nueva (v4) | ❌ No preparada | `master/rules.yaml` sigue con las 8 reglas v3 (listado completo verificado; no hay versión v4 ni borrador). El mecanismo «regla como DATOS» existe (`enabled` + `thresholds` + `outcomes.on_fail` en YAML), pero no hay plan de la regla del sábado. |
| Frontera NO_PAGAR/ESCALAR como datos | ✅ | `outcomes.on_fail` (NIF/IBAN → ESCALAR) en `master/rules.yaml`; validador que impide que una regla rota pague (probado en `tests/test_rules_engine.py`). |

---

## 4. Veredicto por entregable (resumen ejecutivo)

| # | Requisito | Estado anterior (`867748b`) | Estado actual (`59489fa`) |
|---|---|---|---|
| 1 | `outcomes.jsonl` (500 líneas) | ❌ No existía nada | 🟡 Lote 1 corrido y validado (500/500 match); falta emitir/copiar a la raíz de entrega |
| 2 | `outcomes_lote2.jsonl` (40 líneas) | ❌ | ❌ Sin correr el lote 2 |
| 3 | `albertitos_plan.pdf` | ❌ Sin compilar | ✅ Compilado (13 págs), ⚠️ pág. 7 escalabilidad en blanco; ojo: gitignored |
| 4 | Producto/arquitectura/ADRs (35) | ⚠️ Divergencia ADR-06, evidencia ausente | ✅ ADR-06 conciliado con código; evidencia en repo (matiz: citas `.sdd/metrics/*.json` inexistentes, datos reales en `video/data_*.json`) |
| 5 | Trazabilidad (20) | ✅ faltaba decisión real | ✅ Decisión real ejercitada (FA-8801, reprocesado medido) y mostrada en vídeo; ⚠️ provenance del JSONL con motor 1.0.0 |
| 6 | Escalabilidad y coste (25) | ❌ Sección vacía | ⚠️ Contenido escrito y medido en `docs/capacidad_y_coste.md` + `benchmarks_extraccion.md`; falta volcar a `escalabilidad.typ` y recompilar |
| 7 | Resiliencia (10) | ✅ salvo backoff no verificable | ⚠️→✅ Drill 429 con evidencia en repo, PERO el código actual del rung cloud no implementa retry — conciliar antes de defender |
| 8 | Calidad de ejecución (10) | ✅ | ✅ + pulido UI (`59489fa`) y retry de notificaciones |
| 9 | Bonus (+10) | ⚠️ Sin mostrar | ✅ Vídeo de 3 min renderizado (180,0 s medidos); elegir narrativa |
| 10 | Lote 2 sorpresa | ⚠️ Datos listos | ⚠️ Igual + reprocesado ya probado en real; faltan ERP client, maestros nuevos y regla v4 |

---

## 5. Acciones pendientes priorizadas

| Prio | Acción | Impacto |
|---|---|---|
| **P0** | Emitir `outcomes.jsonl` a la raíz del repo de entrega (`uv run filemaid emit --out outcomes.jsonl` — el store ya tiene el lote 1 completo y validado 500/500) | Sin esto la validación binaria del hackathon falla |
| **P0** | Correr el lote 2 (`facturas_primin`) → `outcomes_lote2.jsonl` (40 líneas) y contrastar file_ids | Ídem |
| **P0** | Escribir `docs/report/escalabilidad.typ` (1 página: hardware, throughput por escalón, fórmula de coste, límites 4–14 k arch/h, plan 1k/10k/100k) consumiendo `escalabilidad_datos.typ` y resumiendo `docs/capacidad_y_coste.md`; recompilar el PDF | El PDF de entrega tiene hoy la pág. 7 en blanco (criterio de 25 pts invisible para el jurado) |
| **P0** | Publicar el repo de entrega separado con EXACTAMENTE los 3 ficheros; ojo: el PDF está gitignored en este repo — copiar el artefacto compilado | El contrato exige 3 ficheros en la raíz de otro repo |
| **P1** | Conciliar retry/backoff: reintroducir la política de reintentos + Retry-After en `cloud_vlm.py` (o wherever viva) y re-ejecutar el drill `backoff-429`, o corregir ADR-05; hoy la evidencia del drill no corresponde al código del árbol | Resiliencia (10 pts) y credibilidad en defensa |
| **P1** | Ensayar el día del lote 2: `make erp-lote2`, cliente/ingesta de los maestros nuevos (`pedidos_nuevos.csv`, `proveedores_nuevos.csv`, estado del export), y borrador de «regla v4 como datos» en `master/rules.yaml` | «Cómo diseñasteis el cambio, el reprocesado y los límites» |
| **P1** | Regenerar la evidencia de outcomes con el motor actual (`runner-1.1.0`) o etiquetar la existente: el JSONL de lote 1 cita 13 códigos de regla del motor 1.0.0 (p. ej. `ORDER_AMOUNT_MATCHES`, hoy dentro de `ORDER_BELONGS_TO_SUPPLIER`) | Coherencia de provenance en defensa |
| **P2** | Arreglar citas muertas: `.sdd/metrics/drills.json|impacto-fix-colapso.json|perfil-carga.json|auditoria-trampas.md` no existen (los datos están en `video/data_*.json`); ADR-05 cita «AGENTS §13» que no existe | Pulido de evidencia citada |
| **P2** | Ensayar en la demo la trazabilidad de UNA decisión end-to-end en vivo (FA-8801 → evidencia → reglas → resultado), apoyándose en las capturas del vídeo | 20 pts de trazabilidad, cierre del círculo |
| **P2** | Elegir la mejora del bonus a narrar (recomendado: vigilante + notificación ESCALAR con reintento) y decidir nº de ADRs si el jurado es estricto con el rango 2–5 (el PDF ya lo defiende) | Bonus +10 / pulido |
| **P3** | Conector maestro xlsx (hoy solo CSV) si se quiere cubrir el Excel de la Caja en la demo | Robustez de producto |
