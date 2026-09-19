// HackSpain 2026 report template.
// Look & feel based on https://hackspain.app/ (Maisa × HackSpain · 2026):
// paper background, ink panels, gold accents, Bungee display + DM Sans body.

#let paper = rgb("#f4ecd8") // hs-paper
#let ink = rgb("#2a170f") // hs-ink
#let brown = rgb("#4a2c1f") // hs-brown
#let gold = rgb("#eab619") // hs-gold (primary)
#let orange = rgb("#d96b2a") // hs-orange
#let red = rgb("#cc291f") // hs-red
#let slate = rgb("#8fb8d1") // hs-slate
#let teal = rgb("#35858a") // hs-teal (secondary)
#let sand = rgb("#e8dcc4") // muted paper

#let display-font = "Bungee"
#let body-font = "DM Sans 9pt"
#let mono-font = ("DejaVu Sans Mono", "Courier New")

#let MONTHS = (
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)

/// Small bordered label, HackSpain style (sharp corners, Bungee).
///
/// - body (content): Label text
/// - fill (color): Background color
/// - text-fill (color): Text color
/// -> content
#let chip(body, fill: sand, text-fill: ink, stroke: 0.9pt + ink) = box(
  fill: fill,
  stroke: stroke,
  radius: 0pt,
  inset: (x: 8pt, y: 4pt),
  outset: (y: 1.5pt),
  text(font: display-font, size: 7.5pt, fill: text-fill, tracking: 0.07em, body),
)

/// "HACKSPAIN" wordmark drawn with the display font.
///
/// - size (length): Base font size
/// - year (bool): Whether to append the `26` suffix
/// -> content
#let wordmark(size: 8pt, year: true) = {
  text(font: display-font, size: size, fill: ink)[HACK]
  text(font: display-font, size: size, fill: gold)[SPAIN]
  if year {
    text(font: display-font, size: size * 0.9, fill: brown)[\u{2009}26]
  }
}

/// An Architecture Decision Record panel (ADR), as required by the
/// albertitos_plan.pdf deliverable. Every extra named argument becomes a
/// labeled row, e.g. `contexto: [...]`, `alternativas: [...]`.
///
/// - title (content): Decision title
/// -> content
#let adr(title, ..fields) = {
  counter("adr").step()
  context {
    let n = counter("adr").get().first()
    block(
      width: 100%,
      breakable: true,
      above: 1.6em,
      below: 1.6em,
      stroke: 1.4pt + ink,
      {
        block(
          width: 100%,
          fill: ink,
          inset: (x: 11pt, y: 8pt),
          text(font: display-font, size: 9.5pt, fill: paper, {
            text(fill: gold)[ADR #if n < 10 { "0" + str(n) } else { str(n) }]
            h(9pt)
            title
          }),
        )
        block(width: 100%, inset: (x: 11pt, y: 11pt), {
          for (name, body) in fields.named() {
            grid(
              columns: (84pt, 1fr),
              gutter: 12pt,
              align: (left, left),
              text(
                font: display-font,
                size: 7pt,
                fill: brown,
                tracking: 0.09em,
                upper(name.replace("_", " ")),
              ),
              text(size: 9.8pt, body),
            )
            v(8pt)
          }
        })
      },
    )
  }
}

