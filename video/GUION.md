# Guion — Vídeo Remotion 3 min · filemaid · 500 Sombras de Alberto

30 fps · 1920×1080 · paleta y fuentes de docs/report/lib.typ (papel crema #f4ecd8, tinta #2a170f, oro #eab619, naranja #d96b2a, teal #35858a, rojo #cc291f; Bungee + DM Sans). Estética documental, sin gradientes.

Cada escena sigue la estructura **PROBLEMA → SOLUCIÓN → BENEFICIO/CAVEAT**: la voz narra el detalle (guion definitivo en `narracion/guion_tts.md`, ya grabado en `public/narracion/esc{1..8}.wav`) y la pantalla muestra solo lo esencial. Reparto orientativo de frames locales: P ≈ 25 %, S ≈ 45 %, B/C ≈ 30 %. Kicker de cada escena: subtítulo humano, no técnico.

## Estructura (5400 frames, 8 escenas) y colocación de la voz

`SCENES` de `src/scenes.ts` no cambia. La voz entra dentro de la `Sequence` de cada escena con un `delay` local (tabla del `narracion/SPEC.md`, duraciones reales medidas de los wavs):

| # | Escena | Seg | Frames | Inicio global | Voz: frame local | Voz: frame global | Voz dur. |
|---|--------|-----|--------|---------------|------------------|-------------------|----------|
| 1 | portada     | 0:00–0:12 | 0–360    | 0    | 30 | 30    | 9,72 s  |
| 2 | problema    | 0:12–0:35 | 360–1050 | 360  | 30 | 390   | 21,02 s |
| 3 | producto    | 0:35–0:55 | 1050–1650| 1050 | 36 | 1086  | 17,37 s |
| 4 | escalera    | 0:55–1:25 | 1650–2550| 1650 | 60 | 1710  | 24,41 s |
| 5 | traza       | 1:25–2:00 | 2550–3600| 2550 | 75 | 2625  | 27,48 s |
| 6 | adrs        | 2:00–2:20 | 3600–4200| 3600 | 45 | 3645  | 15,98 s |
| 7 | resiliencia | 2:20–2:40 | 4200–4800| 4200 | 30 | 4230  | 17,35 s |
| 8 | escala      | 2:40–3:00 | 4800–5400| 4800 | 30 | 4830  | 17,70 s |

## Escena 1 · Portada — «quinientas facturas»

- **PROBLEMA (≈ frames locales 0–90).** Hook: «500» gigante animado; el número es el gancho, no un dashboard.
- **SOLUCIÓN (≈ 90–360).** FILEMAID + chips FACTURA/DECISIÓN/TRAZA; filemaid lee, comprueba y decide.
- **BENEFICIO (cierre).** «y siempre enseña la prueba».
- **Voz (esc1, 9,72 s):** «Alberto paga facturas: quinientas al mes, en PDF. Esto es filemaid, un asistente que las lee, las comprueba y decide qué pagar — enseñando siempre la prueba» (`narracion/guion_tts.md`).
- **Datos (scenes.ts):** `METRICS.nArchivos` = 500.

## Escena 2 · El problema de Alberto — «decidir parece fácil, no lo es»

- **PROBLEMA.** Decidir parece trivial: chip PAGAR / NO_PAGAR / ESCALAR.
- **SOLUCIÓN (caveats de las dos alternativas ingenuas, dos tarjetas tachadas con tono entretenido):** «LLM: lento y a veces inventa» · «OCR clásico: se rinde con un escaneo malo».
- **BENEFICIO/CAVEAT.** La norma: «ante duda razonable, escalar antes que pagar» + tarjeta «lo que Alberto necesita: precisión · rapidez · prueba».
- **Voz (esc2, 21,02 s):** narra el mismo arco — grandes modelos tardan e inventan, el OCR clásico se tropieza, y sin evidencia nadie responde; ante la duda, escalar antes que pagar (`narracion/guion_tts.md`).
- **Datos (scenes.ts):** `METRICS` (433 PAGAR / 22 NO_PAGAR / 45 ESCALAR del lote 1) y `CASO_*` como contexto de decisión.

## Escena 3 · El producto — «el trabajo nocturno lo hace la app»

- **PROBLEMA.** «¿y quién hace el trabajo nocturno?».
- **SOLUCIÓN.** Los 5 pasos del flujo (lista mantenida) + captura del producto rotando.
- **BENEFICIO.** «tú solo miras cuando algo huele raro» (notificación). Sin recargar: la voz lleva el detalle.
- **Voz (esc3, 17,37 s):** app de escritorio, sueltas los PDFs, el watcher los ingesta solo, el lote corre 24/7 sin prompts; solo cuando algo huele raro mira un humano (`narracion/guion_tts.md`).
- **Datos (scenes.ts):** pasos del flujo y screenshot (secciones existentes de la escena producto).

## Escena 4 · La escalera de confianza — «¿quién lee una página difícil?»

- **PROBLEMA.** «una página difícil, ¿quién la lee?».
- **SOLUCIÓN.** Los 7 escalones (tabla mantenida, cabeceras simplificadas a QUÉ / COSTE): texto vectorial → QR → Tesseract → VLM local → TypeSafe → Firecrawl → cloud VLM.
- **BENEFICIO/CAVEAT.** «94 % se resuelve gratis y al instante» (métrica destacada) + caveat «y si un escalón falla, degrada con calma: el lote nunca se para».
- **Voz (esc4, 24,41 s):** recorre los escalones en orden, gratis e instantáneo primero, la nube como último recurso y nunca respuesta; degradar con calma (`narracion/guion_tts.md`).
- **Datos (scenes.ts):** `ESCALERA` (7 escalones con coste/velocidad medidos) y `METRICS.textoUsablePct` = 94,2 %.

## Escena 5 · Trazabilidad — «¿por qué NO se paga esta?»

- **PROBLEMA.** La pregunta en pantalla: «¿por qué NO se paga esta factura?».
- **SOLUCIÓN.** 3 casos reales (columnas y reglas mantenidas): duplicado → NO_PAGAR; escaneo ilegible (7 reglas UNKNOWN) → ESCALAR; fecha ilegible → ESCALAR. Menos siglas en pantalla; la voz explica.
- **BENEFICIO.** «todo se puede auditar: nada se inventa» (chips de evidencia: huella, extractor, confianza, configuración, latencia).
- **Voz (esc5, 27,48 s):** sigue las tres decisiones una a una y cierra con la evidencia que guarda cada decisión (`narracion/guion_tts.md`).
- **Datos (scenes.ts):** `CASO_DUPLICADO` (factura_8801.pdf, NO_DOUBLE_PAYMENT:FAIL), `CASO_SCAN` (scan_001.pdf, 7 UNKNOWN), `CASO_ESCALAR` (2026-03-19_P008.pdf, DATE_VALID_NOT_FUTURE:UNKNOWN) y `REGLAS` (los 8 códigos del motor).

## Escena 6 · Reglas deterministas / ADRs — «misma entrada, misma salida»

- **PROBLEMA.** «una IA que decide distinto cada vez no es pagable».
- **SOLUCIÓN.** Motor puro: mismos datos y misma configuración ⇒ misma salida, byte a byte.
- **BENEFICIO/CAVEAT.** ADR-06 (86 falsos NO_PAGAR corregidos, 0 regresiones) + «8 decisiones escritas (ADRs)»; caveat: la política FAIL → NO_PAGAR/ESCALAR es dato, no código.
- **Voz (esc6, 15,98 s):** determinismo byte a byte y el fallo de los 86 falsos no pagar corregido como decisión de arquitectura, ocho ADRs (`narracion/guion_tts.md`).
- **Datos (scenes.ts):** `METRICS` y `REGLAS` (motor puro sobre snapshot de reglas + umbrales); ADR-06 = 86 corregidos / 0 regresiones.

## Escena 7 · Resiliencia — «¿y si algo cae a mitad del lote?»

- **PROBLEMA.** «¿y si un proveedor cae a mitad del lote?».
- **SOLUCIÓN.** Los 4 drills PASS: proveedor caído, backoff-429, crash-reanudación, ledger-corrupto.
- **BENEFICIO/CAVEAT.** «reanudar nunca duplica ni re-factura» + lema «caerse no es opción: degradar».
- **Voz (esc7, 17,35 s):** degradación del escalón, reanudación sin duplicados por idempotencia de huella, cuatro simulacros, cuatro pasan (`narracion/guion_tts.md`).
- **Datos (scenes.ts):** `DRILLS` (4 drills PASS con detalle medido).

## Escena 8 · Escala y coste — «¿cuánto cuesta?»

- **PROBLEMA.** La pregunta directa: «¿cuánto cuesta?».
- **SOLUCIÓN.** La fórmula con números (tabla): 94 % × ~0 ms + resto × CPU local.
- **BENEFICIO.** «500 facturas en 2 min · 0,00 € cloud».
- **CAVEAT/plan + cierre.** Más volumen = concurrencia; nuevo formato = 1 extractor. Cierre: «Alberto duerme. Y paga lo justo.» (línea final grande).
- **Voz (esc8, 17,70 s):** la fórmula simple, quinientas facturas en dos minutos, cero euros en la nube, y el cierre («Alberto duerme. Y paga lo justo») (`narracion/guion_tts.md`).
- **Datos (scenes.ts):** `METRICS` (500 archivos, 120,1 s ≈ 4,162 files/s, 0,00 € cloud, 94,2 % texto vectorial) y `ESCALERA` para el reparto de coste.

## Reglas (el motor REAL: 8 códigos, src/filemaid/rules/rules.py RULE_CODES)

1. `DATE_VALID_NOT_FUTURE` — fecha válida y no futura.
2. `IBAN_MATCHES_MASTER` — el IBAN de la factura está en el maestro.
3. `IVA_CONSISTENT` — base + IVA = total (tolerancia 0,01 €).
4. `NIF_IN_MASTER` — el NIF del proveedor está en el maestro.
5. `NO_DOUBLE_PAYMENT` — el documento no es un duplicado ya pagado.
6. `ORDER_BELONGS_TO_SUPPLIER` — el pedido existe, pertenece al proveedor y **el importe de la factura cuadra con el importe del pedido** (tolerancia 0,01 €; el cruce de importe vive dentro de esta regla, rules.py:94–146).
7. `ORDER_PENDING` — el pedido está pendiente de pago (no ya servido/cerrado).
8. `TOTALS_MUST_MATCH` — los totales declarados cuadran con la suma de líneas.

FAIL ⇒ NO_PAGAR · UNKNOWN ⇒ ESCALAR. No existen otros códigos (p. ej. ORDER_AMOUNT_MATCHES, NO_EMBEDDED_INSTRUCTIONS o PROVEEDOR_FANTASMA no están en el motor actual).

## Reglas visuales
- Sin gradientes; esquinas rectas (radius 0–2px); bordes 1–2px tinta.
- StatusBadge: PAGAR=teal, NO_PAGAR=rojo, ESCALAR=naranja.
- Datos reales del repo: data_lote1.json, data_drills.json, data_dryrun.json, data_impacto.json, data_outcomes_lote1.jsonl (video/).
- Texto mínimo por frame; máx 5 bullets visibles a la vez. La voz narra el detalle; la pantalla muestra lo esencial.
- Duración final 180 s exactos, 5400 frames.
- Audio: voz en `public/narracion/esc{1..8}.wav` (colocación en la tabla de arriba) + música suave `public/music.wav` a volumen bajo; integrados por Remotion en el render (ver README).
