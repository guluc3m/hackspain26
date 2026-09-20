// 500 Sombras de Alberto — defensa (10 min) · guluc3m
// Compilar:  typst compile --root .. --font-path ../report/fonts slides.typ
// Los diagramas son los mismos del informe (docs/report/diagram/): tamaños en
// em, así que escalan con el texto de la diapositiva (envolver en text(size:)).
// Guion: 01 demo y contexto · 02 arquitectura y ADRs ·
//        03 trazabilidad, escala y coste · 04 resiliencia y preguntas

#import "theme.typ": *
#import "../report/diagram/arquitectura-general.typ": arquitectura-general
#import "../report/diagram/escalera-confianza.typ": escalera-confianza
#import "../report/diagram/colapso-candidatos.typ": colapso-candidatos

// Destino del enlace de la demo (imagen clicable de la primera diapositiva).
#let demo-url = "https://hackathon.maisa.ai/"

#show: hs-theme.with(aspect-ratio: "16-9")

/* ── PORTADA ─────────────────────────────────────────────── */

#hs-title-slide[
  #text(size: .58em, style: "italic", fill: brown)[Reto · #challenge]
  #v(.4em)
  #text(font: display-font, size: 1.9em, fill: ink)[ALBERTITOS]
  #v(.25em)
  #line(length: 30%, stroke: 4.5pt + gold)
  #v(.4em)
  #text(size: .85em, weight: 500, fill: brown)[Del PDF a la decisión, con evidencia]
  #v(.6em)
  #chip([FACTURA], fill: gold) #h(.4em) #arrow-right #h(.4em)
  #chip([DECISIÓN], fill: gold) #h(.4em) #arrow-right #h(.4em)
  #chip([TRAZA], fill: gold)
  #v(.7em)
  #text(font: display-font, size: .68em, fill: ink)[Grupo de Usuarios de Linux · #text("uc3m", rgb(0x00, 0x07, 0x79))]
  #v(.3em)
  #text(size: .56em, fill: brown)[Luis Daniel Casais · Albert Giurgiu · Jorge Saghin · Henry Díaz]
]

/* ═══ 01 · DEMO Y CONTEXTO ═════════════════════════════════ */

= 01 · Demo y contexto

==

#align(center)[
  #link(demo-url)[
    #image("img/demo.jpg", height: 18em)
  ]
]


/* ═══ 02 · ARQUITECTURA Y ADRs ═════════════════════════════ */

= 02 · Arquitectura y ADRs

== Arquitectura general

#text(size: .54em)[#arquitectura-general()]

#v(.4em)
#text(size: .68em, fill: brown)[Se pueden añadir reglas sin modificar la extracción, y un tipo de archivo sin tocar el motor. Además, cada peldaño se puede omitir y la caché es por página.]

== Pasos para la extracción

#text(size: .72em)[#escalera-confianza()]

== Features crudas, campos con candidatos

#grid(
  columns: (1fr, 1fr),
  gutter: .8em,
  align: top,
  card([EXTRACCIÓN · FEATURES], [
    - texto, imagen, QR, tabla
    - material crudo, sin interpretar
    - motor + versión + latencia + hash
  ], accent: slate),
  card([PARSER · FIELDS], [
    - NIF, IBAN, total, IVA, fecha, pedido
    - *todos* los candidatos en `values[]`
    - cada uno con extractor y confianza `[0,1]`
  ], accent: teal),
)

#v(.6em)
#text(size: .82em)[Un campo *nunca* se colapsa en el store. El escalar se elige solo en la regla que lo consume, y queda registrado *cuál* y *por qué*:]

#v(.4em)
#text(size: .78em)[#colapso-candidatos()]

#v(.45em)
#text(size: .74em, fill: brown)[Parser multilingüe (7 idiomas) · inmune a trampas OCR · prioriza el NIF del proveedor sobre el CIF del cliente.]

== El motor: puro, determinista, configurable

