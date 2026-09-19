# T33-M4 · Evidencia por reintento de health del rung 4 (pantalla Salud)
assignee: W2
priority: p2

## Objetivo
`run_vlm` (T29) hace hasta N reintentos de health durante la carga del
modelo, pero la evidencia solo registra el SKIP final: la pantalla Salud no
ve cuántas páginas esperaron y cuánto. Mejora aditiva: una fila de evidencia
por reintento (stage `extract:rung4_health`, outcome `retry`, detail con
estado/motivo/pausa) — cero cambios en decisiones, cache o política.

## Cambio
- `rungs.py::run_vlm`: dentro del bucle de backoff, `ctx.add_evidence` por
  intento. Latencia = tiempo desde t0.
- Filas nuevas con stage distinto: los contadores existentes (que filtran
  `stage='extract:rung4_vlm'`) no cambian.
