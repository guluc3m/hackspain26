// Diagrama: Arquitectura general del sistema.
// Flujo de 5 fases (ingesta → extracción → parser → motor → entrega) más los
// carriles laterales de almacén y revisión humana.
#import "../lib.typ": *
#import "../utils.typ": lane-card, stage-card

/// Flecha vertical del pipeline con una leyenda.
///
/// - caption (content): Texto de la transición
/// -> content
#let pipe-arrow(caption) = align(center)[#v(-2pt)#text(
    font: display-font,
    size: 6.5pt,
    fill: brown,
  )[▼ #text(font: body-font, size: 6.5pt, style: "italic")[#caption]]#v(-2pt)]

/// Arquitectura general: pipeline de decisión + almacén + revisión humana.
/// -> content
#let arquitectura-general() = grid(
  columns: (1.5fr, 1fr),
  column-gutter: 12pt,
  align: (top + left, top + left),
  {
    stage-card(
      "1",
      "INGESTA",
      "PDFs del lote: sha256 → UUID interno; maestros y rules.yaml cargados al arranque",
      "sha256 · UUID",
      rgb("#e8f5e9"),
    )
    pipe-arrow[páginas → features]
    stage-card(
      "2",
      "EXTRACCIÓN",
      "Escalera multiescalón por página: features brutas, sin interpretar",
      "ExtractionFeature",
      rgb("#f1f8e9"),
    )
    pipe-arrow[features por página]
    stage-card(
      "3",
      "PARSER",
      "Normaliza e interpreta; conserva todos los candidatos con su confianza",
      "ExtractionField · values[]",
      rgb("#fffde7"),
    )
    pipe-arrow[campos + todos los candidatos]
    stage-card(
      "4",
      "MOTOR DE REGLAS",
      "PASS / FAIL / UNKNOWN por regla; determinista y puro; FAIL jamás resuelve PAGAR",
      "veredicto + snapshot",
      rgb("#e1f5fe"),
    )
    pipe-arrow[resultado + códigos de regla]
    stage-card(
      "5",
      "ENTREGA",
      "outcomes.jsonl por lote; file_id = nombre exacto del PDF",
      "PAGAR · NO_PAGAR · ESCALAR",
      rgb("#fdf1cd"),
    )
  },
  {
    v(7.5em)
    align(center)[#v(-2pt)#text(
        font: display-font,
        size: 6.5pt,
        fill: brown,
      )[◀ #text(font: body-font, size: 6.5pt, style: "italic")[evidencia de cada
          fase]]#v(-2pt)]
    v(2.5pt)
    lane-card(
      "ALMACÉN",
      "CosmosDB: Evidencias, decisiones, resultados. Datos históricos, configuraciones y datos maestros",
      "",
      rgb("#ede7f6"),
    )
    pipe-arrow[sirve candidatos e imágenes]
    lane-card(
      "Interfaz",
      "FastAPI + Svelte. Consulta de datos históricos y cola de ESCALAR para revisión humana",
      "",
      rgb("#fbe9e7"),
    )
  },
)
