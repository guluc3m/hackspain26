= Arquitectura general del sistema

El sistema procesa facturas, y decide si se deben pagar, no pagar, o escalar.

El input son los PDFs, el output es un JSONL con formato:
```json
{ "file_id": "factura_123.pdf", "result": "PAGAR" }
```

Cada factura tendrá su _invoice id_, un UUID.

Para ello vamos a realizar un proceso en dos grandes fases: extraer la
información de la factura y, mediante un motor de reglas, realizar la decisión.
Durante todo el proceso se irán almacenando los _logs_ y datos de cada paso,
para poder mantener la trazabilidad y, dado que en muchas legislaciones es
requerido, un histórico. La idea final es alimentar esa plataforma histórica.


== Bloque de extracción
Se puede subdividir en dos grandes bloques: extracción y _parser_. También se
puede reemplazar todo el bloque entero por un modelo, si es capaz de extraer los
campos con trazabilidad.

=== Extracción
La extracción debe, como su nombre indica, _extraer_ la información en crudo del
PDF, o _features_, ya sea texto o imágenes relevantes como QRs (en algunas
legislaciones, como la portuguesa, estas son obligatorias a la hora de emitir la
factura y contienen los datos de la misma codificados en un formato estándar).

Cada _feature_ tendrá un formato similar a:
```ts
interface ExtractionFeature {
  type: string;
  extraction_method: string;
  timestamp: number;
  data: string | bytes | object;
}
```

Los métodos de extracción pueden incluír extracción de QRs (imágenes),
extracción de texto/tablas directamente desde PDF, o OCR.


=== Parser
El parser tomará las _features_ y las analizará para extraer la información de
los campos requeridos.

La salida de este bloque es (por factura) un _record_ en formato JSON (o
similar) en el cual se detallen todos los campos de información de la factura.
Debido a que la legislación de cada país/administración es distinta, para ser
escalable, estos campos serán dinámicos, pero incluirán cosas como país,
concepto, fecha de factura, orden de pedido, proveedor, cantidad total,
impuestos (porcentajes y cantidades reportadas), y el desglose de los cargos.

Cada campo incluirá la información de la _feature_ desde la que se ha extraído,
incluyendo el método de análisis; ya sea un modelo de DL, un LLM, o un motor
Regex con heurísticas. Todos incluirán un intervalo de confianza (de 0 a 1).
Un valor también podra ser extraído con varios extractores, y todos los valores
se guardarán.

Cada campo tendrá un formato similar a:
```ts
interface ExtractionField {
  type: string,
  timestamp: number,
  values: {
    extractor: string,
    value: string | number | object,
    confidence: float,
  }[]
}
```


== Bloque de toma de decisiones
La toma de decisiones se realizará en base a una serie de reglas definidas en
código, cada una con un código asociado, y dependientes del país o
administración. Por ejemplo, la regla `TOTALS_MUST_MATCH` puede indicar que los
totales deben cuadrar los desgloses parciales. Cada regla puede tener
opcionalmente unos _thresholds_ de confianza configurables por cada tipo de
_field_ y cada extractor, para hacer más _finetuning_.

La salida incluirá las reglas usadas para rechazar/aceptar, así como la
configuración del momento.


== Logs
Los datos históricos de las facturas, así como los resultados, y toda la
información del proceso, se guardan en la base de datos, para luego poder
explotarse.


== Retroalimentación
Para los casos escalados, los resultados de la resolución también se guardan en
la base de datos, para poder usarlos en futuros entrenamientos.