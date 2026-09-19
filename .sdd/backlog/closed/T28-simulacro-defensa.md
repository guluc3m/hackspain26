# T28 · Simulacro de defensa contra el estado REAL
assignee: W3
priority: p1

## Objetivo
Ensaya el guion (`docs/report/DEFENSA.md`) contra el estado ACTUAL: cada
número citado debe existir en los JSONs medidos post-fix (433/22/45, p95 de
pantallas, runners 108 files/s, drills 4/4, 471/29/0...). Y la demo del paso 1
incorpora el resumen ejecutivo (`resumen_alberto.pdf/html`, T26).

## Qué hacer
1. `src/albertitos/simulacro.py` + `python -m albertitos.simulacro`:
   verifica cada afirmación numerada del guion contra los JSON medidos
   ACTUALES (lote1.json, perfil-carga.json, drills.json, corpus-dryrun.json,
   impacto-fix-colapso.json) y la preparación de la demo (store accesible,
   5 pantallas 200, resumen ejecutivo regenerable). Salida:
   `.sdd/metrics/simulacro.json` (pass/fail por verificación).
2. DEFENSA.md: añadir el resumen ejecutivo al paso 1 de la demo + checklist
   (comando `uv run python -m albertitos.resumen`).
3. Si el guion se desincroniza de la medición (el store es objetivo móvil),
   el simulacro lo marca ROJO con causa — se actualiza el guion, nunca se
   finge.

## Criterios de aceptación
- Simulacro verde contra el estado real; JSON por verificación.
- Test: el flujo corre con fixture sembrado; un guion con cifras erróneas
  falla.
- pytest+ruff verde; ticket a closed en el mismo commit.

## Cerrado — decisiones tomadas (W3)

- **`albertitos.simulacro`** (`python -m albertitos.simulacro`): 15
  verificaciones del guion contra el estado REAL — fuentes citadas existen,
  distribución final 433/22/45 (lote1.json × outcomes definitivo del repo de
  entrega), perfil de carga (peor p95 citado == medido, files/s de runners
  en rango), drills 4/4, dry-run 471/29/0, resumen ejecutivo regenerable
  desde store×maestro, y las 5 pantallas de la UI en 200 in-process
  (TestClient, sin red). Salida: `.sdd/metrics/simulacro.json` + exit 0/1.
- **ROJO honesto**: el primer intento detectó 3 desincronizaciones reales y
  las documentó: (1) outcomes-lote1.jsonl en metrics era PRE-fix (el
  simulacro ahora usa el outcomes DEFINITIVO del repo de entrega
  post-fix 433/22/45), (2) el p95 citado en el guion (11,9 ms) estaba
  desactualizado — W1 re-midió 7,7 ms; guion actualizado, y (3) el resumen
  del paso 1 faltaba en el guion — añadido.
- **DEFENSA.md actualizado**: apertura con 433 PAGAR por 2 331 130,43 €,
  paso 5 de la demo = resumen ejecutivo (resumen_alberto.pdf/html), sección
  3 con el perfil de carga T23, checklist con los comandos de resumen y
  simulacro. Los saltos de línea del guion ya no engañan al verificador
  (normalización de espacios).
- **Tests** (3): simulacro verde con estado coherente (JSON por
  verificación), guion con cifras erróneas ⇒ ROJO con causa (se actualiza
  el guion, nunca se finge), verificaciones individuales. Suite: 232 passed,
  ruff limpio, sin secretos.
