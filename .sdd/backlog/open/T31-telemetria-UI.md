
## NOTA (supervisor): stats del VLM explícitas
La telemetría debe incluir las stats del VLM (rung 4 llama-server y rung 5
cloud) como ciudadano de primera: por página — latencia, tokens de entrada
(píxeles de imagen aprox.) y de salida, cache hit/miss por
(page_sha256, engine, config_version), tasa de truncado, y en rung 5 las
llamadas facturables vs cacheadas con su coste. El llama-server expone /metrics
(Prometheus) y /props: sonda y agrega en la pantalla Operaciones (Uptime de
componentes + cola rung 4). Sin estos números la defensa de escala/coste (25
pts) no cierra para el lote 2.
