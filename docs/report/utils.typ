// Shared diagram helpers for the report. HackSpain card look & feel:
// sand-tinted panels, ink borders, Bungee labels + DM Sans body.
#import "lib.typ": *

/// Numbered pipeline card: `(num) NAME` + description + right-aligned artifact.
///
/// All sizes are em-based so the same diagram scales with the ambient text
/// size (10.5pt in the report, 18pt in the slides).
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
  inset: (x: 0.762em, y: 0.571em),
  radius: 2pt,
  width: 100%,
  grid(
    columns: (1.905em, 1fr, auto),
    gutter: 0.667em,
    align: (center + horizon, left + horizon, right + horizon),
    circle(radius: 0.762em, fill: ink, text(font: display-font, size: 0.667em, fill: paper, num)),
    [
      #text(font: display-font, size: 0.667em, fill: ink, name) \
      #text(size: 0.714em, fill: brown, desc)
    ],
    text(font: mono-font, size: 0.619em, fill: teal, artifact),
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
  inset: (x: 0.762em, y: 0.571em),
  radius: 2pt,
  width: 100%,
  grid(
    columns: (1fr, auto),
    gutter: 0.667em,
    align: (left + horizon, right + horizon),
    [
      #text(font: display-font, size: 0.667em, fill: ink, name) \
      #text(size: 0.714em, fill: brown, desc)
    ],
    text(font: mono-font, size: 0.619em, fill: teal, artifact),
  ),
)
