# T38-F6 · Los overrides humanos de la UI NUNCA se consumen
assignee: W2 (pipeline/runner), W1 disponible
priority: p1
severidad: p1 (producto: el bucle de revisión humana es un callejón sin salida)

## Hallazgo
La UI encola correcciones humanas en `.sdd/review-queue/overrides.jsonl`
(ui/app.py `resolver`) con provenance, y `ReviewQueue.read_overrides()`
(src/albertitos/extract/review.py) sabe leerlas — pero NINGÚN componente del
pipeline las consume: `grep -rn "read_overrides" src/` devuelve solo la
definición. AGENTS.md §7 y T7 exigen: override ⇒ alimenta SOLO la extracción
(candidato con provenance) ⇒ el motor recalcula. Hoy: el override se encola y
muere; la decisión de la factura no cambia jamás.

## Reproducción (pasos exactos)
1. Sandbox con un store y un outcomes.
2. Escribir una línea override en `<sandbox>/review-queue/overrides.jsonl`:
   {"invoice_id": "...", "file_id": "...", "campo": "nif", "valor": "B46102331", ...}
3. Correr el runner con --force sobre ese file_id.
4. La decisión no cambia y la corrección no aparece como candidato en
   ningún sitio. (grep -rn read_overrides src/ ⇒ solo la definición.)
## Propuesta
En `_decide_and_record`: leer overrides pendientes del file_id, inyectarlos
como candidatos `extraction_method: "humano"` (conf 1.0, feature_ref
"override:<cuando>") en los campos correspondientes, marcarlos CONSUMIDOS
(moverlos a overrides.jsonl.processed o flag), y re-decidir. El motor no
cambia. ~60 líneas + tests.

## Resolución (W4, T39 — ciclo evaluador-implementador)
APROBADO e implementado. p1 real: el bucle de revisión humana era un callejón
sin salida (la UI encolaba overrides que NADIE consumía — verificado con
grep). Coste ~90 líneas, beneficio: §7/T7 se cumplen de verdad. El motor no
cambia; la corrección humana entra SOLO como candidato de extracción y el
motor determinista recalcula.

- `src/albertitos/extract/review.py`: `read_overrides_pendientes()`,
  `marcar_consumidas()` — marcador `kind=consumido` APPEND-ONLY en
  `overrides.jsonl` (el histórico jamás se reescribe; crash entre inyectar y
  marcar ⇒ re-run re-inyecta y re-decide igual, idempotente).
- `src/albertitos/run.py`: `aplicar_overrides()` (función PURA, testeable) —
  candidato `extractor="humano"`, conf 1.0, provenance `override:<cuando>`,
  `feature_ref` trazable; campos numéricos convertidos con `parse_amount_float`
  (el motor compara floats); valor no convertible ⇒ NO se pierde en silencio:
  evidencia `outcome="descartado"`. Inyección en `_decide_and_record` tras el
  parse, antes de `decide()`; filas de evidencia `stage="override"` con
  outcome `aplicado`/`descartado`; consumo marcado SOLO tras decidir.
- Tests: `tests/test_overrides_consumo.py` (7): inyección numérica/texto,
  campo nuevo, descarte con señal, humano gana por confianza, ciclo
  pendiente/consumido append-only, e2e con el Runner real (override aplicado
  + evidencia + no re-aplicación).
- Verificado: pytest verde, ruff limpio, validador de contrato 500/500 sobre
  el lote 1 tras el cambio en src/. Decisión=motor intacto: sin overrides en
  cola, el pipeline es byte a byte idéntico.
