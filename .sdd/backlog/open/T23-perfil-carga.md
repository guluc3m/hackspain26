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
