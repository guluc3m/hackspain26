// Diagrama: La Escalera de Confianza Multiescalón (7 escalones de extracción).
#import "../lib.typ": *

/// Tarjeta de un escalón: número, técnica, descripción y coste/latencia.
///
/// - num (content): Número del escalón
/// - tech (content): Técnica del escalón
/// - desc (content): Descripción del escalón
/// - cost (content): Coste por página
/// - speed (content): Latencia aproximada
/// - fill-col (color): Fondo de la tarjeta
/// -> content
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
    circle(radius: 8pt, fill: ink, text(
      font: display-font,
      size: 7pt,
      fill: paper,
      num,
    )),
    [
      #text(font: body-font, weight: 800, fill: ink, tech) \
      #text(size: 7.5pt, fill: brown, desc)
    ],
    [
      #text(font: display-font, size: 6.5pt, fill: teal, speed) \
      #text(font: display-font, size: 6.5pt, fill: orange, cost)
    ],
  ),
)

/// Conector vertical entre escalones.
#let flow-arrow = align(center)[#v(-2pt)#text(
    font: display-font,
    size: 6.5pt,
    fill: brown,
  )[▼ #text(font: body-font, size: 6.5pt, style: "italic")[degrada al siguiente
      escalón]]#v(-2pt)]

/// Escalera de confianza multiescalón: 7 escalones, del texto vectorial al
/// VLM en la nube.
/// -> content
#let escalera-confianza() = grid(
  columns: 1fr,
  gutter: 2.5pt,
  step-card(
    "1",
    [Texto Vectorial (pypdf + Plausibilidad)],
    [Filtro ortográfico y alfanumérico anti-mojibake CID],
    [0 €],
    [< 1 ms],
    fill-col: rgb("#e8f5e9"),
  ),
  flow-arrow,
  step-card(
    "2",
    [Rasterizado y QR (pypdfium2 + zxing)],
    [300 DPI. Si la página es solo QR, payload = contenido],
    [0 €],
    [~40 ms],
    fill-col: rgb("#f1f8e9"),
  ),
  flow-arrow,
  step-card(
    "3",
    [Tesseract OCR (Doble Puerta)],
    [Pasa solo con word-conf > 40% y cobertura campos > 0.4],
    [0 €],
    [~150 ms],
    fill-col: rgb("#fffde7"),
  ),
  flow-arrow,
  step-card(
    "4",
    [VLM Local (PaddleOCR-VL 1.6 Q8 + OpenCV)],
    [Contexto 131k, KV q8_0, unsharp masking en escaneos],
    [0 €],
    [~1.7 s],
    fill-col: rgb("#fff8e1"),
  ),
  flow-arrow,
  step-card(
    "5",
    [TypeSafe System One (Jev-latest)],
    [Decisiones tipadas y probabilidades paralelas (noul/choice/score)],
    [~0.04 \$ / Mtok],
    [~560 ms],
    fill-col: rgb("#e1f5fe"),
  ),
  flow-arrow,
  step-card(
    "6",
    [Firecrawl Document Parsing (\/v2\/parse)],
    [Rescate de tablas complejas y PDFs a Markdown estructurado],
    [1 credit],
    [~1.2 s],
    fill-col: rgb("#ede7f6"),
  ),
  flow-arrow,
  step-card(
    "7",
    [Cloud VLM (>25B Multimodal OpenAI comp.)],
    [Último recurso. Lectura como candidato extra (sin auto-stop)],
    [Pago token],
    [~3 s],
    fill-col: rgb("#fbe9e7"),
  ),
)
