# T30 · BONUS: escalados priorizados por dinero en riesgo
assignee: W3
priority: p1

## Objetivo
Mejora aditiva para Alberto: los 45 escalados priorizados por DINERO EN
RIESGO — «revisando estas N facturas cubres el X % del dinero en juego».
Alimenta el resumen ejecutivo (T26); no toca el motor ni las reglas.

## Qué hacer
1. `datos_resumen` añade la sección `riesgo`: total € en riesgo (escalados
   con importe en el maestro), cuántos quedan «sin importe», y el PLAN
   ordenado por importe desc con suma acumulada y % del riesgo cubierto.
2. `resumen_alberto.html/.pdf`: nueva subsección con el plan (y el nº de
   facturas para cubrir el 80 % del dinero en riesgo).
3. Sin datos ⇒ PENDIENTE honesto. Fuentes citadas (store × maestro).

## Criterios de aceptación
- Test: sumas acumuladas EXACTAS contra el store sembrado; sin importes ⇒
  PENDIENTE; el nº para cubrir el 80 % es el mínimo k con k facturas.
- pytest+ruff verde; ticket a closed en el mismo commit.
## Cerrado — decisiones tomadas (W3)

- **Plan por dinero en riesgo (T30, aditivo)**: `datos_resumen` añade la
  sección `riesgo` — total € en juego en la cola de ESCALAR (importes del
  maestro Pedidos_2026 vía file_id→pedido), nº sin importe conocido (honesto),
  y el PLAN ordenado por importe desc con suma acumulada y % del riesgo
  cubierto. `para_cubrir_80_pct` = mínimo k de facturas (por importe) que
  cubren el 80 % del dinero en juego. Puro agregado del resumen: el motor y
  las reglas no se tocan (la prioridad es presentación para Alberto).
- **Renderizado** en resumen_alberto.html y .pdf (top-10 del plan + tarjeta
  del total + la frase "revisando las N primeras cubres el 80 %").
- **Demo real**: 116 163,14 € en riesgo en la cola de 45 escalados (32 sin
  importe en el maestro — avisadas); con **3 facturas** se cubre el 80 %
  (encabeza la outlier de 84 700,00 € — trampa del corpus, escalada
  correctamente).
- **Sin datos ⇒ PENDIENTE** (plan vacío, para_cubrir_80_pct=PENDIENTE con
  etiqueta sin datos), jamás ceros falsos — testeado.
- **Incidente ajeno documentado**: la suite en solitario fallaba en
  test_drill_rung4_live (T24, W1) porque el submodule caja-de-alberto no
  estaba inicializado en ESTE worktree — inicializado user-space
  (`git submodule update --init`, solo lectura). Queda 1 flaky de timing en
  ese drill en vivo cuando llama-server está en uso (verde en suite
  completa) — avisado para W1.
- **Tests** (4 nuevos): sumas acumuladas exactas, matemática del 80 %
  (2 escaladas: k=2 porque 6 540,90 < 0,8 × 11 176,16), HTML+PDF con el plan,
  placeholder PENDIENTE. Suite: 252 passed, ruff limpio, sin secretos.
