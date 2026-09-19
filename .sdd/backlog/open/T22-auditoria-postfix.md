# T22 · Re-auditoría de trampas contra el outcomes POST-fix
assignee: W1
priority: p0

## Objetivo
T18 cambió el motor (ADR-06) y el outcomes pasó a 433 PAGAR / 22 NO_PAGAR /
45 ESCALAR. Tu tabla VERDE/ROJO de T17 debe seguir siendo VERDE en el nuevo
outcomes — y ahora además los 86 falsos pasados a PAGAR deben tener
provenance del candidato elegido.

## Qué verificar
1. Todas las trampas de T17 contra `outcomes.jsonl` (regenerado): fantasma ×3
   ESCALAR, FA-8801 2ª copia, instrucciones embebidas, outlier, pendiente_revisar,
   26 scans ESCALAR.
2. Los 22 NO_PAGAR restantes: distribución por código de regla; los 14 genuinos
   del T17 deben seguir NO_PAGAR (0 regresiones), y ningún PAGAR nuevo debe
   carecer de provenance del candidato en el store.
3. Muestreo de 20 PAGAR nuevos (los que cambió el fix): verifica que el
   candidato citado en el verdict es el que matchea el maestro y que la
   tolerancia 0,01 se respetó — auditoría de provenance, no de fe.

## Entregable
`.sdd/metrics/auditoria-postfix.md` (tabla VERDE/ROJO de nuevo) +
`regenera lote1.json` vía `python -m albertitos.metrics` si el runner ya dejó
el store completo: el lote1.json debe describir las 500 (n_archivos=500,
distribucion final 433/22/45, files_per_s, rungs_invocados) y el diff del fix
va en impacto-fix-colapso.json — separa ambos, no mezcles schemas.

## Criterios de aceptación
- Tabla VERDE/ROJO completa; cualquier ROJO con causa documentada.
- test_defensa en verde con el lote1.json regenerado (schema estable: n_archivos
  + distribucion + files_per_s).
- pytest+ruff verde; ticket a closed en el mismo commit.
