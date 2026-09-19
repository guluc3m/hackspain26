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

/// Team mark, ink on sand.
#let team-mark(size: 0.5em) = box(
  fill: ink,
  inset: (x: 0.45em, y: 0.12em),
  text(font: display-font, size: size, fill: paper, tracking: 0.08em, upper(team)),
)

/// Coloured square used as a bullet / accent.
#let tick(color: gold) = box(width: 0.42em, height: 0.42em, fill: color, baseline: 8%)

/// Big metric: value in Bungee, label underneath.
#let kpi(value, label, color: ink, size: 1.55em) = block(breakable: false, {
  text(font: display-font, size: size, fill: color, value)
  linebreak()
  text(size: 0.5em, weight: 700, fill: brown, tracking: 0.04em, upper(label))
})

/// Bordered panel with a Bungee title.
#let card(title, body, accent: gold, fill: paper) = block(
  width: 100%,
  breakable: false,
  stroke: 1.1pt + ink,
  fill: fill,
  {
    block(
      width: 100%,
      fill: ink,
      inset: (x: 0.6em, y: 0.34em),
      grid(
        columns: (1fr, auto),
        align: (left + horizon, right + horizon),
        text(font: display-font, size: 0.62em, fill: paper, title),
        box(width: 0.34em, height: 0.34em, fill: accent),
      ),
    )
    block(inset: (x: 0.7em, y: 0.55em), width: 100%, text(size: 0.78em, body))
  },
)

/// Numbered step of a flow, compact.
#let step(num, title, detail, fill: sand) = box(
  width: 100%,
  fill: fill,
  stroke: 0.9pt + ink,
  inset: (x: 0.5em, y: 0.32em),
  grid(
    columns: (0.95em, 1fr),
    gutter: 0.4em,
    align: (center + horizon, left + horizon),
    circle(radius: 0.42em, fill: ink, text(font: display-font, size: 0.5em, fill: paper, str(num))),
    [ #text(font: display-font, size: 0.58em, fill: ink, title) #h(0.5em) #text(size: 0.62em, fill: brown, detail) ],
  ),
)

#let arrow-down = align(center, text(font: display-font, size: 0.6em, fill: brown)[▾])

#let arrow-right = box(outset: (x: 0.05em), text(font: display-font, size: 0.7em, fill: orange)[→])

/// Bullet list with coloured squares instead of dots.
#let points(..items) = list(
  marker: tick(color: orange),
  indent: 1.15em,
  spacing: 0.62em,
  ..items,
)

/* SLIDE CHROME */

#let header(self) = {
  let section = utils.display-current-heading(level: 1)
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
  )
  v(0.22em)
  line(length: 100%, stroke: 1.2pt + ink)
}

#let footer(self) = {
  v(0.05em)
  line(length: 100%, stroke: 0.9pt + hairline)
  v(0.3em)
  context {
    grid(
      columns: (1fr, auto),
      gutter: 0.5em,
      align: (left + bottom, right + bottom),
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
        inset: (x: 0.5em, y: 0.16em),
        text(
          font: display-font,
          size: 0.5em,
          fill: ink,
          context counter(page).display("1 / 1", both: true),
        ),
      ),
    )
  }
}

/// Default slide: HackSpain chrome on paper.
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
        alpha: 8%,
        format: "svg",
        height: 88%,
      ))
      box(width: 100%, height: 100%, stroke: 2.4pt + ink, inset: 0.4em, {
        box(width: 100%, height: 100%, stroke: 0.9pt + ink, inset: 1.1em, {
          grid(
            columns: (auto, 1fr, auto),
            align: (left + top, center + top, right + top),
            chip([MAISA · HACKSPAIN 2026], fill: ink, text-fill: paper),
            [],
            chip([ETSIT UPM · MADRID], fill: sand),
          )
          v(1.9fr)
          body
          v(2.1fr)
        })
      })
    })),
  )
})

/// Section divider: ink panel, gold number.
#let hs-section-slide(body) = touying-slide-wrapper(self => {
  touying-slide(
    self: self,
    config: utils.merge-dicts(
      config-page(header: none, footer: none, fill: ink),
      config-common(freeze-slide-counter: true),
    ),
    align(center + horizon, block(width: 100%, {
      text(font: display-font, size: 0.75em, fill: gold, tracking: 0.12em, upper(utils.display-current-heading(level: 1)))
      v(0.4em)
      line(length: 26%, stroke: 3.5pt + gold)
      v(0.4em)
      text(size: 0.95em, fill: paper, body)
    })),
  )
})

/// Quote / big statement on ink (typst-intro style focus slide).
#let hs-focus-slide(body, footer-text: none) = touying-slide-wrapper(self => {
  touying-slide(
    self: self,
    config: utils.merge-dicts(
      config-page(header: none, footer: none, fill: ink),
      config-common(freeze-slide-counter: true),
    ),
    align(center + horizon, block(width: 88%, {
      set text(fill: paper, size: 1.35em)
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
    below: 0.9em,
    text(font: display-font, size: 0.95em, fill: brown, utils.display-current-heading(level: 2)),
  ),
  ..args,
  body,
) = {
  show: touying-slides.with(
    config-page(
      paper: "presentation-" + aspect-ratio,
      fill: paper,
      margin: (x: 1.7em, top: 1.5em, bottom: 1.6em),
      footer-descent: 0em,
    ),
    config-common(
      slide-fn: hs-slide,
      new-section-slide-fn: hs-section-slide,
      reset-page-counter-to-slide-counter: false,
    ),
    config-methods(
      init: (self: none, body) => {
        set text(font: body-font, size: 18pt, fill: ink, lang: "es")
        set par(leading: 0.62em)
        show heading.where(level: 1): set text(font: display-font, size: 1.35em, fill: ink)
        show heading.where(level: 2): set text(font: display-font, size: 1.0em, fill: brown)
        show heading: set block(above: 0.3em, below: 0.45em)
        show list: set list(indent: 1.15em, spacing: 0.62em, marker: tick(color: orange))
        show enum: set enum(indent: 1.15em, spacing: 0.62em)
        show link: set text(fill: teal)
        show quote: set block(stroke: (left: 3pt + gold), inset: (left: 0.8em, y: 0.3em))
        show quote: set text(style: "italic", fill: brown)
        show raw.where(block: true): it => block(
          width: 100%,
          breakable: false,
          fill: sand,
          stroke: 0.8pt + ink,
          inset: 0.7em,
          text(font: mono-font, size: 0.62em, fill: ink, it),
        )
        show raw.where(block: false): it => box(
          fill: sand,
          outset: (x: 0.18em, y: 0.12em),
          text(font: mono-font, size: 0.8em, fill: ink, it),
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
