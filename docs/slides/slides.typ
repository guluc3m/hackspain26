// 500 Sombras de Alberto — defensa (10 min) · guluc3m
// Compilar:  typst compile --font-path ../docs/report/fonts slides.typ
// Guion: 01 demo y contexto · 02 arquitectura y ADRs ·
//        03 trazabilidad, escala y coste · 04 resiliencia y preguntas

#import "theme.typ": *

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
Se enseña en vivo; aquí, el marco

== El reto de Alberto

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: .7em,
  align: top,
  card([ENTRADA], [500 PDFs: nativos y escaneados], accent: teal),
  card([MAESTRO], [proveedores, pedidos y normas], accent: slate),
  card([SISTEMA], [ERP legado de 2009], accent: orange),
)

#v(.9em)
#text(size: .84em)[Leer cada factura y decidir si se puede pagar — con *evidencia en cada paso* y sin que el lote se detenga jamás.]

#v(.7em)
#quote[Ante duda razonable, escalar antes que pagar.]

== Tres resultados, una doctrina

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: .8em,
  align: top,
  card([PAGAR], [Todas las reglas PASS. Trazable.], accent: teal),
  card([NO\_PAGAR], [Negativo definitivo: nadie lo revierte.], accent: red),
  card([ESCALAR], [Duda razonable o evidencia incompleta: decide una persona.], accent: gold),
)

#v(.8em)
#text(size: .82em)[La frontera NO\_PAGAR / ESCALAR no está cableada: es *configuración versionada* (`outcomes.on_fail`), y cada decisión guarda el resultado resuelto por regla.]

#v(.5em)
#text(size: .74em, fill: brown)[Una regla *nunca* puede resolver PAGAR; el motor rechaza esa config al cargarla.]

== Demo en vivo

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: .7em,
  align: top,
  card([LOTE], [500 PDFs → `outcomes.jsonl` en ~2 min], accent: teal),
  card([REVISIÓN], [candidatos lado a lado, desacuerdo resaltado], accent: gold),
  card([TRAZA], [una fila de evidencia por etapa], accent: slate),
)

#v(.9em)
#align(center)[#chip([EN VIVO · iniciar.sh], fill: gold, size: .8em)]

#v(.6em)
#align(center)[#text(size: .8em, fill: brown)[Un solo paso: levanta la UI, carga el maestro y reanuda donde se quedó.]]

/* ═══ 02 · ARQUITECTURA Y ADRs ═════════════════════════════ */

= 02 · Arquitectura y ADRs
Dos fases, decisiones trazables

== Arquitectura general

#grid(
  columns: (1fr, auto, 1fr, auto, 1fr, auto, 1fr, auto, 1fr),
  align: horizon,
  fbox([PDF], sub: [input]),
  arrow-right,
  fbox([EXTRACCIÓN], sub: [features crudas], fill: slate),
  arrow-right,
  fbox([PARSER], sub: [campos + candidatos], fill: slate),
  arrow-right,
  fbox([MOTOR], sub: [reglas puras], fill: gold),
  arrow-right,
  fbox([RESULTADO], sub: [JSONL], fill: teal, tfill: paper),
)

#v(.6em)
#align(center)[#text(font: body-font, size: .68em, fill: brown)[#sym.arrow.b  evidencia + snapshot de configuración  #sym.arrow.b]]

#v(.6em)
#grid(
  columns: (1fr, auto, 1.25fr, auto, 1fr),
  align: horizon,
  fbox([EVIDENCIA + SNAPSHOT], sub: [cada etapa], fill: sand),
  arrow-right,
  fbox([STORE], sub: [PouchDB local · réplica CouchDB], fill: ink, tfill: paper),
  arrow-right,
  fbox([UI], sub: [operación y revisión], fill: sand),
)

#v(.7em)
#text(size: .74em, fill: brown)[Añadir una regla no toca la extracción; añadir un tipo de archivo no toca el motor. Cada peldaño es *omisible* (`skipped:<razón>`) y la caché es por página.]

== La escalera de extracción · 7 peldaños, por página

#grid(
  columns: (1fr, 1fr),
  gutter: (.9em, 0pt),
  [
    #align(left)[#chip([LOCAL · 0 €], fill: sand)]
    #v(.35em)
    #rung(1, [Texto vectorial], [pypdf · filtro anti-mojibake], [0 €], [< 1 ms], fill: rgb("#e8f5e9"))
    #rung-arrow
    #rung(2, [Raster + QR], [pypdfium2 + zxing · 300 DPI], [0 €], [~40 ms], fill: rgb("#f1f8e9"))
    #rung-arrow
    #rung(3, [Tesseract OCR], [doble puerta: conf + cobertura], [0 €], [~150 ms], fill: rgb("#fffde7"))
    #rung-arrow
    #rung(4, [VLM local], [PaddleOCR-VL Q8 · temp 0], [0 €], [~1,7 s], fill: rgb("#fff8e1"))
  ],
  [
    #align(right)[#chip([NUBE · ESCALADA], fill: slate)]
    #v(.35em)
    #rung(5, [TypeSafe System One], [decisiones tipadas (jev-latest)], [0,04 \$/Mtok], [~560 ms], fill: rgb("#e1f5fe"))
    #rung-arrow
    #rung(6, [Firecrawl Parse], [tablas complejas → Markdown], [1 crédito], [~1,2 s], fill: rgb("#ede7f6"))
    #rung-arrow
    #rung(7, [Cloud VLM >25B], [último recurso · candidato], [pago/token], [~3 s], fill: rgb("#fbe9e7"))
  ],
)

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
#text(size: .82em)[Un campo *nunca* se colapsa en el store. El escalar se elige solo en la regla que lo consume, y queda registrado *cuál* y *por qué*.]

