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