#grid(
  columns: (1.05fr, 1fr),
  gutter: (.9em, 0pt),
  align: bottom,
  [
    Reglas en código, con _thresholds_ configurables
    #v(-.35em)
    #codepanel(size: .5em)[
      NIF\_IN\_MASTER · IBAN\_MATCHES\_MASTER \
      ORDER\_BELONGS\_TO\_SUPPLIER · ORDER\_PENDING \
      NO\_DOUBLE\_PAYMENT · IVA\_CONSISTENT \
      TOTALS\_MUST\_MATCH · DATE\_VALID\_NOT\_FUTURE
    ]
    #v(.45em)
    #text(size: .85em)[
      - `FAIL` ⇒ outcome *más restrictivo* (`NO_PAGAR` / `ESCALAR`, dependiente de la regla).
      - `UNKNOWN` (o sin reglas) ⇒ *ESCALAR*: duda razonable.
      - Todas `PASS` ⇒ *PAGAR*
    ]
  ],
  [
    #text(size: .8em, weight: 800)[Salida: *evaluación + snapshot*]
    #v(-.1em)
    ```json
    {
      "result": "ESCALAR",
      "rule_verdicts": [
        {"rule": "TOTALS_MUST_MATCH", "verdict": "PASS", "values": {...}},
        {"rule": "NIF_IN_MASTER", "verdict": "UNKNOWN", "reason": "sin candidato"}
      ],
      "snapshot": {"rule_set": "v1", "thresholds": {...},
                   "extractors": {...}, "master_sha256": "9f2c…"}
    }
    ```
    #v(.35em)
    #text(size: .68em, fill: brown)[Umbrales, reglas habilitadas y: *configuración versionada*. El maestro se sella por *sha256*; el ERP, por interfaz intercambiable.]
  ],
)

#v(.35em)
#align(center)[#text(weight: 800, size: .85em)[Mismos campos + misma config ⇒ misma decisión.]]

== Cuatro ADRs (1/2) · motor y extracción

#grid(
  columns: (1fr, 1fr),
  gutter: (.7em, .42em),
  align: top,
  card([ADR-01 · Motor de reglas determinista], [
    Reglas en código, *puras y deterministas*; umbrales y política como configuración versionada, con *snapshot* en cada decisión.
    Añadir una regla no toca la extracción; cambiar la política exige ADR.
  ], accent: gold),
  card([ADR-02 · Extracción en dos bloques], [
    *Features* tipadas + parser que produce campos con *valores múltiples* (extractor y confianza).
    Umbrales del peldaño 3 calibrados con el corpus: el *94,2 %* resuelve por texto.
  ], accent: gold),
)

#v(.45em)
#text(size: .72em, fill: brown)[Cada ADR lleva contexto, alternativas, decisión, consecuencias y *evidencia medida*. Detalle en `albertitos_plan.pdf`.]

== Cuatro ADRs (2/2) · pipeline y almacén

#grid(
  columns: (1fr, 1fr),
  gutter: (.7em, .42em),
  align: top,
  card([ADR-03 · Pipeline desacoplada], [
    Colas entre extracción, parser y decisión: cada bloque escala y falla por separado.
    El ERP, solo por *costura de adaptador*; reanudación *sin duplicados*.
  ], accent: gold),
  card([ADR-04 · Almacén PouchDB + CouchDB], [
    PouchDB embebido como única persistencia, con adjuntos fragmentados y *replicación nativa* a CouchDB.
    Sin *joins* ni transacciones: consistencia por IDs deterministas y conflictos *fail-closed*.
  ], accent: gold),
)

#v(.45em)
#text(size: .72em, fill: brown)[El histórico y los candidatos viven en el almacén; la regla v4 del lote 2 llega como *datos*, sin tocar el motor.]

/* ═══ 03 · TRAZABILIDAD, ESCALA Y COSTE ════════════════════ */

= 03 · Trazabilidad, escala y coste
El estado vive en disco; los números, medidos

==

- Cada factura tiene un *UUID*; `file_id` es el nombre exacto del PDF.
- *PouchDB local (LevelDB)*: decisiones inmutables, candidatos sin colapsar, adjuntos fragmentados. En servidor, réplica nativa *PouchDB ↔ CouchDB*; la config local no se replica.
- *Idempotente y resumible*: clave `(sha256, etapa, engine_version, config_version)`; re-procesar es un no-op.

#v(.3em)
#text(weight: 800)[Cada etapa escribe una fila de evidencia:]

#v(.35em)
#codepanel[
  invoice\_id · stage · extractor · extractor\_version · config\_version \
  sha256 · latency\_ms · confidence · outcome · detail
]

#v(.5em)
#text(size: .78em)[La cola de revisión guarda la corrección humana como *override con provenance* (quién, cuándo, antes/después); afecta solo a la extracción y el motor recalcula. Es el corpus de reentrenamiento.]

== Escala: hagamos las cuentas

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: (.8em, .9em),
  kpi([500], [PDFs del lote 1], color: ink),
  kpi([4,16], [archivos/s end-to-end], color: teal),
  kpi([2,3 s], [latencia media / factura], color: teal),
)

