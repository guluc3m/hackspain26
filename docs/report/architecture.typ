#import "lib.typ": *

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

La extracción no es una caja negra: es una *escalera de 7 escalones calibrada por página*, diseñada para resolver al mínimo coste y escalar con rigor matemático ante cualquier anomalía documental.

#let step-card(num, tech, desc, cost, speed, fill-col: sand) = box(
  fill: fill-col,
  stroke: 1.1pt + ink,
  inset: (x: 8pt, y: 6pt),
  radius: 2pt,
  width: 100%,
  grid(
    columns: (22pt, 1fr, auto),
    gutter: 8pt,
    align: (center + horizon, left + horizon, right + horizon),
    circle(radius: 8pt, fill: ink, text(font: display-font, size: 7pt, fill: paper, num)),
    [
      #text(font: body-font, weight: 800, fill: ink, tech) \
      #text(size: 7.5pt, fill: brown, desc)
    ],
    [
      #text(font: display-font, size: 6.5pt, fill: teal, speed) \
      #text(font: display-font, size: 6.5pt, fill: orange, cost)
    ]
  )
)
#let flow-arrow = align(center)[#v(-2pt)#text(font: display-font, size: 6.5pt, fill: brown)[▼ #text(font: body-font, size: 6.5pt, style: "italic")[degrada al siguiente escalón]]#v(-2pt)]

#v(2pt)
#grid(
  columns: (1fr),
  gutter: 2.5pt,
  step-card("1", [Texto Vectorial (pypdf + Plausibilidad)], [Filtro ortográfico y alfanumérico anti-mojibake CID], [0 €], [< 1 ms], fill-col: rgb("#e8f5e9")),
  flow-arrow,
  step-card("2", [Rasterizado y QR (pypdfium2 + zxing)], [300 DPI. Si la página es solo QR, payload = contenido], [0 €], [~40 ms], fill-col: rgb("#f1f8e9")),
  flow-arrow,
  step-card("3", [Tesseract OCR (Doble Puerta)], [Pasa solo con word-conf > 40% y cobertura campos > 0.4], [0 €], [~150 ms], fill-col: rgb("#fffde7")),
  flow-arrow,
  step-card("4", [VLM Local (PaddleOCR-VL 1.6 Q8 + OpenCV)], [Contexto 131k, KV q8_0, unsharp masking en escaneos], [0 €], [~1.7 s], fill-col: rgb("#fff8e1")),
  flow-arrow,
  step-card("5", [TypeSafe System One (Jev-latest)], [Decisiones tipadas y probabilidades paralelas (noul/choice/score)], [~0.04 \$ / Mtok], [~560 ms], fill-col: rgb("#e1f5fe")),
  flow-arrow,
  step-card("6", [Firecrawl Document Parsing (\/v2\/parse)], [Rescate de tablas complejas y PDFs a Markdown estructurado], [1 credit], [~1.2 s], fill-col: rgb("#ede7f6")),
  flow-arrow,
  step-card("7", [Cloud VLM (>25B Multimodal OpenAI comp.)], [Último recurso. Lectura como candidato extra (sin auto-stop)], [Pago token], [~3 s], fill-col: rgb("#fbe9e7")),
)
#v(4pt)
#v(6pt)

=== Parser Resiliente Multilingüe

El _parser_ consume las _features_ y extrae candidatos preservando procedencia y confianza:
- *Inmune a trampas OCR*: Normaliza espacios invisibles (`\u200b`), separadores combinados (`1 426,40`, `1,135,20`) y acrónimos fusionados (`IVA21%27150`).
- *Políglota nativo*: Reconoce importes y reglas fiscales en 7 idiomas (español, inglés, francés, alemán, italiano, catalán y portugués).
- *Desambiguación emisor/cliente*: Prioriza siempre el NIF del proveedor real sobre el CIF del cliente (`Banco Miralmar`), evitando falsos positivos de fraude.
- *Valores múltiples*: Todos los candidatos coexisten en `values[]`. La resolución escalar se difiere a la regla que la consume, garantizando trazabilidad y auditoría forense.


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

La persistencia runtime usa únicamente PouchDB JS local (LevelDB): documentos
dinámicos para evidencia, caché, eventos y decisiones inmutables, con adjuntos
fragmentados. La app solicita standalone o servidor al iniciar la UI; el batch
permanece no interactivo. El servicio FastAPI aloja el intercambio entre bases
PouchDB y el escalador VLM sin servidor CouchDB. Los endpoints se configuran en
la UI y se guardan en documentos locales no replicados.


== Retroalimentación
Para los casos escalados, los resultados de la resolución también se guardan en
la base de datos, para poder usarlos en futuros entrenamientos.