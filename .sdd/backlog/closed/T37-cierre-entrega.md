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

## Cerrado — decisiones tomadas (W3)

- **Informe final post-fix** (14 páginas): bindings nuevos en
  `escalabilidad_datos.typ` desde los orígenes T18 (impacto-fix-colapso:
  108 reprocesados, 86 NO_PAGAR→PAGAR, 0 regresiones, validación OK),
  T23 (perfil de carga: peor p95 7,7 ms, 108-110 files/s, 0 ROJOS) y
  distribución final 433/22/45; Modo Alberto + ADR-07 citados. ADR-06 y
  ADR-07 ya integrados por W1/W2 en el informe. PDF recompilado (14 páginas,
  verificado con pypdf).
- **Repo de entrega re-staged** (`scripts/stage_delivery.sh` con los
  outcomes DEFINITIVOS post-fix): validador 500/500 OK, exactamente
  outcomes.jsonl + albertitos_plan.pdf (lote 2 llega a las 16:00 UTC —
  re-staging con el mismo comando). Higiene de secretos sobre lo que se
  copia: limpia.
- **`.sdd/metrics/entrega.json`**: sha256+bytes de cada entregable del repo
  de entrega, versión de reglas (v3.0-2026-09-19 / runner-1.1.0),
  distribución corrida original (347/108/45) y final post-fix (433/22/45),
  impacto del fix T18 (108 reprocesados) y checklist de defensa
  (simulacro 15/15 PASS).
- **Tests** (3, test_entrega.py): estructura de entrega.json, sha256 de los
  entregables cuadran contra los ficheros reales del repo de entrega,
  repo válido (exactamente los entregables) y sin secretos. Suite: 288
  passed, ruff limpio.
