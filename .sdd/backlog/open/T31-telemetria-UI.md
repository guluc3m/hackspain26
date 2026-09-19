
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
