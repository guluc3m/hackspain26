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
