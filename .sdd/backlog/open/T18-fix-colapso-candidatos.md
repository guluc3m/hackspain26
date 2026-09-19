# T18 · Fix colapso de candidatos en el motor + reprocesado del lote 1
assignee: W1
priority: p0

## Contexto (tu propio T17, hallazgo principal — ROJO)
El motor colapsa `values[]` con el PRIMER candidato de `total` (la línea
«Subtotal») y lo compara contra el importe CON IVA del maestro ⇒ 87 de los
108 NO_PAGAR son FALSOS (un candidato sí matchea con tolerancia 0,01). 14
genuinos: ningún candidato matchea. La doctrina §2 prohíbe colapsar sin
registrar cuál se eligió y por qué.

## Cambio en el motor (semántica exacta)
Para las reglas que comparan un campo contra el maestro
(`ORDER_AMOUNT_MATCHES`, `TOTALS_MUST_MATCH`, `IVA_CONSISTENT`,
`IBAN_MATCHES_MASTER`):
- La regla evalúa TODOS los candidatos del campo.
- Si exactamente uno matchea dentro de tolerancia ⇒ PASS citando ESE
  candidato (provenance: extractor + value + feature_ref en el verdict).
- Si VARIOS matchean ⇒ PASS con nota de ambigüedad (los candidatos concuerdan
  entre sí dentro de tolerancia — no es señal de fraude).
- Si NINGUNO matchea ⇒ FAIL (los 14 genuinos no cambian).
- PROHIBIDO: que un resultado previamente PASS pase a FAIL por este cambio.

## ADR nuevo (ADR-06) en la plantilla del informe
"Selección de candidato con provenance": contexto (87/108 falsos medidos),
alternativas (1er candidato / max confianza / cualquiera-matchea / escalar-si-
ambiguo), decisión (evaluar todos + provenance), consecuencias, evidencia
(T17 + reprocesado).

## Reprocesado
Con tu fix en el motor: re-ejecuta el runner (idempotente por diseño — fuerza
reproceso con --only sobre los afectados o borra la cache de decisión; usa el
mecanismo de T13 si aplica) y regenera outcomes.jsonl + lote1.json. Validador
en verde. Diff ANTES/DESPUÉS → .sdd/metrics/impacto-fix-colapso.json
(exactamente 87 NO_PAGAR→PAGAR esperados, 14 genuinos se mantienen, 0
regresiones en el resto).

## Criterios de aceptación
- Test: candidato Subtotal + TOTAL donde TOTAL matchea el maestro ⇒ PASS con
  provenance del candidato; sin candidato matcheando ⇒ FAIL; dos candidatos
  matcheando ⇒ PASS con nota.
- Test: la corrida completa del lote tras el fix produce EXACTAMENTE el diff
  esperado (87 cambiando, 14 NO_PAGAR genuinos se mantienen).
- Validador 500/500 verde; pytest+ruff verde; ticket a closed en el mismo commit.
