# T39 · Implementador del LOOP (W4)
assignee: W4
priority: p1

## Tu rol en el loop infinito (T38, .sdd/backlog/open/T38-protocolo-loop.md)
Eres el 2º EVALUADOR-IMPLEMENTADOR. Trabaja el extremo opuesto de la cola de
tickets abierta (W3 toma desde el principio, tú desde el final) para no pisar
a W3: revisa `.sdd/backlog/open/` y los hallazgos T38F* — evalúa (coste/riesgo/
beneficio, adherencia a T38), descarta documentando, e implementa los
aprobados: tests + commit + ticket a closed, UNO POR COMMIT.

## Dominio preferente
App escritorio (T35), presentación Remotion (T32/T36), UI Modo Alberto (T34),
telemetría (T31) — los módulos que W3 no está tocando ahora mismo.

## Reglas duras (T38)
- Entregables intocables; validador 500/500 tras cada cambio en src/.
- Decisión = motor versionado; política NO_PAGAR/ESCALAR fuera de tu alcance.
- pytest+ruff verde en cada commit; higiene de secretos; sin tickets no hay commit.
- Si llega el aviso de lote 2 / congelación: pausa o pasa a SOLO-LECTURA.
