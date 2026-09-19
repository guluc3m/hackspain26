# T29 · Fix del race health-check-bajo-carga (T24) + hardening para lote 2
assignee: W2
priority: p1

## Contexto (tu propio T24, ROJO documentado)
`except OSError: return True` trató HTTPError 503 como "servidor vivo" durante
la carga del modelo: los requests se cuelgan hasta el timeout 60 s porque
llama-server acepta conexiones mientras carga. En lote 2 (40 facturas
nuevas + regla v4) esto añadiría minutos de degradación innecesaria.

## Fix propuesto (el que documentaste en T24 — impleméntalo ya)
1. La sonda de health debe distinguir: conexión rechazada (servidor muerto ⇒
   skip rápido), 503/answer de /health no-OK (cargando ⇒ backoff con límite
   conocido, NO tratar como vivo), y timeout (colgado ⇒ backoff). Cada rama
   con su motivo en la evidencia.
2. El backoff de health respeta `Retry-After`/carga: máx N reintentos con cap
   configurable; después degradar a ESCALAR (nunca colgar el lote).
3. Cachear el "skip transitorio" solo si el skip fue DEFINITIVO (servidor
   muerto), nunca si fue "cargando" (un skip por carga no debe marcar la
   página como no-OCRizable para siempre).

## Criterios de aceptación
- Test con stub de llama-server en cada estado (muerto / cargando / colgado /
  sano): cada rama produce su skip/retry/backoff correcto y su evidencia.
- Test: "cargando" N veces seguidas ⇒ tras el límite, ESCALAR con motivo y el
  lote sigue; la página queda pendiente para re-proceso, no cacheada como
  fallida definitiva.
- pytest+ruff verde; ticket a closed en el mismo commit.
