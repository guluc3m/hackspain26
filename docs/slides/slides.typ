// 500 Sombras de Alberto — defensa (10 min) · guluc3m
// Compilar:  typst compile --root .. --font-path ../report/fonts slides.typ
// Los diagramas son los mismos del informe (docs/report/diagram/): tamaños en
// em, así que escalan con el texto de la diapositiva (envolver en text(size:)).

#import "theme.typ": *
#import "../report/diagram/arquitectura-general.typ": arquitectura-general
#import "../report/diagram/escalera-confianza.typ": escalera-confianza
#import "../report/diagram/colapso-candidatos.typ": colapso-candidatos

#show: hs-theme.with(aspect-ratio: "16-9")

/* ── PORTADA ─────────────────────────────────────────────── */

#hs-title-slide[
  #text(size: .6em, style: "italic", fill: brown)[Reto · #challenge]
  #v(.55em)
  #text(font: display-font, size: 2.15em, fill: ink)[ALBERTITOS]
  #v(.3em)
  #line(length: 30%, stroke: 4.5pt + gold)
  #v(.55em)
  #text(size: .9em, weight: 500, fill: brown)[Del PDF a la decisión, con evidencia]
  #v(1em)
  #chip([FACTURA], fill: gold) #h(.4em) #arrow-right #h(.4em)
  #chip([DECISIÓN], fill: gold) #h(.4em) #arrow-right #h(.4em)
  #chip([TRAZA], fill: gold)
  #v(1.1em)
  #text(font: display-font, size: .7em, fill: ink)[guluc3m]
  #v(.4em)
  #text(size: .58em, fill: brown)[Casais · Giurgiu · Saghin · Díaz]
  #v(.5em)
  #text(font: display-font, size: .48em, fill: brown, tracking: .06em)[ETSIT UPM · 20 SEP 2026]
]

/* ── 01 · PROBLEMA ───────────────────────────────────────── */

= 01 · El problema
Documento → decisión → evidencia

== El caso de Alberto

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: .7em,
  card([ENTRADA], [500 PDFs, algunas escaneadas], accent: teal),
  card([MAESTRO], [Proveedores, pedidos y normas de pago], accent: slate),
  card([SISTEMA], [ERP legado de 2009], accent: orange),
)

#v(.55em)
#text(weight: 800, fill: brown)[Una decisión por factura · un registro por archivo]
#v(.5em)
#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: .7em,
  card([PAGAR], [Trazable], accent: teal),
  card([NO\_PAGAR], [Negativo definitivo], accent: red),
  card([ESCALAR], [Duda razonable], accent: gold),
)

#v(.5em)
#quote[Ante duda razonable, escalar antes que pagar.]

/* ── 02 · ARQUITECTURA ───────────────────────────────────── */

= 02 · Arquitectura
Dos fases separadas, un contrato común

== De PDF a decisión

#text(size: .7em)[#arquitectura-general()]

#v(.55em)
#text(size: .68em, fill: brown)[Extracción y decisión no se tocan: añadir una regla no cambia la extracción, y añadir un tipo de archivo no cambia el motor.]

/* ── escalera ── */

== La escalera de extracción · por página, siete peldaños

#text(size: .78em)[#escalera-confianza()]

#v(.5em)
#text(size: .74em, fill: brown)[Cada peldaño es *omisible*: si falta, se registra `skipped:<razón>` y se degrada — el lote nunca se detiene. (1–4 en local, 5–7 en la nube.)]

/* ── dos bloques ── */

== Dos bloques, cero cajas negras

#grid(
  columns: (1fr, 1fr),
  gutter: .8em,
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

#v(.55em)
#text(size: .78em)[Nunca se colapsa un campo en el store. El escalar se elige solo en la regla que lo consume, y se registra *cuál* y *por qué*:]

#v(.4em)
#text(size: .85em)[#colapso-candidatos()]

#v(.45em)
#text(size: .72em, fill: brown)[Multilingüe (7 idiomas) · inmune a trampas OCR · emisor ≠ cliente.]

/* ── 03 · DECISIÓN ───────────────────────────────────────── */

= 03 · Decisión
Determinista, explicable, configurable

== Motor de reglas determinista

