// HackSpain 2026 · "500 Sombras de Alberto" — slide theme.
// Touying look & feel inspired by https://github.com/rajayonin/typst-intro,
// palette, fonts and sharp panels from the official HackSpain brand kit.

#import "@preview/touying:0.6.1": *
#import "@preview/grayness:0.4.1": image-transparency

/* BRAND */

#let paper = rgb("#f4ecd8") // hs-paper
#let ink = rgb("#2a170f") // hs-ink
#let brown = rgb("#4a2c1f") // hs-brown
#let gold = rgb("#eab619") // hs-gold
#let orange = rgb("#d96b2a") // hs-orange
#let red = rgb("#cc291f") // hs-red
#let teal = rgb("#35858a") // hs-teal
#let slate = rgb("#8fb8d1") // hs-slate
#let sand = rgb("#e8dcc4") // muted paper
#let hairline = rgb("#d8c9a8") // subtle rule

#let display-font = "Bungee"
#let body-font = "DM Sans 9pt"
#let mono-font = "DejaVu Sans Mono"

#let challenge = "500 Sombras de Alberto"
#let team = "guluc3m"

/* ATOMS */

/// Small bordered label, HackSpain style (sharp corners, Bungee).
#let chip(body, fill: sand, text-fill: ink, size: 0.5em, stroke: 0.9pt + ink) = box(
  fill: fill,
  stroke: stroke,
  radius: 0pt,
  inset: (x: 0.45em, y: 0.14em),
  text(font: display-font, size: size, fill: text-fill, tracking: 0.06em, body),
)

/// "HACKSPAIN 26" wordmark drawn with the display font.
#let wordmark(size: 0.55em, year: true) = box(
  text(font: display-font, size: size, fill: ink)[HACK]
    + text(font: display-font, size: size, fill: gold)[SPAIN]
    + if year { text(font: display-font, size: size * 0.9, fill: brown, [\u{2009}26]) },
)

/// Coloured square used as a bullet / accent.
#let tick(color: gold) = box(width: 0.42em, height: 0.42em, fill: color, baseline: 8%)

/// Big metric: value in Bungee, label underneath.
#let kpi(value, label, color: ink, size: 1.5em) = block(breakable: false, {
  text(font: display-font, size: size, fill: color, value)
  linebreak()
  text(size: 0.48em, weight: 700, fill: brown, tracking: 0.04em, upper(label))
})

/// Bordered panel with a Bungee title and tight body.
#let card(title, body, accent: gold, fill: paper) = block(
  width: 100%,
  breakable: false,
  above: 0pt,
  below: 0pt,
  stroke: 1.1pt + ink,
  fill: fill,
  {
    set align(left + top)
    block(
      width: 100%,
      fill: ink,
      inset: (x: 0.55em, y: 0.3em),
      above: 0pt,
      below: 0pt,
      grid(
        columns: (1fr, auto),
        align: (left + horizon, right + horizon),
        text(font: display-font, size: 0.6em, fill: paper, title),
        box(width: 0.32em, height: 0.32em, fill: accent),
      ),
    )
    block(
      inset: (x: 0.65em, y: 0.42em),
      width: 100%,
      above: 0pt,
      below: 0pt,
      text(size: 0.76em, body),
    )
  },
)

/// Monospaced panel used for evidence rows and config.
#let codepanel(body, size: 0.56em) = block(
  width: 100%,
  breakable: false,
  fill: sand,
  stroke: 0.8pt + ink,
  inset: (x: 0.7em, y: 0.5em),
  {
    set smartquote(enabled: false)
    text(font: mono-font, size: size, fill: ink, body)
  },
)

/// Numbered step of the extraction ladder.
#let step(num, title, detail, fill: sand) = box(
  width: 100%,
  fill: fill,
  stroke: 0.9pt + ink,
  inset: (x: 0.5em, y: 0.3em),
  height: 2.5em,
  align(left + horizon, grid(
    columns: (1.1em, 1fr),
    gutter: 0.45em,
    align: (center + horizon, left + horizon),
    circle(radius: 0.42em, fill: ink, text(font: display-font, size: 0.48em, fill: paper, str(num))),
    [
      #text(font: display-font, size: 0.55em, fill: ink, title)
      #h(0.4em)
      #text(size: 0.58em, fill: brown, detail)
    ],
  )),
)

