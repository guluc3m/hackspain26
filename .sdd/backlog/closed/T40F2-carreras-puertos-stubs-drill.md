# T40F2 · Carreras de puertos y tmp compartidos en los stubs del rung 4 (drill + hardening)
assignee: W5
priority: p1
severidad: p2 (flaky: EADDRINUSE y cross-talk entre corridas)

## Hallazgo (repro verificado hoy)
- `tests/test_drill_rung4_live.py`: 7 puertos FIJOS (8231, 8232, 8233, 8235,
  8236, 8237 y 8238 vía STUB_PORT+k). `tests/test_rung4_hardening.py`: 7 más
  (8241–8247). Si CUALQUIER otro proceso ocupa uno (llama-server real, un drill
  en vivo, u OTRO worker del loop corriendo pytest a la vez — el loop tiene 3),
  el `ThreadingHTTPServer` no puede enlazar ⇒ excepción ⇒ falso rojo no
  determinista.
- Ambos ficheros comparten además directorios fijos bajo `.sdd/pytest-tmp/`
  (patrón rmtree+mkdir entre tests): dos corridas pytest concurrentes se
  pisan el sandbox/cache.

## Fix (la causa, no el síntoma)
- Stubs enlazados al puerto 0 (efímero del SO) y puerto REAL leído tras el
  bind (`server_address[1]`); `restart()` revincula al puerto ya conocido
  (requisito del drill: mismo puerto tras la recuperación). Cero puertos
  fijos en tests.
- `tmp_path` de pytest por test en vez del directorio compartido: aislamiento
  real entre tests y entre procesos.

## Coste/riesgo/beneficio
Ediciones en 2 ficheros de tests, cero src/. Beneficio: el suite deja de
depender de que nadie más use esos 14 puertos, y dos workers pueden correr
pytest a la vez sin pisarse.

## Criterio de aceptación
- Los dos ficheros en verde (2 pasadas seguidas).
- `grep -n "82[34][0-9]" tests/test_drill_rung4_live.py tests/test_rung4_hardening.py`
  vacío; ningún directorio compartido bajo `.sdd/pytest-tmp` creado por estos tests.
