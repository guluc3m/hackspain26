
## NOTA (supervisor): stats del VLM explícitas
La telemetría debe incluir las stats del VLM (rung 4 llama-server y rung 5
cloud) como ciudadano de primera: por página — latencia, tokens de entrada
(píxeles de imagen aprox.) y de salida, cache hit/miss por
(page_sha256, engine, config_version), tasa de truncado, y en rung 5 las
llamadas facturables vs cacheadas con su coste. El llama-server expone /metrics
(Prometheus) y /props: sonda y agrega en la pantalla Operaciones (Uptime de
componentes + cola rung 4). Sin estos números la defensa de escala/coste (25
pts) no cierra para el lote 2.

## NOTA 2 (supervisor): stats comparables por tramo de la escalera
La telemetría debe mantener stats POR RUNG como serie temporal comparable (no
solo agregados del último lote): por rung — nº ejecuciones, p50/p95 de
latencia, ratio de descarte, coste acumulado — en ventanas (última corrida,
última hora, histórico). La UI Operaciones gana una vista "Escalera": las 4-5
barras de rungs lado a lado con sus p50/p95 y % de páginas que cada uno
consumió, para comparar tiempos entre tramos de un vistazo (y ver la deriva
tras cambios). Fuente: las filas de evidencia (stage/latencia) que ya existen.

## Cerrado — decisiones tomadas (W3)

- **`albertitos.telemetria`** (aditivo, motor intacto) con las dos NOTAS del
  supervisor implementadas:
  1. **Stats VLM de primera**: rung 4 (llama-server) y rung 5 (cloud) con
     invocaciones emitidas, latencia media/máx, cache hit/miss (hit LITERAL
     "cache hit" — un "cache miss" es un miss), tasa de truncado (medida si
     la evidencia la registra; 0.0 % es una medición, None solo si no hay
     invocaciones), tokens (cuando la evidencia los registra) y coste rung 5
     facturable = facturables × precio (fórmula T9 intacta); páginas en
     caché (page_sha256 × engine × config_version) contadas del cache real.
  2. **Vista Escalera** en Operaciones: tabla por tramo con n/p50/p95,
     % de filas consumidas, ratio de descarte, errores y coste — en dos
     ventanas: **corrida actual** (config_version de la ÚLTIMA fila del
     ledger append-only) e **histórico**; «última hora» solo si las filas
     llevan timestamp (si no ⇒ «sin datos», jamás serie falseada).
  3. **Sonda llama-server** (/health, /props, /metrics Prometheus) con caché
     de 60 s para no saturar el sidecar: estado, modelo, cola rung 4 y
     contadores Prometheus en Operaciones.
  4. **Cadena encadenada con hash** (`EventChain`): log append-only donde
     cada evento sella el hash del anterior; pantalla **Actividad** nueva en
     la UI con verificación en vivo (recalcula la cadena y delata
     manipulación — testeado); los overrides de Revisión y anotaciones de
     Alberto quedan sellados. Telemetría de la UI bajo
     `.sdd/telemetria/`, jamás dentro del store.
- **Demo en vivo**: Operaciones con Escalera + Stats VLM + Sonda (up),
  Actividad íntegra con anotaciones selladas. CLI: `python -m albertitos.telemetria`.
- **Tests** (10): p50/p95/pct exactos, ventanas (corrida/hora/histórico con
  y sin timestamps), coste con fórmula T9, VLM cache/truncado/sin-datos,
  sonda down ⇒ sin datos, cadena íntegra y anti-manipulación, UI.
- Nota: `test_drill_rung4_live` (T24, W1) vuelve a ser flaky bajo carga de
  suite (verde en solitario) — ya documentado para W1.
- Suite: 261 passed (1 flaky ajeno intermitente), ruff limpio, sin secretos.
