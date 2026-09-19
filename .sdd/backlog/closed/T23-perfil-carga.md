# T23 · Perfil de carga medido: régimen completo en la caja
assignee: W3
priority: p2

## Objetivo
La sección de escalabilidad necesita el sistema bajo carga REAL, no por partes.
Tu UI (T16) está integrada y el store del lote 1 está post-fix (433/22/45).

## Qué medir (todo con `time`, `/usr/bin/time -v` o psutil desde Python)
1. Corre el UI (uvicorn) apuntando al store real del lote 1
   (`.sdd/lote1` symlink o config) y mide: RAM RSS de uvicorn, RAM total del
   sistema, tiempo de respuesta p95 de las 5 pantallas (httpx con
   `--traces` o curl -w) con las 500 facturas y los 45 escalados.
2. Lanza 2 runners concurrentes en `--limit 50` sobre copias de store temporales
   (NUNCA el store real) + llama-server corriendo + tu UI: mide CPU por proceso,
   RAM, y degrada? (los drill de T12 ya prueban aislamiento).
3. Entrégalo como `.sdd/metrics/perfil-carga.json` + párrafo para
   escalabilidad.typ: límite práctico de concurrencia en esta caja (8 cores /
   12 GB), con la fórmula de coste ya existente intacta.
4. Si algún componente se degrada (p.ej. UI > 2 s/página con 500 filas), es un
   ROJO con causa (paginación pendiente) — no lo arregles a mano: documéntalo.

## Criterios de aceptación
- perfil-carga.json con: RSS por componente, p95 de pantallas, concurrencia
  máxima soportada medida, nota de qué sería diferente con más RAM.
- test: el JSON se genera desde la corrida sembrada (sin red).
- pytest+ruff verde; ticket a closed en el mismo commit.

## Cerrado — decisiones tomadas (W3)

- **`albertitos.perfil`** (`python -m albertitos.perfil`): mide el régimen
  COMPLETO en la caja — UI real (subproceso uvicorn con
  ALBERTITOS_STORE=.sdd/lote1/ledger, SOLO LECTURA) + N runners concurrentes
  reales (`python -m albertitos.run`, stores TEMPORALES, nunca el real) +
  llama-server (health medido). Mediciones vía /proc (RSS VmRSS pico, CPU
  utime+stime) y /proc/meminfo — sin dependencia nueva (psutil fuera).
- **Corrida real**: 2 runners (limit 50, text-layer para no colgarse en rung
  4 serial de 15-60 s/página) + UI con el lote 1 completo. MEDIDO: UI p95
  < 12 ms en las 5 pantallas con 500 facturas cargadas; 108-110 files/s por
  runner en paralelo; RSS ~96 MB UI / ~38 MB runner; 8 GB RAM libres de 12;
  llama-server up; **0 ROJOS ⇒ concurrencia de 2 runners + UI soportada MEDIDA**.
- **`perfil-carga.json`**: régimen, RSS/CPU por componente, latencias
  p50/p95/max por pantalla, RAM, límite práctico (estimado etiquetado) y
  nota de por qué más RAM no cambia nada (el límite es CPU en rung 3/4).
  Párrafo nuevo en `escalabilidad.typ` citando la fuente; PDF recompilado.
- **ROJO como código**: `rojos_de()` — UI > 2 s/página con el lote completo ⇒
  ROJO con causa, documentado y no parcheado a mano (regla del ticket).
- **Ajustes honrados en el guion**: lote1.json evolucionó (reprocesado T18:
  433/22/45 final, rung 4 máx 60,1 s con timeouts controlados) — DEFENSA.md
  actualizado y el test exige que el guion cite la medición ACTUAL (dinámico).
- **Tests**: perfil JSON desde corrida sembrada (UI + runner real en loopback,
  sin red externa) + clasificación ROJO. 206 passed, ruff limpio, sin secretos.
