# T40 · Implementador del LOOP (W5)
assignee: W5
priority: p1

## Tu rol en el loop infinito (T38, .sdd/backlog/open/T38-protocolo-loop.md)
Eres el 3º EVALUADOR-IMPLEMENTADOR. Tu dominio preferente son los TESTS y la
ROBUSTEZ de la infraestructura de verificación: los hallazgos T38F* que sean
flaky-tests, carreras de puertos, fixtures compartidos, timeouts — arregla la
CAUSA, no el síntoma. También: docstrings/documentación de operación que
falten, y el grep de higiene de secretos como test permanente (hoy solo
existe en T7).

## Método
Evalúa cada ticket abierto (coste/riesgo/beneficio, adherencia a T38),
descarta documentando, implementa los aprobados: tests + commit + ticket a
closed, UNO POR COMMIT. Coordínate evitando los ficheros que W3 y W4 estén
tocando (W3 desde el principio de la cola, W4 desde el final, tú los de
tests/robustez).

## Reglas duras (T38)
- Entregables intocables; validador 500/500 tras cada cambio en src/.
- Decisión = motor versionado; política NO_PAGAR/ESCALAR fuera de tu alcance.
- pytest+ruff verde en cada commit; higiene de secretos; sin tickets no hay commit.
- Si llega el aviso de lote 2 / congelación: pausa o pasa a SOLO-LECTURA.
