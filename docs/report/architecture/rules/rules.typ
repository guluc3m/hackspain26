== Reglas y motor de decisión

La decisión final (PAGAR / NO_PAGAR / ESCALAR) la produce un motor que evalúa
una serie de reglas sobre los campos extraídos por el _parser_.

=== Reglas

Cada regla vive en código y tiene un _código estable_ asociado (p. ej.
`TOTALS_MUST_MATCH`), que es lo que aparece en los _logs_ y en la salida, nunca
cadenas de texto libres. Añadir una regla no debe requerir tocar el bloque de
extracción, y añadir un tipo de ficha no debe requerir tocar el motor.

Toda regla devuelve uno de tres veredictos, acompañado de un motivo legible y
de los valores de campo que ha consumido:

- `PASS`: la regla se cumple.
- `FAIL`: la regla se incumple de forma definitiva; ningún juicio humano puede
  cambiarlo.
- `UNKNOWN`: no hay evidencia suficiente para decidir (campo ausente, lectura
  poco fiable, datos no cruzables).

La distinción es la frontera entre `NO_PAGAR` y `ESCALAR`: un `FAIL` es un
negativo definitivo, mientras que un `UNKNOWN` es duda razonable. Ante duda
razonable, escalar antes que pagar; cualquier cambio en esta política es una
ADR.

=== Motor de decisión

El motor es _puro y determinista_: mismos campos + misma configuración + mismo
maestro ⇒ misma salida, byte a byte. No hace I/O, no consulta el reloj ni usa
azar; la marca temporal la sella el _store_ al recibir la decisión.

La agregación de veredictos es:

+ Si alguna regla devuelve `FAIL` ⇒ `NO_PAGAR`.
+ Si no, si alguna devuelve `UNKNOWN` (o no hay reglas que evaluar) ⇒ `ESCALAR`.
+ Si no (todas `PASS`) ⇒ `PAGAR`.

La salida del motor incluye, además del resultado:

- la lista completa de evaluaciones (código, veredicto, motivo, valores
  consumidos y candidato elegido para cada campo, con su extractor y
  confianza);
- un _snapshot_ de la configuración activa: versión del conjunto de reglas,
  _thresholds_, versiones de los extractores y hash del maestro. Así se puede
  auditar y reproducir cualquier decisión posteriormente.

=== Colapso de candidatos

Las reglas no consumen valores sueltos: consumen campos con _todos_ sus
candidatos. Cuando una regla necesita un escalar, se colapsa el campo siguiendo
el proceso de selección de @rules/escoger.typ; la elección queda registrada en
la evaluación (candidato elegido, extractor y por qué). Si el proceso no
produce ningún candidato fiable — campo ausente, todos rechazados por formato o
puntuación bajo el _threshold_ — la regla devuelve `UNKNOWN` y el motor escala.

=== Reglas vigentes

- `NIF_IN_MASTER`: el NIF del emisor está en el maestro de proveedores.
- `IBAN_MATCHES_MASTER`: el IBAN de la factura coincide con el del maestro para
  ese NIF.
- `ORDER_BELONGS_TO_SUPPLIER`: el pedido existe en el ERP, pertenece a ese
  proveedor y el importe de la factura cuadra con el del pedido.
- `ORDER_PENDING`: el estado del pedido en el ERP es `PENDIENTE`.
- `NO_DOUBLE_PAYMENT`: el pedido no tiene ningún pago previo.
- `IVA_CONSISTENT`: el IVA reportado coincide con `base × tipo / 100`.
- `TOTALS_MUST_MATCH`: el total coincide con `base + IVA` (tolerancia
  configurable, por defecto 0,01 EUR).
- `DATE_VALID_NOT_FUTURE`: la fecha es válida y no es futura.

Las comparaciones de importes usan una tolerancia fija (0,01 EUR) para
descartar falsos negativos por redondeo.

=== Configuración

Los _thresholds_ son configuración, no código: viven en un YAML versionado (su
hash forma parte del _snapshot_), con una entrada por código de regla:

```yaml
rule_set_version: v1
rules:
  enabled:
    - TOTALS_MUST_MATCH
    - NIF_IN_MASTER
    # ...
thresholds:
  TOTALS_MUST_MATCH:
    min_confidence: 0.7
  NIF_IN_MASTER:
    min_confidence: 0.7
```

Cada regla puede fijar la confianza mínima exigida a los campos que consume; si
el mejor candidato no la supera, la regla devuelve `UNKNOWN` en lugar de
interpretar basura. Deshabilitar reglas o ajustar umbrales no requiere tocar
código; endurecer o relajar la frontera `NO_PAGAR`/`ESCALAR` sí es un cambio de
política y requiere ADR.
