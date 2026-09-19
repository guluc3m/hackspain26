# T38-F4 · parse_fecha: la 1ª fecha inválida anula el campo entero
assignee: W1
priority: p2
severidad: p2

## Hallazgo
`parse_fecha` (normalizers.py) hace `search` de la primera fecha y si es
inválida (30/02/2026) devuelve None aunque el texto contenga fechas válidas
después. El extractor de fechas devuelve entonces SIN candidatos ⇒
DATE_VALID_NOT_FUTURE UNKNOWN ⇒ ESCALAR por un artefacto de parsing.

## Reproducción (verificado hoy)
```
parse_fecha("30/02/2026, factura 05/03/2026") -> None  (esperado: 2026-03-05)
```
## Propuesta
Iterar `finditer` y devolver la primera fecha VÁLIDA; las inválidas pueden
quedar como candidatos de baja confianza si se quiere señal de ambigüedad.
~6 líneas.
