# T37 · Cierre de entrega: informe final + repo de entrega actualizado
assignee: W3
priority: p0

## Objetivo
Dejar la entrega en estado "solo falta el lote 2": PDF final con TODOS los
números post-fix (433/22/45, auditoría T17, impacto del colapso T18, drills
T24, Modo Alberto T34, app escritorio T35, presentación T32/T36) y el repo de
entrega re-staged.

## Tareas
1. Regenera `escalabilidad_datos.typ` desde .sdd/metrics (tu flujo T15) con
   todos los orígenes nuevos; recompila `albertitos_plan.pdf` (typst ya en
   ~/.local/bin).
2. Añade al informe el ADR-07 (app escritorio: pywebview > Electron, con el
   argumento) y el cierre del ADR-06 (colapso de candidatos: 87/108 falsos
   medidos → fix → re-procesado con diff sin regresiones).
3. Ejecuta `scripts/stage_delivery.sh` — verifica que el repo de entrega tiene
   EXACTAMENTE outcomes.jsonl + albertitos_plan.pdf (+ outcomes_lote2.jsonl
   cuando exista, hoy NO) y que el validador pasa 500/500.
4. Vuelca el resumen de entrega en .sdd/metrics/entrega.json: lista de
   entregables con su sha256 (los 3 archivos del repo de entrega), versión de
   reglas, distribución final, y el estado de la checklist de defensa
   (DEFENSA.md).
5. Higiene: grep de secretos sobre TODO lo que va al repo de entrega.

## Criterios de aceptación
- PDF recompilado con los números post-fix; ADR-07 presente.
- Repo de entrega válido (validador verde, exactamente los archivos, sin secretos).
- entrega.json con los sha256 de los entregables.
- pytest+ruff verde; ticket a closed en el mismo commit.
