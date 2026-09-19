// Diagrama: Colapso de candidatos.
// Cómo un campo con `values[]` se reduce a un escalar elegido (o a UNKNOWN).
// Tamaños en em: escala con el texto ambiente (10.5pt informe, 18pt diapositivas).
#import "../lib.typ": *

/// Tarjeta de una etapa del colapso (número, técnica y descripción centrados).
///
/// - num (content): Número de la etapa
/// - tech (content): Técnica de la etapa
/// - desc (content): Descripción de la etapa
/// - fill-col (color): Fondo de la tarjeta
/// -> content
#let colapso-card(num, tech, desc, fill-col: sand) = box(
  fill: fill-col,
  stroke: 1.1pt + ink,
  inset: (x: 0.381em, y: 0.476em),
  radius: 2pt,
  width: 100%,
  {
    align(center, circle(radius: 0.667em, fill: ink, text(
      font: display-font,
      size: 0.619em,
      fill: paper,
      num,
    )))
    v(0.286em)
    align(center, text(
      font: body-font,
      size: 0.762em,
      weight: 800,
      fill: ink,
      tech,
    ))
    v(0.238em)
    align(center, text(size: 0.581em, fill: brown, desc))
  },
)

/// Caja de entrada al colapso: los candidatos tal cual llegan del parser.
/// No es una etapa, es el material de partida.
///
/// - tech (content): Campo de entrada (p. ej. `values[]`)
/// - desc (content): Contenido del campo
/// -> content
#let colapso-input(tech, desc) = box(
  fill: ink,
  stroke: 1.1pt + ink,
  inset: (x: 0.381em, y: 0.476em),
  radius: 2pt,
  width: 100%,
  {
    align(center, text(
      font: display-font,
      size: 0.619em,
      fill: gold,
      tracking: 0.09em,
      [INPUT],
    ))
    v(0.286em)
    align(center, text(
      font: body-font,
      size: 0.762em,
      weight: 800,
      fill: paper,
      tech,
    ))
    v(0.238em)
    align(center, text(size: 0.581em, fill: sand, desc))
  },
)

/// Conector horizontal entre etapas del colapso.
#let colapso-arrow = align(center + horizon, text(
  font: display-font,
  size: 0.81em,
  fill: orange,
)[→])

/// Colapso de candidatos: de `values[]` al escalar, con traza completa.
/// -> content
#let colapso-candidatos() = grid(
  columns: (1fr, auto, 1fr, auto, 1fr, auto, 1fr, auto, 1fr),
  gutter: 0.286em,
  align: horizon,
  colapso-input([candidatos], [(extractor, confianza)]),
  colapso-arrow,
  colapso-card("1", [trim()], [Saneado de texto], fill-col: rgb("#e8f5e9")),
  colapso-arrow,
  colapso-card(
    "2",
    [FORMATO],
    [#text(fill: red)[✗ descarta los que no cumplen]],
    fill-col: rgb("#fffde7"),
  ),
  colapso-arrow,
  colapso-card(
    "3",
    [SCORE],
    [confianza × peso, umbral por campo],
    fill-col: rgb("#fff8e1"),
  ),
  colapso-arrow,
  colapso-card("4", [MÁXIMO], [empate → ranking], fill-col: rgb("#e1f5fe")),
)
