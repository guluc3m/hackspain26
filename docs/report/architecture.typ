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


== Bloque de extracción: La Escalera de Confianza Multiescalón

La extracción no es un modelo monolítico ni una caja negra: es una *escalera de degradación elegante y calibrada por página*, diseñada para maximizar el throughput, aniquilar costes innecesarios y resistir cualquier trampa adversarial de formato.

El principio rector es implacable: *hacer el trabajo más barato y rápido posible con garantías matemáticas de plausibilidad, escalando solo cuando la física del documento lo exige.*

```
PDF / Imagen 
  │
  ├── Rung 1: Texto nativo (pypdf + Plausibilidad) ────▶ [¿Texto útil?] ──(Sí)──▶ PARSER
  │                                                            │ (No)
  ├── Rung 2: Rasterizado + QR (pypdfium2 + zxing) ────▶ [¿Solo QR?]  ───(Sí)──▶ PARSER
  │                                                            │ (No)
  ├── Rung 3: Tesseract OCR (Doble puerta de cobertura) ──────▶ [¿Pasa?] ────(Sí)──▶ PARSER
  │                                                            │ (No)
  ├── Rung 4: VLM Local (PaddleOCR-VL Q8 + OpenCV) ────────────▶ [¿Pasa?] ────(Sí)──▶ PARSER
  │                                                            │ (No)
  ├── Rung 5: TypeSafe System One (Jev-latest) ───────────────▶ Evidencia Tipada (Paralela)
  │                                                            │
  ├── Rung 6: Firecrawl Document Parsing (/v2/parse) ─────────▶ Markdown Estructurado
  │                                                            │
  └── Rung 7: Cloud VLM (>25B Multimodal, OpenAI comp.) ───────▶ Candidato Final (Sin auto-stop)
```

Cada escalón rinde `ExtractionFeature` tipadas con identidad única `(page_sha256, rung_version, config_version)` que alimentan una caché de cero-red; un re-procesamiento 24/7 jamás re-factura una llamada externa.

=== La anatomía de los 7 escalones

1. *Rung 1 · Capa de texto nativa (`pypdf`)*: Inspecciona el stream vectorial. Para repeler trampas de _mojibake_ (fuentes CID corruptas que generan texto con alta confianza aparente), el texto se somete a un filtro de plausibilidad ortográfica y ratio alfanumérico. Si es legible, resuelve en $< 1$ ms a coste cero.
2. *Rung 2 · Rasterizado y QRs (`pypdfium2` + `zxing-cpp`)*: Si el texto nativo falla o no existe, la página se rasteriza a 300 DPI y se escanean códigos de barras/QR (VeriFactu / AT). Si la página es puramente un QR, su payload es el contenido de la página y la escalera concluye. Si coexiste con texto, el payload se preserva como feature y se continúa.
3. *Rung 3 · OCR Clásico (`Tesseract`)*: Primer filtro óptico con doble puerta: media ponderada de confianza de palabras ($>40\%$) y ratio de cobertura de campos clave ($>0.4$).
4. *Rung 4 · VLM Local (`PaddleOCR-VL 1.6 Q8` vía `llama-server`)*: Inteligencia visual on-premise ejecutada en GPU/CPU local sin fuga de datos. Para escaneos arrugados o de bajo contraste, un preprocesador dinámico OpenCV aplica estiramiento de histograma y máscara de desenfoque (_unsharp masking_). El servidor corre con *contexto completo de 131.072 tokens*, cuantización de KV-cache a `q8_0` y límite de 1.024 tokens a temperatura 0, resolviendo escaneos difíciles en $\sim 1.7$ s.
5. *Rung 5 · TypeSafe System One (`Jev`)*: Integración nativa de modelos System 1. Jev renuncia a la generación de texto no restringida a cambio de *decisiones estructuradas paralelas y calibradas*. Formula preguntas probabilísticas (`noul`, `choice`, `score`) sobre la calidad y naturaleza fiscal del documento en $\sim 560$ ms. Actúa como escalón de evidencia tipada no-parada (`auto_stop=False`).
6. *Rung 6 · Firecrawl Document Parsing (`/v2/parse`)*: Escalón de rescate documental que convierte páginas PDF o tablas en Markdown semántico limpio, preservando alineaciones complejas de importes.
7. *Rung 7 · Cloud VLM (>25B Multimodal compatible con OpenAI)*: Vía de contingencia para anomalías extremas. Su lectura se incorpora como un candidato más; nunca dicta una decisión automática.

=== Parser: Extractores Resilientes Multilingües

El _parser_ consume las features textuales y aplica un ejército de extractores deterministas inmunes a las trampas documentales observadas en el mundo real:
- *Normalización de caracteres invisibles*: Limpieza automática de espacios de ancho cero (`\u200b`, `\u200c`, `\ufeff`) que fracturan la detección de IBANs en entornos OCR.
- *Poliglotismo fiscal (7 idiomas)*: Extracción robusta de bases y totales en español (`TOTAL`), inglés (`Subtotal`), alemán (`Zwischensumme`, `GESAMT`), francés (`Sous-total`), italiano (`Imponibile`, `TOTALE`), portugués (`Valor base`) y catalán (`Base imposable`).
- *Divisas globales*: Desacoplamiento de importes y monedas (€, \$, £, Fr, ¥, R\$, MX\$) con análisis contextual de separadores de miles y decimales.
- *Fechas naturales complejas*: Parser cronológico capaz de interpretar tanto formatos numéricos como fechas redactadas en prosa en siete idiomas (*"the seventh of March, two thousand twenty-six"*, *"le trois janvier deux mille vingt-six"*, *"dos de gener de dos mil vint-i-sis"*).
- *Reensamblado vertical*: Reconstrucción sintáctica de textos impresos verticalmente con saltos de línea letra a letra (`P\na\np\ne\nl...`).
- *Desambiguación de rol fiscal*: Priorización del NIF del emisor sobre el CIF del cliente (`Banco Miralmar`) independientemente del orden relativo en la cabecera.

Todos los candidatos se conservan en `values[]` con su confianza y procedencia. El colapso a un valor escalar se pospone estrictamente al momento en que una regla de negocio lo evalúa, registrando la traza auditable en la base de datos.
Los campos dinámicos extraídos detallan emisor, receptor, fecha, pedido, proveedor, base, desglose de impuestos y total. Cada candidato almacena su extractor de procedencia y nivel de confianza en [0, 1].

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