/// Flow box with a fixed height so all boxes in a row align.
#let fbox(title, sub: none, fill: sand, tfill: ink) = box(
  fill: fill,
  stroke: 0.9pt + ink,
  width: 100%,
  height: 2.5em,
  inset: (x: 0.45em, y: 0.25em),
  align(center + horizon, {
    text(font: display-font, size: 0.5em, fill: tfill, title)
    if sub != none {
      linebreak()
      text(size: 0.44em, fill: if tfill == ink { brown } else { sand }, sub)
    }
  }),
)

#let arrow-right = box(outset: (x: 0.02em), text(font: display-font, size: 0.62em, fill: orange)[→])

/// Extraction-ladder rung, adapted from `docs/report/architecture.typ` (`step-card`):
/// number, technique, short description, and the speed/cost of the rung.
#let rung(num, tech, desc, cost, speed, fill: sand) = box(
  width: 100%,
  fill: fill,
  stroke: 1pt + ink,
  inset: (x: 0.5em, y: 0.26em),
  height: 1.7em,
  align(left + horizon, grid(
    columns: (1.5em, 1fr, auto),
    gutter: 0.5em,
    align: (center + horizon, left + horizon, right + horizon),
    circle(
      radius: 0.5em,
      fill: ink,
      text(font: display-font, size: 0.52em, fill: paper, str(num)),
    ),
    [
      #text(font: body-font, size: 0.6em, weight: 800, fill: ink, tech) \
      #text(size: 0.5em, fill: brown, desc)
    ],
    [
      #text(font: display-font, size: 0.44em, fill: teal, speed) \
      #text(font: display-font, size: 0.44em, fill: orange, cost)
    ],
  )),
)

/// "Falls through to the next rung" marker for the ladder.
#let rung-arrow = align(center, box(height: 0.32em, text(font: display-font, size: 0.46em, fill: brown)[▼]))

/* SLIDE CHROME */

#let header(self) = {
  let section = utils.display-current-heading(level: 1)
  grid(
    rows: (auto, auto),
    row-gutter: 0.26em,
    grid(
      columns: (auto, 1fr, auto),
      gutter: 0.5em,
      align: (left + bottom, horizon, right + bottom),
      if section != none and section != [] {
        box(
          fill: gold,
          inset: (x: 0.45em, y: 0.12em),
          text(font: display-font, size: 0.52em, fill: ink, tracking: 0.05em, upper(section)),
        )
      } else { [] },
      [],
      wordmark(size: 0.55em),
    ),
    line(length: 100%, stroke: 1.2pt + ink),
  )
}

#let footer(self) = {
  grid(
    rows: (auto, auto),
    row-gutter: 0.3em,
    line(length: 100%, stroke: 0.9pt + hairline),
    grid(
      columns: (1fr, auto),
      gutter: 0.5em,
      align: (left + horizon, right + horizon),
      text(
        size: 0.46em,
        weight: 700,
        fill: brown,
        tracking: 0.08em,
        upper(challenge + " · " + team),
      ),
      box(
        fill: gold,
        stroke: 0.9pt + ink,
        inset: (x: 0.5em, y: 0.14em),
        text(
          font: display-font,
          size: 0.5em,
          fill: ink,
          context counter(page).display("1 / 1", both: true),
        ),
      ),
    ),
  )
}

/// Default slide: HackSpain chrome on paper, content vertically balanced.
#let hs-slide(
  config: (:),
  repeat: auto,
  setting: body => body,
  composer: auto,
  ..bodies,
) = touying-slide-wrapper(self => {
  let self = utils.merge-dicts(
    self,
    config-page(header: header, footer: footer),
    config-common(subslide-preamble: self.store.subslide-preamble),
  )
  touying-slide(self: self, config: config, repeat: repeat, setting: setting, composer: composer, ..bodies)
})

