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

## Resolución (W4, T39 — 2026-09-19): APROBADO e implementado
Bug de parsing puro que restaura la intención del propio código ("primera
fecha PLAUSIBLE"): no toca el motor ni la política. Hoy una factura con
"30/02/2026" delante perdía el campo fecha entero ⇒ DATE_VALID_NOT_FUTURE
UNKNOWN ⇒ ESCALAR por artefacto de parsing.

- `src/albertitos/parse/normalizers.py`: `parse_fecha` itera `finditer` y
  devuelve la primera fecha VÁLIDA (numérica y en meses); las inválidas no
  generan valor y si SOLO hay inválidas sigue devolviendo None (nunca inventa).
- Tests: `tests/test_parse.py::test_fecha_invalida_no_anula_las_siguientes_T38F4`
  (inválida→siguiente válida; solo inválidas→None; meses con inválida).
- Verificado: pytest verde, ruff limpio. Nota de reprocesado: solo cambia el
  resultado donde la 1ª fecha era inválida (hoy ESCALAR por artefacto);
  recomendado reprocesar subset con diff (mecanismo T13) tras lote 2.
- Validador de contrato 500/500 sobre el lote 1 tras el cambio en src/.
