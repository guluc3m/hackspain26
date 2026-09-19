# T38-ID1 · «Llegó el lote 2»: ingesta + emisión + staging en un comando
assignee: W2
priority: p1 (listo para implementar; el sábado 16:00 UTC manda)

## Objetivo
T21 dejó el flujo del sábado documentado como SECUENCIA MANUAL (docstring de
`lote2.py`: run con v4 + run-id lote2 + emit-scope lote, luego
stage_delivery). A las 16:00 UTC con Alberto delante, eso son pasos que
pueden equivocarse de orden. Un comando atado y verificado elimina el error
humano: `bash scripts/lote2_llego.sh <dir-lote2>`.

## Cambio (additivo; no toca runner/store/emit)
1. **Chequeo previo**: el dir existe, tiene ~40 PDFs, y NINGÚN nombre ya
   está en el lote 1 (sobreposición por basename = error de ingesta). Si
   falta `regla_v4.yaml` o el lote 2 no llega a 40, FALLA LIMPIO sin tocar
   nada (patrón stage_delivery).
2. **Ingesta**: `python -m albertitos.run --facturas <dir> --outcomes
   outcomes_lote2.jsonl --rules src/albertitos/rules/regla_v4.yaml
   --run-id lote2 --emit-scope lote` (el flujo exacto de T21).
3. **Validador** contra el dir del lote 2; si falla, aviso y STOP (el
   store conserva el histórico; re-run es idempotente).
4. **Staging**: `bash scripts/stage_delivery.sh` (2→3 entregables).
   Output final: resumen legible en español (n ingestados, resultados,
   validación OK, staging listo).

## Test
Fixture con 2 PDFs nuevos (fixtures no usados por el lote 10) + regla v4:
el script pasa de 0 a 2 líneas en outcomes_lote2.jsonl sin TOCAR
outcomes.jsonl (hash antes/después) y de staging con 2→0 errores del
validador. Caso negativo: un PDF repetido del lote 1 ⇒ fallo limpio.

## Por qué un ticket aparte del propio script
T38 (IDEAS): las ideas pequeñas y seguras llevan su ticket listo para
implementar; implementarlo es del EVALUADOR-IMPLEMENTADOR del ciclo
siguiente. ~60 líneas de bash + test.