/// Title slide: double ink frame, faded logo, gold rule.
#let hs-title-slide(body) = touying-slide-wrapper(self => {
  touying-slide(
    self: self,
    config: utils.merge-dicts(
      config-page(header: none, footer: none, fill: paper),
      config-common(freeze-slide-counter: true),
    ),
    align(center + horizon, block(width: 100%, height: 100%, {
      place(center, image-transparency(
        read("img/gul-logo.svg", encoding: none),
        alpha: 11%,
        format: "svg",
        height: 76%,
      ))
      box(width: 100%, height: 100%, stroke: 2.4pt + ink, inset: 0.4em, {
        box(width: 100%, height: 100%, stroke: 0.9pt + ink, inset: 1em, {
          grid(
            columns: (auto, 1fr, auto),
            align: (left + top, center + top, right + top),
            chip([MAISA · HACKSPAIN 2026], fill: ink, text-fill: paper),
            [],
            chip([ETSIT UPM · MADRID], fill: sand),
          )
          v(1.7fr)
          body
          v(1.9fr)
        })
      })
    })),
  )
})

/// Section divider: ink panel, gold label and rule.
#let hs-section-slide(body) = touying-slide-wrapper(self => {
  touying-slide(
    self: self,
    config: utils.merge-dicts(
      config-page(header: none, footer: none, fill: ink),
      config-common(freeze-slide-counter: true),
    ),
    align(center + horizon, block(width: 100%, {
      text(font: display-font, size: 1.05em, fill: gold, tracking: 0.1em, upper(utils.display-current-heading(level: 1)))
      v(0.45em)
      line(length: 24%, stroke: 4pt + gold)
      v(0.45em)
      text(size: 0.95em, fill: paper, body)
    })),
  )
})

/// Quote / big statement on ink.
#let hs-focus-slide(body, footer-text: none) = touying-slide-wrapper(self => {
  touying-slide(
    self: self,
    config: utils.merge-dicts(
      config-page(header: none, footer: none, fill: ink),
      config-common(freeze-slide-counter: true),
    ),
    align(center + horizon, block(width: 88%, {
      set text(fill: paper, size: 1.3em)
      body
      if footer-text != none {
        v(0.7em)
        text(font: display-font, size: 0.5em, fill: gold, tracking: 0.08em, upper(footer-text))
      }
    })),
  )
})

/* THEME */

#let hs-theme(
  aspect-ratio: "16-9",
  primary: gold,
  subslide-preamble: block(
    below: 0.6em,
    text(font: display-font, size: 0.92em, fill: brown, utils.display-current-heading(level: 2)),
  ),
  ..args,
  body,
) = {
  show: touying-slides.with(
    config-page(
      paper: "presentation-" + aspect-ratio,
      fill: paper,
      margin: (x: 1.6em, top: 2.3em, bottom: 2.45em),
      header-ascent: 0.5em,
      footer-descent: 0.55em,
    ),
    config-common(
      slide-fn: hs-slide,
      new-section-slide-fn: hs-section-slide,
      reset-page-counter-to-slide-counter: false,
      zero-margin-header: false,
      zero-margin-footer: false,
    ),
    config-methods(
      init: (self: none, body) => {
        set text(font: body-font, size: 20pt, fill: ink, lang: "es")
        set par(leading: 0.62em)
        set align(horizon)
        show heading.where(level: 1): set text(font: display-font, size: 1.35em, fill: ink)
        show heading.where(level: 2): set text(font: display-font, size: 1.0em, fill: brown)
        show heading: set block(above: 0.3em, below: 0.45em)
        show list: set list(indent: 1.0em, spacing: 0.6em, marker: tick(color: orange))
        show enum: set enum(indent: 1.0em, spacing: 0.6em)
        show link: set text(fill: teal)
        show quote: set block(stroke: (left: 3pt + gold), inset: (left: 0.8em, y: 0.3em))
        show quote: set text(style: "italic", fill: brown)
        show raw.where(block: true): it => block(
          width: 100%,
          breakable: false,
          fill: sand,
          stroke: 0.8pt + ink,
          inset: (x: 0.7em, y: 0.55em),
          text(font: mono-font, size: 0.56em, fill: ink, it.text),
        )
        show raw.where(block: false): it => box(
          fill: sand,
          outset: (x: 0.14em, y: 0.1em),
          text(font: mono-font, size: 0.8em, fill: ink, it.text),
        )
        body
      },
      alert: utils.alert-with-primary-color,
    ),
    config-colors(
      neutral-light: brown,
      neutral-lightest: paper,
      neutral-darkest: ink,
      primary: primary,
    ),
    config-store(subslide-preamble: subslide-preamble),
    ..args,
  )

  body
}
