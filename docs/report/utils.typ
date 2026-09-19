// Shared diagram helpers for the report. HackSpain card look & feel:
// sand-tinted panels, ink borders, Bungee labels + DM Sans body.
#import "lib.typ": *

/// Numbered pipeline card: `(num) NAME` + description + right-aligned artifact.
///
/// - num (content): Step number drawn in the ink circle
/// - name (content): Stage name, shown in the display font
/// - desc (content): One-line description
/// - artifact (content): Artifact produced, shown in mono
/// - fill-col (color): Panel background
/// -> content
#let stage-card(num, name, desc, artifact, fill-col) = box(
  fill: fill-col,
  stroke: 1.1pt + ink,
  inset: (x: 8pt, y: 6pt),
  radius: 2pt,
  width: 100%,
  grid(
    columns: (20pt, 1fr, auto),
    gutter: 7pt,
    align: (center + horizon, left + horizon, right + horizon),
    circle(radius: 8pt, fill: ink, text(font: display-font, size: 7pt, fill: paper, num)),
    [
      #text(font: display-font, size: 7pt, fill: ink, name) \
      #text(size: 7.5pt, fill: brown, desc)
    ],
    text(font: mono-font, size: 6.5pt, fill: teal, artifact),
  ),
)

/// Side-lane card (no step number): name + description + right-aligned artifact.
///
/// - name (content): Lane name, shown in the display font
/// - desc (content): One-line description
/// - artifact (content): Artifact produced, shown in mono
/// - fill-col (color): Panel background
/// -> content
#let lane-card(name, desc, artifact, fill-col) = box(
  fill: fill-col,
  stroke: 1.1pt + ink,
  inset: (x: 8pt, y: 6pt),
  radius: 2pt,
  width: 100%,
  grid(
    columns: (1fr, auto),
    gutter: 7pt,
    align: (left + horizon, right + horizon),
    [
      #text(font: display-font, size: 7pt, fill: ink, name) \
      #text(size: 7.5pt, fill: brown, desc)
    ],
    text(font: mono-font, size: 6.5pt, fill: teal, artifact),
  ),
)