/// The cover page.
#let _cover(event, challenge, title, subtitle, chips, logo, team, teamId, repo, authors, place, date) = {
  set page(header: none, footer: none, margin: 26pt)
  set align(center)
  set par(justify: false)
  set text(font: body-font, fill: ink)

  block(width: 100%, height: 100%, stroke: 2.6pt + ink, inset: 6pt, {
    block(width: 100%, height: 100%, stroke: 0.8pt + ink, inset: 22pt, {
      grid(
        columns: (auto, 1fr, auto),
        gutter: 8pt,
        align: (left + top, center + top, right + top),
        chip(event, fill: ink, text-fill: paper),
        [],
        chip(place, fill: sand),
      )

      v(2.4fr)

      text(size: 11pt, style: "italic", fill: brown)[Reto · #challenge]
      v(0.9em)
      text(font: display-font, size: 30pt, fill: ink, title)
      v(0.9em)
      if subtitle != none {
        text(size: 12.5pt, weight: 500, fill: brown, subtitle)
      }

      v(1.1em)
      line(length: 38%, stroke: 4.5pt + gold)

      v(2.4fr)

      if chips.len() > 0 {
        for (i, c) in chips.enumerate() {
          chip(c, fill: gold)
          if i < chips.len() - 1 {
            h(9pt)
            text(fill: orange, weight: 900)[→]
            h(9pt)
          }
        }
        v(2.2fr)
      }

      if logo != none {
        image(logo, height: 2.1cm)
        v(0.9em)
      }

      if team != none {
        text(font: display-font, size: 13pt, fill: ink, team)
        v(0.8em)
      }

      if authors.len() > 0 {
        let entries = authors.map(a => if type(a) == "string" { (name: a) } else { a })
        for a in entries {
          text(size: 10.5pt, weight: 700, hyphenate: false, {
            if "email" in a {
              link("mailto:" + a.email, text(fill: ink, a.name))
            } else {
              a.name
            }
          })
          v(5.5pt, weak: true)
        }
        v(1.6fr)
      }

      if teamId != none {
        chip([TEAM ID · #teamId], fill: sand)
        v(0.9em)
      }

      if repo != none {
        v(0.6em)
        link(repo, chip(repo.replace("https://", ""), fill: sand, text-fill: teal))
        v(0.9em)
      }

      if date != none {
        text(font: display-font, size: 8.5pt, fill: brown, tracking: 0.05em, upper(date))
      }
    })
  })

  pagebreak()
  counter(page).update(1)
}

/// Main configuration function.
///
/// - event (content): Event label for the cover chip, e.g. `\[ MAISA · HACKSPAIN 2026 \]`
/// - challenge (str): Challenge name, e.g. `"500 Sombras de Alberto"`
/// - title (content): Report title, e.g. `[ALBERTITOS PLAN]`
/// - subtitle (content, none): Report subtitle
/// - place (content): Place label for the cover chip
/// - date (content, none): Date shown at the bottom of the cover
/// - chips (array): Row of tag chips shown mid-cover, e.g. `([FACTURA], [DECISIÓN], [TRAZA])`
/// - logo (str, none): Path to the team logo shown on the cover
/// - team (content, none): Team name
/// - teamId (str, none): HackSpain teamId
/// - repo (str, none): Team repository URL, shown as a linked chip
/// - authors (array): Team members, either strings or `(name: str, email: str)`
/// - toc (bool): Whether to include the table of contents
/// - doc (content): Document contents
/// -> content
#let conf(
  event: [MAISA · HACKSPAIN 2026],
  challenge: "500 Sombras de Alberto",
  title: [ALBERTITOS PLAN],
  subtitle: none,
  place: [ETSIT UPM · MADRID],
  date: [Entrega · dom 20 sep 2026 · 11:00],
  chips: (),
  logo: none,
  team: none,
  teamId: none,
  repo: none,
  authors: (),
  toc: true,
  doc,
) = {
  set document(
    title: "albertitos_plan · " + challenge,
    author: authors.map(a => if type(a) == "string" { a } else { a.name }),
  )

  set text(font: body-font, size: 10.5pt, fill: ink, lang: "es", hyphenate: true)
  set par(leading: 0.68em, spacing: 1.05em, justify: true)
  set heading(numbering: "1.1")

  set page(
    paper: "a4",
    fill: paper,
    margin: (top: 2.5cm, bottom: 2.4cm, x: 2.1cm),
    header: context {
      let heads = query(heading.where(level: 1)).filter(h => h.numbering != none)
      let page = here().page()
      let visible = heads.filter(h => h.location().page() <= page)
      let section = if visible.len() > 0 { visible.last().body } else []
      grid(
        columns: (auto, 1fr, auto),
        gutter: 10pt,
        align: (bottom, horizon, bottom),
        wordmark(size: 8pt),
        text(size: 7.5pt, fill: brown, tracking: 0.14em, weight: 600, upper(challenge)),
        text(size: 8pt, fill: brown, tracking: 0.06em, weight: 700, upper(section)),
      )
      v(5pt)
      line(length: 100%, stroke: 1.5pt + ink)
    },
    footer: context {
      line(length: 100%, stroke: 1.5pt + ink)
      v(5pt)
      grid(
        columns: (1fr, auto),
        gutter: 10pt,
        align: (bottom, bottom),
        if team != none {
          text(size: 8.5pt, weight: 700, fill: brown, tracking: 0.05em, upper(team))
          text(size: 8pt, fill: brown, tracking: 0.06em, weight: 700, [ -- #upper(title)])
        },
        box(
          fill: gold,
          stroke: 1pt + ink,
          inset: (x: 7pt, y: 2.5pt),
          text(font: display-font, size: 7.5pt, fill: ink, counter(page).display("1 / 1", both: true)),
        ),
      )
    },
  )

  /* HEADINGS */

  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    block(width: 100%, breakable: false, above: 1.8em, below: 1.5em, {
      grid(
        columns: (auto, 1fr),
        gutter: 12pt,
        align: (center, left + horizon),
        if it.numbering != none {
          box(
            fill: gold,
            stroke: 1.3pt + ink,
            inset: (x: 10pt, y: 5.5pt),
            text(font: display-font, size: 11pt, fill: ink, counter(heading).display(it.numbering)),
          )
        },
        text(font: display-font, size: 15.5pt, fill: ink, it.body),
      )
      v(8pt)
      line(length: 100%, stroke: 2.2pt + ink)
      v(-4.2pt)
      line(length: 14%, stroke: 2.2pt + gold)
    })
  }

  show heading.where(level: 2): it => {
    block(breakable: false, above: 1.35em, below: 0.75em, {
      box(width: 0.32em, height: 0.78em, fill: gold, outset: (right: 6pt), baseline: 10%)
      text(font: body-font, size: 12.5pt, weight: 800, fill: brown, {
        if it.numbering != none {
          text(fill: teal, counter(heading).display(it.numbering))
          h(7pt)
        }
        it.body
      })
    })
  }

  show heading.where(level: 3): it => {
    text(size: 11pt, weight: 800, fill: ink, {
      if it.numbering != none {
        text(fill: orange, counter(heading).display(it.numbering))
        h(7pt)
      }
      it.body
    })
  }

  /* INLINE ELEMENTS */

  show link: set text(fill: teal)
  show ref: set text(fill: teal)

  show raw.where(block: false): it => box(fill: sand, outset: (y: 2pt), it)
  show raw.where(block: true): it => block(
    width: 100%,
    breakable: true,
    fill: sand,
    stroke: 0.9pt + ink,
    inset: 10pt,
    radius: 0pt,
    text(font: mono-font, size: 8.6pt, fill: ink, it),
  )
  show raw: set text(font: mono-font, size: 8.6pt, fill: ink)

  show figure.caption: it => {
    set text(size: 9.5pt, fill: brown)
    strong(it.supplement)
    h(0.35em)
    if it.numbering != none {
      context it.counter.display(it.numbering)
      h(0.35em)
    }
    it.body
  }
  show figure: set block(breakable: false, above: 1.2em, below: 1.2em)
  show figure.where(kind: table): set figure.caption(position: top)

  show table.cell.where(y: 0): set text(fill: paper, weight: 700, size: 9.5pt)
  set table(
    stroke: 1pt + ink,
    inset: (x: 8pt, y: 6pt),
    fill: (_, y) => if y == 0 { ink } else if calc.odd(y) { paper } else { sand },
  )

  set list(indent: 1em, marker: text(fill: orange, weight: 900)[▪])
  set enum(indent: 1em)
  show enum: set text(fill: ink)
  show quote: set block(stroke: (left: 3pt + gold), inset: (left: 11pt, y: 4pt))
  show quote: set text(style: "italic", fill: brown)

  /* COVER */

  _cover(event, challenge, title, subtitle, chips, logo, team, teamId, repo, authors, place, date)

  /* OUTLINE */

  if toc {
    outline(
      title: text(font: display-font, size: 17pt, fill: ink)[Índice],
      depth: 2,
    )
    pagebreak()
  }

  doc
}
