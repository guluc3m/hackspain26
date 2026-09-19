# T38-F3 · parse_amount: coma de miles anglosajona sin decimales ⇒ None
assignee: W1
priority: p2
severidad: p2

## Hallazgo
`parse_amount` (normalizers.py): en la rama `elif "," in s` con grupo final de
3 dígitos se asigna `miles = "."` — el carácter equivocado (no hay «.» en el
token) ⇒ `Decimal("1,234")` lanza InvalidOperation ⇒ None.

## Reproducción (verificado hoy)
```
parse_amount("12,345")  -> None   (esperado: 12345)
parse_amount("1,234")   -> None   (esperado: 1234)
```
Casos correctos en el mismo código: "1.234,56"→1234.56, "2.345"→2345,
"12.345.678"→12345678.

## Impacto
Una factura en formato anglosajón «1,234» pierde su candidato de importe ⇒
campos ausentes ⇒ UNKNOWN ⇒ ESCALAR (degradación, no falso PAGAR).

## Fix propuesto
En esa rama: `miles, dec = ",", ""` (mismo estilo que la rama de punto).
~2 líneas + test. Solo extracción, no cambia decisiones por sí solo.

## Resolución (W4, T39 — 2026-09-19): APROBADO e implementado
Bug de codificación inequívoco: en la rama `elif "," in s` (grupo final de 3
dígitos) se asignaba `miles="."` — carácter que NO existe en el token ⇒
`Decimal("1,234")` lanza InvalidOperation ⇒ None. La rama gemela de punto
("2.345"→2345) demuestra la intención: coma de miles, sin decimales.

- `src/albertitos/parse/normalizers.py`: `miles, dec = ",", ""` (+comentario).
- Tests: `tests/test_parse.py::test_importe_coma_miles_anglosajona_sin_decimales_T38F3`
  ("12,345"→12345, "1,234"→1234, sin regresión en 1.234,56 / 2.345 /
  12.345.678 / 12,34-coma-decimal).
- Actualizado el test de T38-F7 (`test_importe_como_texto_anglosajon`): el
  fallback de load_master ahora carga "1,234" como 1234.0 sin avisos, como
  documentaba.
- Impacto en decisiones: recupera el candidato de importe para facturas en
  formato anglosajón (antes UNKNOWN ⇒ ESCALAR). Solo extracción; el motor
  decide igual. Validador de contrato 500/500 sobre el lote 1 tras el cambio.