#v(.7em)
#grid(
  columns: (1fr, 1fr),
  gutter: (.9em, .45em),
  align: top,
  card([EL LOTE ENTERO], [
    `500 ÷ 4,16 ≈ 120 s` → *≈ 2 min* por lote.
    Peldaño 1 medido a *2 636 archivos/s*.
  ], accent: teal),
  card([DÓNDE SE VA EL TIEMPO], [
    `471 / 500 = 94,2 %` resuelve por texto.
    Solo `29 = 5,8 %` baja a raster / OCR / VLM.
  ], accent: gold),
)

#v(.6em)
#text(size: .78em)[UI + 2 runners en paralelo: peor *p95 7,7 ms*, ~*109 archivos/s por runner*, 0 incidencias. Hardware medido: *4 núcleos · 8q GB*.]

== Coste: hagamos las cuentas

#codepanel[
  coste\_lote = CPU\_local + llamadas\_cloud + tokens\_agentes \
  CPU local = 0,0000 € (medido) · llamadas cloud = 0,0000 € (medido)
]

#v(.6em)
#grid(
  columns: (1fr, 1fr),
  gutter: (.9em, .45em),
  align: top,
  card([LO QUE CUESTA], [
    Rung 5 TypeSafe: `0,04 $ / Mtok`.
    Rung 6 Firecrawl: `1 crédito`.
    Rung 7: pago por token.
  ], accent: orange),
  card([LO QUE SE PAGA], [
    `471` páginas resuelven *gratis* por texto.
    Solo las que caen a la nube pagan, y quedan *cacheadas por página*.
  ], accent: teal),
)

#v(.6em)
#text(size: .8em)[En el lote medido cayó *1 página* a la nube ⇒ coste marginal ≈ *0 €*. Estimación de cola: `5 000 tok × 0,04 $/Mtok ≈ 0,0002 $/página`; 500 páginas difíciles ≈ *0,10 \$*, y con caché re-ejecutar es gratis.]

== Lote 1, auditado

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: .8em,
  kpi([433], [PAGAR], color: teal),
  kpi([22], [NO\_PAGAR], color: red),
  kpi([45], [ESCALAR], color: orange),
)

#v(.7em)
#card([LA AUDITORÍA ENCONTRÓ LA TRAMPA], [
  El motor colapsaba `total` al *primer* candidato — «Subtotal» en vez de «TOTAL A PAGAR»:
  *87 NO\_PAGAR eran falsos*. ADR-02: ahora las reglas evalúan *todos* los candidatos con provenance.
  Reprocesado: `347 + 86 = 433` PAGAR y `108 − 86 = 22` NO\_PAGAR, *0 regresiones*. *86,6 %* PAGAR automático.
], accent: orange)

/* ═══ 04 · RESILIENCIA Y PREGUNTAS ════════════════════════ */

= 04 · Resiliencia y preguntas
Degrada, no se detiene

== Resiliencia probada

#grid(
  columns: (1fr, 1fr),
  gutter: (.7em, .5em),
  align: top,
  card([PROVEEDOR CAÍDO], [3 intentos → revisión; el lote sigue. *PASS*], accent: teal),
  card([BACKOFF 429], [`Retry-After` respetado; 0 llamadas extra. *PASS*], accent: teal),
  card([CRASH + REANUDACIÓN], [Reanudación completa; *0 duplicados*. *PASS*], accent: teal),
  card([LEDGER CORRUPTO], [El histórico sobrevive; recuperable. *PASS*], accent: teal),
)

#v(.6em)
#text(size: .8em)[4 / 4 drills medidos en PASS. Un peldaño que falta no para el lote: `skipped:<razón>` y el veredicto honesto es *ESCALAR*.]

#v(.45em)
#text(size: .74em, fill: brown)[Medido en la corrida: 22 reintentos, 3 omisiones y *0 errores de proveedor*.]

== Futuro: lo que viene

#grid(
  columns: (1fr, 1fr),
  gutter: (.7em, .45em),
  align: top,
  card([LOTE 2 · REGLA v4], [Cargada como *datos* en `rules.yaml`; el motor no cambia.], accent: gold),
  card([CORPUS DE ESCALADOS], [Los casos revisados alimentan reentrenamiento y umbrales.], accent: gold),
  card([ERP REAL], [Conectar el ERP por la costura de adaptador, sin tocar reglas ni extracción.], accent: gold),
  card([MÁS ADMINISTRACIONES], [El parser ya cubre 7 idiomas; añadir reglas fiscales por país.], accent: gold),
)

#v(.6em)
#text(size: .74em, fill: brown)[Y el panel de *salud y coste*: coste por página, proveedor y peldaño, visible mientras el lote corre.]

/* ── CIERRE ──────────────────────────────────────────────── */

#hs-focus-slide(footer-text: "github.com/guluc3m/hackspain26")[
  #text(font: display-font, size: 1.5em)[¿Preguntas?]
]
