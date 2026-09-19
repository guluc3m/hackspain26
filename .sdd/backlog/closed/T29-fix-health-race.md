# T29 · Fix del race health-bajo-carga (4 estados del stub)
assignee: W2
priority: p1

## Objetivo
Implementar el fix propuesto en T24 (`.sdd/metrics/drill-rung4-live.json`,
sección "bug"): el sonda `hooks_reales.health()` da UP mientras llama-server
carga el modelo (el chequeo de /health cae en `except OSError: return True`
con el 503 de carga). El sonda debe exigir `GET /health == 200`.

## Requisitos
- `health()` listo de verdad: /v1/models 200 Y /health 200; cualquier otra
  cosa (503 de carga, conexión rechazada, timeout) ⇒ False.
- Stub de llama-server con los 4 ESTADOS del ciclo de vida real:
  `up` (health 200), `loading` (/v1/models 200 pero /health 503 — el race),
  `hung` (acepta conexiones y no responde — timeout del cliente), `down`
  (rechaza conexiones — proceso muerto). Transiciones inyectables.
- Tests: health() True SOLO en `up`; el gate de arranque del drill aborta
  limpio si el stub está en `loading` (no correr con el modelo cargando);
  `_esperar_health` devuelve False si el stub queda en `loading`/`hung`/`down`
  (la timeline lo registra, sin colgar).

## Criterios de aceptación
- pytest+ruff verde; no rompe el determinismo (no toca decisiones ni store);
  ticket a closed en el mismo commit.

## Nota de origen
Ticket dictado por el coordinador tras T24; la cola `open/` estaba ya vacía
(entrega cerrada en T25-T28) y el fichero no existía: se transcribe aquí tal
cual antes de implementar.
