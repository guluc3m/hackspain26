#import "diagram/colapso-candidatos.typ": colapso-candidatos

== Motor de reglas y decisión

El motor consume los campos que entrega el _parser_ (incluyendo todos sus
candidatos) y, junto con los datos maestros y la configuración de la BBDD,
produce la decisión: `PAGAR`, `NO_PAGAR` o `ESCALAR`. Es *determinista*: los
mismos campos, con la misma configuración y datos, producen la misma salida.

=== Reglas

Cada regla vive en código y tiene un ID asociado. Añadir una regla no toca el
bloque de extracción, y añadir un tipo de ficha no toca el motor.

Toda regla devuelve uno de tres veredictos, acompañado de un motivo legible y de
los valores de campo que ha consumido:
- `PASS`: la regla se cumple.
- `FAIL`: la regla se incumple.
- `UNKNOWN`: no hay evidencia suficiente para decidir (campo ausente, lectura
  poco fiable, cruce no posible contra el maestro).

Las reglas definidas, extraídas del Excel `FINAL_v7_DEFINITIVO_ahorasi.xlsx`,
son:
#figure(
  table(
    columns: (auto, 1fr),
    table.header([Código], [Qué comprueba]),
    [`NIF_IN_MASTER`], [El NIF del emisor está en el maestro de proveedores.],
    [`IBAN_MATCHES_MASTER`],
    [El IBAN de la factura coincide con el del maestro para ese NIF.],

    [`ORDER_BELONGS_TO_SUPPLIER`],
    [El pedido existe en el ERP, pertenece a ese proveedor y el importe de la
      factura cuadra con el suyo.],

    [`ORDER_PENDING`], [El estado del pedido en el ERP es `PENDIENTE`.],
    [`NO_DOUBLE_PAYMENT`], [El pedido no tiene ningún pago previo.],
    [`IVA_CONSISTENT`], [El IVA reportado coincide con `base × tipo / 100`.],
    [`TOTALS_MUST_MATCH`], [El total coincide con `base + IVA`.],
    [`DATE_VALID_NOT_FUTURE`], [La fecha es válida y no es futura.],
  ),
  caption: [Reglas vigentes],
)

Las comparaciones de importes usan una tolerancia fija (0,01 EUR) para descartar
falsos negativos por redondeo.

=== Veredictos

La frontera entre `NO_PAGAR` y `ESCALAR` es configuración, no código: un
`UNKNOWN` es siempre duda razonable (escala), mientras que un `FAIL` resuelve al
resultado configurado para esa regla: `NO_PAGAR` (negativo definitivo, valor por
defecto) o `ESCALAR` (un humano debe revisarlo). Una regla rota nunca puede
resolver `PAGAR`. Ante duda razonable, escalar antes que pagar.

Se tienen en cuenta los valores devueltos por las distintas reglas, y se sigue
el siguiente algoritmo para realizar el veredicto:
+ Si hay algún `FAIL`, se comprueban las reglas que ha roto, y se aplica el
  _outcome_ más restrictivo, dependiendo de la configuración
  (`NO_PAGAR`/`ESCALAR`).
+ Si alguna regla devuelve `UNKNOWN`, o no hay reglas que evaluar: `ESCALAR`.
+ Si no (todas `PASS`): `PAGAR`.


La salida del motor incluye, además del resultado:
- la lista completa de evaluaciones: código, veredicto, motivo, valores
  consumidos y candidato elegido para cada campo (con su extractor y confianza);
- un _snapshot_ de la configuración activa: versión del conjunto de reglas,
  _thresholds_, versiones de los extractores y hash del maestro. Cualquier
  decisión se puede auditar y reproducir después.

=== Colapso de candidatos

Las reglas no consumen valores sueltos: consumen campos con todos sus
candidatos. Cuando una regla necesita un escalar, el campo se colapsa:

+ `trim()` de los valores de texto.
+ Tests de formato con ID estable (`NIF_FORMAT`, `IBAN_FORMAT`,
  `AMOUNT_POSITIVE`, ...), seleccionables por campo desde la configuración:
  quien no los supera se rechaza por razón de formato.
+ A cada candidato se le asigna una puntuación, computada como la confianza por
  el peso del extractor. Cada campo tiene un _threshold_ de puntuación que hay
  que superar para continuar.
+ Gana la puntuación máxima. En caso de empate, sólo si los valores no son
  iguales, se desempata por un ranking de extractores configurable por campo.

El proceso queda auditado candidato a candidato: cuál se eligió y por qué, y qué
pasó con el resto (rechazado por formato, bajo el umbral, desfavorecido en el
desempate). La elección se registra en la evaluación de la regla. Si no
sobrevive ningún candidato (campo ausente, todos rechazados por formato o por
debajo del umbral), la regla devuelve `UNKNOWN` y el motor escala.

#figure(colapso-candidatos(), caption: [Arquitectura general])



=== Configuración y maestros

Los _thresholds_ y la selección de candidatos viven en la base de datos y pueden
ser cargados a través de un YAML versionado cuyo hash forma parte del
_snapshot_, con una entrada por código de regla:

// ```yaml
// rule_set_version: v1
// rules:
//   enabled:
//     - TOTALS_MUST_MATCH
//     - NIF_IN_MASTER
//     # ...
// thresholds:
//   TOTALS_MUST_MATCH:
//     min_confidence: 0.7
// outcomes:
//   default: NO_PAGAR
//   on_fail:
//     NIF_IN_MASTER: ESCALAR
// seleccion:
//   default_score_threshold: 0.3
//   default_extractor_weights:
//     pypdf: 1.0
//     tesseract: 0.9
//   fields:
//     nif:
//       format_tests: [NIF_FORMAT]
// ```

Cada regla fija la confianza mínima exigida a los campos que consume; si el
mejor candidato no la supera, la regla devuelve `UNKNOWN` en lugar de
interpretar basura. Deshabilitar reglas o ajustar umbrales no requiere tocar
código.

Los datos maestros (`proveedores.csv`, `pedidos.csv`) se cargan al arrancar y se
almacenan en la base de datos. Consisten en:
- Listado de proveedores: NIF con su IBAN
- Pedidos del ERP con proveedor, importe, estado y pago. Su `sha256` queda
  sellado en cada decisión, de modo que se sabe qué maestro estaba activo al
decidir; el cruce contra el ERP se hace a través de una interfaz intercambiable,
sin acoplar el motor a ningún ERP concreto.
