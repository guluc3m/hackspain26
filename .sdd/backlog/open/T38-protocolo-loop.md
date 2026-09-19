# T38 · Protocolo del LOOP infinito: cazar bugs → generar ideas → evaluar e implementar
assignee: TODOS (rotativo)
priority: p1

## Regla del usuario (permanente)
Cuando los 3 workers están libres, NO se apagan: entran en **loop infinito de
mejora** con 3 roles que ROTAN cada ciclo:
- **CAZADOR (bugs)**: busca bugs, issues y fallos reales. Instrumentos: suite
  completa, validador de contrato, drills, correr el runner sobre fixtures,
  leer rutas de código críticas (extract/parse/rules/store/ui), revisar el
  ledger y la telemetría por eventos raros. SALIDA: un ticket por hallazgo con
  REPRODUCCIÓN (test que falla o pasos exactos) y severidad (p0/p1/p2).
- **IDEAS (mejoras)**: propone mejoras de producto, arquitectura, UX, coste y
  defensa. Instrumentos: releer AGENTS.md + hackathon.maisa.ai + rúbrica +
  SUGERENCIAS.md existente + el código. SALIDA: entradas nuevas en
  `docs/report/SUGERENCIAS.md` (formato T33) y, si una idea es pequeña y
  segura, su propio ticket listo para implementar.
- **EVALUADOR-IMPLEMENTADOR**: lee los tickets que dejaron los otros dos,
  descarta los que no valen (triviales, rompen doctrina, riesgo sin beneficio),
  evalúa los demás (coste/riesgo/beneficio) e IMPLEMENTA los aprobados: tests
  + commit + ticket a closed, uno por commit.

## Rotación
Cada ciclo (≈ un turno de trabajo, lo marca el supervisor): CAZADOR→IDEAS,
IDEAS→EVALUADOR, EVALUADOR→CAZADOR. El supervisor anuncia el nuevo rol en el
mensaje de continuación.

## Reglas duras (adhesión a las reglas del hackathon — NO NEGOCIABLE)
1. **Entregables intocables**: `outcomes.jsonl` (500), `outcomes_lote2.jsonl`,
   el repo de entrega y `albertitos_plan.pdf` compilado. Ningún cambio puede
   invalidarlos; tras cada cambio en src/, el validador debe seguir en
   500/500.
2. **Decisión = motor**: prohibido que un LLM, un humano o una "mejora" altere
   el resultado de una factura fuera del motor de reglas versionado. Cambios
   de política NO_PAGAR/ESCALAR: SOLO el supervisor con el usuario (ADR).
3. **Calidad antes que nada**: cada commit con pytest+ruff en verde. Si una
   mejora rompe algo, se revierte antes de continuar.
4. **Higiene de secretos**: grep antes de cada commit (AGENTS.md §13).
5. **Estado del lote 2**: durante la llegada/procesado del lote 2 (16:00 UTC)
   el loop se PAUSA — el procesado del lote manda.
6. **Ventana de congelación**: a partir del aviso del supervisor (domingo
   mañana), el loop pasa a modo SOLO-LECTURA: se cazan bugs y se documentan en
   SUGERENCIAS.md, pero NO se implementan cambios en src/ (solo docs/tests).
7. Cada hallazgo/implementación queda trazado: ticket + commit + evidencia.
   Sin tickets no hay commit.

## Criterios de aceptación (para cerrar ESTE ticket nunca — es el protocolo)
Este ticket NO se cierra: es el contrato del loop. Cada ciclo produce commits
trazados y, como mínimo acumulativo por ciclo: ≥1 hallazgo documentado con
repro, ≥2 entradas en SUGERENCIAS.md, ≥1 mejora implementada con tests.
