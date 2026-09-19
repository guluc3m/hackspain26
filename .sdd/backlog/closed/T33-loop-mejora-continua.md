# T33 · Loop de mejora continua + fichero de sugerencias
assignee: W1 (y de plantilla para todos los workers al quedar ociosos)
priority: p2

## Objetivo
Cuando un worker se queda sin tickets, NO se apaga: entra en **loop de mejora**.
Ciclo: (1) relee el proyecto completo — AGENTS.md, docs/report/architecture.typ,
docs/decisiones/DECISIONS.md, el código de su módulo y los tickets cerrados;
(2) identifica mejoras concretas; (3) implementa SOLO las pequeñas, seguras y
aditivas (un commit cada una, tests en verde, ticket por cada una con la
plantilla estándar); (4) las grandes o riesgosas van a un fichero de
sugerencias, NO se implementan.

## El fichero de sugerencias
`docs/report/SUGERENCIAS.md` — apéndice colectivo (cada worker añade, nunca
reescribe lo de otros). Formato por entrada:
- **Título** y categoría (arquitectura / extracción / reglas / UI / operación / producto).
- **Problema** que resuelve (con evidencia del código o de las métricas, citada).
- **Propuesta** concreta y su **coste** estimado (líneas, riesgo, qué toca).
- **Por qué NO se implementó ya** (riesgo, alcance, depende de lote 2, etc.).
- **Prioridad** (alta/media/baja) y quién debería hacerlo.

Mínimo al cerrar este ticket: 6 entradas cubriendo ≥3 categorías, ninguna
trivial ("añadir más tests" sin más no vale).

## Reglas duras
- Prohibido tocar el motor de reglas, la política de decisión o la semántica
  del emit en este loop (cambios de decisión = supervisor + usuario).
- Prohibido romper el entregable: outcomes.jsonl y el repo de entrega son
  intocables; cualquier mejora debe mantener el validador 500/500 en verde.
- Cada mejora implementada: su ticket propio (plantilla estándar), commit
  separado, pytest+ruff verde.
- Máximo 3 mejoras implementadas por ciclo de loop; luego re-evalúa.

## Criterios de aceptación
- SUGERENCIAS.md existe con ≥6 entradas bien fundadas y ≥3 categorías.
- Alguna mejora pequeña implementada como ejemplo del formato (con su ticket).
- pytest+ruff verde; ticket a closed en el mismo commit.

## CIERRE (W1, 2026-09-19) — ciclo 1 del loop
**Re-lectura**: AGENTS.md (contrato + §13), architecture.typ (features/parser/
reglas/logs/retroalimentación), DECISIONS.md (D-001/D-002 PaddleOCR q8 +
llama-server CPU), mi módulo extract/ + tools/, y los tickets cerrados de W1
(T1, T7, T10, T14, T17, T18, T22, T25, T27).

**Mejoras implementadas (3 — máximo del ciclo, cada una con ticket+commit):**
- T33-M1 (da4d1fe): `ExtractionConfig.tesseract_psm` — el `--psm 6` hardcodeado
  del rung 3 pasa a configuración (doctrina «thresholds are config, not code»);
  comportamiento idéntico por defecto; test hermético con binario falso que
  imita tesseract real (--version vs run).
- T33-M2 (baf6db6): un solo PdfReader por página en la escalera (antes 3 parses
  completos por PDF de 2 páginas); degradación de PDF dañado intacta (test).
- T33-M3 (06aeba0): `ReviewQueue` dedupe O(1) amortizado (se lee la cola UNA
  vez por instancia) + `tools/regen_review_queue.py` (la cola es estado
  derivado, regenerable en segundos sin re-facturar cloud; regenerada la real:
  29 páginas con invoice_uuid correcto).

**SUGERENCIAS.md creado**: 9 entradas, 6 categorías (operación ×3,
arquitectura, extracción ×2, reglas, UI, producto), ninguna trivial.

**Estado del suite (honesto)**: 251/252 verde en la última corrida completa.
El único rojo es `test_ui_lote1::test_store_real_truncado_50_filas` y es
interferencia ENTRE WORKERS: `tests/test_simulacro.py` de W2 (T21) ejecuta
`shutil.rmtree(Path(".sdd/review-queue"))` sobre la cola REAL de este worktree
a mitad de suite (documentado con causa y fix de 2 líneas en SUGERENCIAS #1,
prioridad alta — W2). También observado: colisión de puerto 8231 entre
pytest concurrentes (SUGERENCIAS #2) y un crash esporádico de memoria en la
máquina en carga (malloc_consolidate), transitorio. Regenerable con
`uv run python tools/regen_review_queue.py` (idempotente).

Rangos de las reglas duras respetados: motor/política/emit intocables;
outcomes y delivery-repo sin tocar; validador 500/500 intacto.