#grid(
  columns: (1.25fr, 1fr),
  gutter: 1em,
  [
    - Reglas en código con código estable: `TOTALS_MUST_MATCH`, `NIF_IN_MASTER`, `IVA_CONSISTENT`, `ORDER_PENDING`, `NO_DOUBLE_PAYMENT`…
    - Cada regla devuelve *PASS / FAIL / UNKNOWN* con motivo y valores consumidos.
    - Umbrales de confianza por *campo* y *extractor*: configuración versionada, no código.
    - Salida: resultado + reglas + `config_snapshot`.
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

#v(.5em)
#text(weight: 800, size: .82em)[Mismos campos + misma config ⇒ misma salida, byte a byte.]

/* ── frontera ── */

== NO\_PAGAR no es ESCALAR

#grid(
  columns: (1fr, 1fr),
  gutter: .8em,
  card([NO_PAGAR], [Negativo definitivo. Ninguna persona lo revierte.], accent: red),
  card([ESCALAR], [Duda razonable o evidencia incompleta. Decide una persona.], accent: gold),
)

#v(.6em)
#text(size: .82em)[La frontera es *datos*, no código:]
#v(.35em)
#block(fill: sand, stroke: .8pt + ink, inset: .65em, width: 100%,
  text(font: mono-font, size: .6em)[
    #"outcomes.default": "NO_PAGAR"
    #"outcomes.on_fail.NIF_IN_MASTER": "ESCALAR"
    #"outcomes.on_fail.IBAN_MATCHES_MASTER": "ESCALAR"]
  ,
)
#v(.45em)
#text(size: .74em, fill: brown)[Una regla *jamás* puede resolver `PAGAR`; la carga de config lo rechaza. Cada cambio de política es un ADR.]

/* ── 04 · TRAZABILIDAD ───────────────────────────────────── */

= 04 · Trazabilidad y operación
El estado vive en disco, no en memoria

== Todo deja rastro

- Cada factura tiene un *UUID*; `file_id` es el nombre exacto del PDF.
- *SQLite (WAL) + ledger JSONL* append-only. Sin servicios extra; recuperar = copiar un fichero.
- *Idempotente y resumible*: clave `(sha256, etapa, engine_version, config_version)`. Re-procesar es un no-op.
- Cada etapa escribe una fila de evidencia:

#v(.35em)
#grid(
  columns: (1fr, 1fr),
  gutter: .7em,
  text(font: mono-font, size: .56em, fill: ink)[
    invoice_id · stage · extractor
    extractor_version · config_version
    sha256 · latency_ms
    confidence · outcome · detail
  ],
  [
    #text(size: .74em)[Los *campos y candidatos* se conservan en el store; los valores no se colapsan. `rule_verdicts` y `config_snapshot` quedan unidos a cada decisión.]
  ],
)

/* ── revisión ── */

== La duda no bloquea el lote

#grid(
  columns: (1fr, 1fr),
  gutter: .8em,
  card([COLA DE REVISIÓN], [
    - imagen de la página
      + todos los candidatos, lado a lado
    - desacuerdo resaltado
    - trabajo pendiente visible
  ], accent: gold),
  card([CORRECCIÓN HUMANA], [
    - override con *provenance*
      (quién, cuándo, antes/después)
    - afecta *solo* a la extracción
    - el motor recalcula determinista
    - replayable y auditable
  ], accent: teal),
)

#v(.6em)
#align(center)[#text(font: display-font, size: .7em, fill: brown)[El pipeline avanza mientras el humano duerme.]]

/* ── 05 · ESCALA Y FALLOS ────────────────────────────────── */

= 05 · Escala y fallos
Medido, no estimado

== Escala y coste

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: .8em,
  row-gutter: .8em,
  kpi([4,16], [archivos/s · lote 1], color: teal),
  kpi([2 636], [archivos/s · peldaño 1], color: teal),
  kpi([2,3 s], [latencia media], color: teal),
  kpi([8 / 12], [núcleos / GB], color: ink),
  kpi([≈ 0 €], [coste local], color: teal),
  kpi([109], [archivos/s · runner], color: ink),
)

