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