#v(.45em)
#text(size: .74em, fill: brown)[Parser multilingüe (7 idiomas) · inmune a trampas OCR · prioriza el NIF del proveedor sobre el CIF del cliente.]

== El motor: puro, determinista, configurable

#grid(
  columns: (1.05fr, 1fr),
  gutter: .9em,
  align: top,
  [
    #text(weight: 800)[8 reglas en código, *código estable*:]
    #v(.35em)
    #codepanel[
      TOTALS\_MUST\_MATCH · NIF\_IN\_MASTER · IVA\_CONSISTENT \
      ORDER\_PENDING · ORDER\_BELONGS\_TO\_SUPPLIER · NO\_DOUBLE\_PAYMENT \
      IBAN\_MATCHES\_MASTER · DATE\_VALID\_NOT\_FUTURE
    ]
    #v(.55em)
    - *PASS / FAIL / UNKNOWN* con motivo y valores consumidos.
    - Umbrales por campo/extractor (`min_confidence`): config, no código.
    - `UNKNOWN` ⇒ duda ⇒ ESCALAR; `FAIL` ⇒ `outcomes.on_fail`.
  ],
  [
    ```json
    {
      "rule_verdicts": [
        {"rule": "TOTALS_MUST_MATCH", "verdict": "PASS"},
        {"rule": "NIF_IN_MASTER", "verdict": "UNKNOWN"}
      ],
      "rule_outcomes": {"NIF_IN_MASTER": "ESCALAR"}
    }
    ```
  ],
)

#v(.6em)
#align(center)[#text(weight: 800, size: .85em)[Mismos campos + misma config ⇒ misma salida, byte a byte.]]

== Ocho ADRs (1/2) · decisión y extracción

#grid(
  columns: (1fr, 1fr),
  gutter: (.7em, .42em),
  align: top,
  card([ADR-01 · Motor determinista], [Reglas en código; umbrales y política como configuración versionada.], accent: gold),
  card([ADR-02 · Extracción en dos bloques], [Features crudas → parser con candidatos; umbrales calibrados con el corpus.], accent: gold),
  card([ADR-03 · Pipeline desacoplada], [Colas por bloque; el ERP solo por costura de adaptador.], accent: gold),
  card([ADR-04 · Trazabilidad en BD], [PouchDB local + réplica CouchDB; decisiones inmutables.], accent: gold),
)

#v(.45em)
#text(size: .72em, fill: brown)[Cada ADR lleva contexto, alternativas, decisión, consecuencias y *evidencia medida*. Detalle en `albertitos_plan.pdf`.]

== Ocho ADRs (2/2) · operación y política

#grid(
  columns: (1fr, 1fr),
  gutter: (.7em, .42em),
  align: top,
  card([ADR-05 · Rung 5 cloud + revisión], [La lectura cloud es otro candidato, nunca respuesta; la cola no bloquea el lote.], accent: gold),
  card([ADR-06 · Todos los candidatos], [Las reglas evalúan `values[]` con provenance; la auditoría cazó 87 falsos NO\_PAGAR.], accent: gold),
  card([ADR-07 · App de escritorio], [pywebview, no Electron: la misma UI Vue en ventana nativa Linux/Windows/Mac.], accent: gold),
  card([ADR-08 · `outcomes.on_fail`], [La frontera NO\_PAGAR/ESCALAR es datos por regla; una regla nunca paga.], accent: gold),
)

#v(.45em)
#text(size: .72em, fill: brown)[El lote 2 traerá la regla v4 cargada como *datos*, sin tocar el motor.]

/* ═══ 03 · TRAZABILIDAD, ESCALA Y COSTE ════════════════════ */

= 03 · Trazabilidad, escala y coste
El estado vive en disco; los números, medidos

== Todo deja rastro

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
#text(size: .78em)[UI + 2 runners en paralelo: peor *p95 7,7 ms*, ~*109 archivos/s por runner*, 0 incidencias. Hardware medido: *8 núcleos · 12 GB*.]

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
  *87 NO\_PAGAR eran falsos*. ADR-06: ahora las reglas evalúan *todos* los candidatos con provenance.
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