#v(.7em)
#text(size: .76em)[94,2 % del corpus resuelve por texto (peldaño casi gratis). El coste cloud aparece solo en páginas difíciles y queda *cacheado por página*: nunca se refactura.]
#v(.35em)
#text(size: .7em, fill: brown)[UI + 2 runners simultáneos: peor p95 7,7 ms, 0 errores.]

== Resiliencia probada

#grid(
  columns: (1fr, 1fr),
  gutter: .7em,
  row-gutter: .6em,
  card([PROVEEDOR CAÍDO], [3 intentos, la página va a revisión, el lote sigue. *PASS*], accent: teal),
  card([BACKOFF 429], [`Retry-After` respetado, 0 llamadas extra. *PASS*], accent: teal),
  card([CRASH + REANUDACIÓN], [Reanudación completa, *0 duplicados*. *PASS*], accent: teal),
  card([LEDGER CORRUPTO], [El histórico sobrevive; recuperación desde la copia. *PASS*], accent: teal),
)

#v(.55em)
#text(size: .78em)[Un peldaño que falta no para el lote: se registra `skipped:<razón>`, se degrada y el veredicto honesto es *ESCALAR*. 4 / 4 drills en PASS.]

/* ── resultados ── */

== Lote 1, auditado

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: .8em,
  kpi([433], [PAGAR], color: teal),
  kpi([22], [NO\_PAGAR], color: red),
  kpi([45], [ESCALAR], color: orange),
)

#v(.8em)
#card([LA AUDITORÍA ENCONTRÓ LA TRAMPA], [
  El motor colapsaba `total` al *primer* candidato — «Subtotal» en vez de «TOTAL A PAGAR»:
  *87 NO\_PAGAR eran falsos*. Ahora las reglas evalúan *todos* los candidatos y citan el elegido.
  Reprocesado: *86 NO\_PAGAR → PAGAR, 0 regresiones.*
], accent: orange)

/* ── ADRs ────────────────────────────────────────────────── */

= ADRs y trade-offs
Ocho decisiones, cada una con evidencia

== Decisiones que sostienen el sistema

#grid(
  columns: (1fr, 1fr),
  gutter: .6em,
  row-gutter: .5em,
  card([ADR-01 · Motor determinista], [Reglas en código; umbrales como configuración versionada.], accent: gold),
  card([ADR-02 · Extracción en dos bloques], [`features` crudas y `parser` con candidatos y confianza.], accent: gold),
  card([ADR-03 · Pipeline desacoplada], [Colas por bloque; el ERP solo por costura de adaptador.], accent: gold),
  card([ADR-04 · Trazabilidad en BD], [SQLite + ledger append-only; histórico y reentrenamiento.], accent: gold),
  card([ADR-05 · Rung 5 + revisión], [Cloud solo como candidato; la cola humana no bloquea.], accent: gold),
  card([ADR-06 · Todos los candidatos], [Evaluar `values[]` con provenance evita falsos negativos.], accent: gold),
)

#v(.45em)
#text(size: .72em, fill: brown)[Y dos más: *ADR-07* app de escritorio con pywebview · *ADR-08* `outcomes.on_fail` configurable. Detalle en `albertitos_plan.pdf`.]

/* ── BONUS ───────────────────────────────────────────────── */

= Bonus · Modo Alberto

== Para que Alberto lo use de verdad

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: .7em,
  card([UN PASO], [`iniciar.sh` idempotente. Sin instalación ni terminal.], accent: orange),
  card([ESCRITORIO], [pywebview: ventana nativa en Linux, Windows y Mac. Cero Node, cero runtime extra.], accent: orange),
  card([LENGUAJE LLANO], [UI en español con ayuda contextual; la misma en navegador o ventana.], accent: orange),
)

#v(1em)
#align(center)[#text(font: display-font, size: .8em, fill: brown)[La operación, por dentro — sin jerga.]]

/* ── CIERRE ──────────────────────────────────────────────── */

#hs-focus-slide(footer-text: "guluc3m · github.com/guluc3m/hackspain26")[
  #text(font: display-font, size: 1.5em)[¿Preguntas?]
  #v(.6em)
  #text(size: .95em)[Documento → decisión → evidencia.]
]
