# Vídeo filemaid — Remotion, 3 min (5400 frames @ 30 fps, 1920×1080)

## Renderizar

Desde `video/` (dependencias ya instaladas en `node_modules`):

```sh
npm run render        # = npx remotion render src/index.tsx filemaid out/filemaid.mp4
```

Salida: `video/out/filemaid.mp4` (180 s exactos). El MP4 final lleva **voz + música integrados** (etiquetas `<Audio>` en `src/FilemaidVideo.tsx`); no requiere ningún postproceso externo.

Stills de verificación visual (uno por escena clave):

```sh
npx remotion still src/index.tsx filemaid out/still-portada.png --frame=100
npx remotion still src/index.tsx filemaid out/still-traza.png --frame=3000
npx remotion still src/index.tsx filemaid out/still-escalera.png --frame=2000
```

(El compositor se llama `filemaid` y el punto de entrada `src/index.tsx`.)

> **Artefactos trackeados a propósito**: `video/out/filemaid.mp4` y los wav de
> `video/narracion/` + `video/public/` (voz y música, incluida la pista externa
> `public/music_yt.wav`) están versionados en git
> por decisión del product owner aunque sean binarios generados. Los dos TTFs
> que sirve el render viven en `video/public/fonts/` (copia byte a byte de
> `frontend/public/fonts/`) y se registran desde `src/fonts.ts`.

## Audio

El vídeo lleva dos pistas, integradas por Remotion en el render:

- **Voz** (volumen 1.0): narración en español generada con **piper** `es_ES-carlfm-x_low`, una por escena, colocada dentro de la `Sequence` de cada escena según la tabla de colocación de `narracion/SPEC.md` (duraciones reales: esc1 9,72 s … esc8 17,70 s). Los textos narrados son los de `narracion/guion_tts.md` (fuente de verdad, no reescribir). Los wavs servidos en el render viven en `public/narracion/esc{1..8}.wav` (copia de `narracion/esc{1..8}.wav`).
- **Música** (volumen **0.07**, deliberadamente muy por debajo de la voz): pista **externa** servida en `public/music_yt.wav`, descargada de <https://www.youtube.com/watch?v=JMfYqpLLAnc> (solo audio) y normalizada a **180 s exactos**, 44,1 kHz estéreo PCM 16 bit, con fade-in de 1,5 s y fade-out de 3 s.

> ⚠️ **Aviso de copyright**: `public/music_yt.wav` es **material de terceros con
> copyright** (tema publicado en YouTube), no música propia del proyecto y no se
> reclama su autoría. Se usa como banda sonora de fondo del vídeo entregado;
> antes de cualquier publicación o difusión externa hay que revisar la licencia
> del tema original con su titular.

El pad anterior (`narracion/make_music.py` → `public/music.wav`) **se conserva**
en el repo (y sigue siendo reproducible con semilla fija), pero **ya no lo usa la
composición**: `src/FilemaidVideo.tsx` monta únicamente `music_yt.wav`.

Regenerar la voz (piper con el modelo `es_ES-carlfm-x_low`). El texto de cada
escena no está en ficheros sueltos: vive en `narracion/guion_tts.md` (fuente de
verdad, no reescribir), en el párrafo que sigue a cada cabecera `**escN …:**`.

```sh
# un wav por escena; ajusta --length-scale si el texto no cabe con holgura
for i in 1 2 3 4 5 6 7 8; do
  awk -v n="$i" '$0 ~ "^\\*\\*esc" n " " {on=1; next} /^\*\*esc/{on=0} on{print}' \
      narracion/guion_tts.md | sed '/^$/d' \
    | piper --model es_ES-carlfm-x_low --output_file "narracion/esc$i.wav"
done
```

Regenerar el pad antiguo y copiar los wavs a `public/` (ambos comandos desde `video/`, que es el cwd del que parte `make_music.py` para escribir `public/music.wav`). Del bloque solo se usa la voz: el pad **no** entra en el render actual:

```sh
python3 narracion/make_music.py        # escribe public/music.wav (180 s exactos, semilla fija: reproducible) — ya NO lo usa la composición
cp narracion/esc{1..8}.wav public/narracion/
```

Comprobar duraciones antes de renderizar (la voz debe caber en su escena con ≥ 0,8 s de holgura):

```sh
for f in narracion/esc{1..8}.wav; do ffprobe -v error -show_entries format=duration -of csv=p=0 "$f"; done
```

## Verificación del render final

Fecha: 2026-09-20. Render **final, con voz + música integradas**: es el MP4 que
se entrega, `out/filemaid.mp4`.

Comando exacto (desde `video/`), tiempo de pared **179 s**:

```sh
npx remotion render src/index.tsx filemaid out/filemaid.mp4 --concurrency 14
```

Medidas del MP4 entregado (ffprobe del binario incluido en
`node_modules/@remotion/compositor-linux-x64-gnu/`):

- Duración de vídeo: **5400 frames = 180,000000 s exactos** (el contenedor
  reporta 180,053333 s: relleno del codificador AAC).
- Resolución / fps: **h264 1920×1080 @ 30 fps** (avg_frame_rate 30/1); pista de
  audio **aac** presente (voz 1.0 + música 0.07).
- Sonoridad del mix (`volumedetect`): **mean −20,6 dB / max −2,7 dB**. En los
  huecos sin voz la pista suena sola a **≈ −45 dB**, es decir **~27 dB por
  debajo** de la voz (escenas medidas a ≈ −17 dB): la música queda claramente
  subordinada a la narración. El pico lo marca la voz, no la música.
- Tamaño: **16 605 156 bytes (~16,6 MB)**, < 20 MB.
- sha256: `290a47a02438ed390932df01a3d5f9839b7d15630c71137ba0bad142bf15ad4a`.

Stills de verificación del último pase en `out/rt-<frame>.png`, generados con
`npx remotion still`: las fronteras de cada tiempo narrativo (P→S→B/C) y los
últimos 30 frames de cada escena, con las animaciones ya asentadas. Inspección
visual frame a frame:

Tipografías: los TTFs reales de la app (`frontend/public/fonts/Bungee-Regular.ttf`
y `DMSans.ttf`) se copian a `video/public/fonts/` y se registran en `src/fonts.ts`
con `delayRender`/`continueRender` + `document.fonts.load`, así que stills y MP4
salen con **Bungee** (títulos, número, kickers) y **DM Sans** (cuerpo), no con el
fallback del sistema.

| Escena | Still | Verificado |
|---|---|---|
| 1 · Portada | `rt-330.png` | El «500» con «facturas al mes, en PDF», FILEMAID, «las lee · las comprueba · decide», «y siempre enseña la prueba», chips FACTURA/DECISIÓN/TRAZA y el pie de créditos, sin solapes |
| 2 · El problema | `rt-690.png` | Las 2 alternativas tachadas (LLM / OCR clásico) con chips PAGAR teal · NO_PAGAR rojo · ESCALAR naranja; norma «escalar antes que pagar» y tarjeta «precisión · rapidez · prueba» |
| 3 · Producto | `rt-1470.png` | Los 5 pasos del flujo (watcher, lote 24/7, notificación, revisión, sync con el servidor) + captura rotando; titular a 74 px en una sola línea |
| 4 · Escalera | `rt-2260.png` | Los 7 escalones con QUÉ CORRE / COSTE (la tabla no muestra latencias: 0 € en los escalones 1–4, pago por token en el 7), el pie «El VLM local (~4 GB RAM) solo arranca si el servidor está offline.» y el caveat de degradación |
| 5 · Trazabilidad | `rt-3130.png` | Los 8 rule codes visibles en las 3 columnas, cada columna entrando con su caso: NO_PAGAR rojo, ESCALAR naranja, UNKNOWN naranja |
| 6 · ADRs | `rt-3790.png` | MOTOR PURO + caja «misma entrada ⇒ misma salida · byte a byte»; ADR-06 con 86 corregidos / 0 regresiones y «8 decisiones escritas (ADRs)» |
| 7 · Resiliencia | `rt-4770.png` | Los 4 drills PASS (provider-caído, backoff-429, crash-reanudación, ledger-corrupto) + el bloque CLIENTE/SERVIDOR (1500×440: watcher, escalera, motor, store local ⇄ replicación CouchDB, cola de revisión) y el cierre «caerse no es opción: degradar» |
| 8 · Escala | `rt-5370.png` | Tabla de coste (94 % del corpus 0,00 €, 120 s para 500 PDFs, Cloud VLM 0,00 €, 10 000 facturas), «2 min / 0,00 €» y el cierre «Alberto duerme. Y paga lo justo.» |

Nota sobre la escena 5: las 3 columnas entran escalonadas al ritmo de la voz
(`i*165` frames) y cada columna escalona sus 8 reglas (`j*7`); en `rt-3130.png`
los 8 códigos de RULE_CODES están asentados en las tres columnas.

Nota sobre la escena 7: el bloque CLIENTE/SERVIDOR entra dentro del tiempo B/C
con `f` local propia; el contenido (watcher, escalera, motor, store local,
replicación CouchDB, cola de revisión, histórico de overrides) está citado en
`docs/capacidad_y_coste.md`, `docs/db-mig.md` y `src/filemaid/desktop/watcher.py`.

## Cómo se verificó

1. **ffprobe del MP4 final** (binario incluido en
   `node_modules/@remotion/compositor-linux-x64-gnu/`): duración
   180,000000 s, 1920×1080, avg_frame_rate 30/1.
2. **sha256 + tamaño**: `sha256sum out/filemaid.mp4` y `stat -c %s`
   sobre el MP4 renderizado con el código vigente.
3. **Stills de los tiempos narrativos**: `npx remotion still` en las
   fronteras P→S→B/C de cada escena y en sus últimos 30 frames
   (`out/rt-<frame>.png`), más los frames densos de la tabla de la
   escalera, las 3 columnas de traza, los drills de resiliencia, la tabla
   de coste y el diagrama CLIENTE/SERVIDOR. Inspección visual de cada
   still: sin solapes ni recortes (el ink de cada bloque se midió contra
   el área de contenido de 1740×960), colores de badge correctos, datos
   idénticos a los ficheros `data_*.json`.
4. **Cruce con la fuente de verdad**: cada cifra en pantalla se cotejó
   contra `data_lote1.json`, `data_dryrun.json`, `data_drills.json`,
   `data_impacto.json` y los tres casos reales de
   `data_outcomes_lote1.jsonl`; las 8 reglas contra `RULE_CODES` de
   `src/filemaid/rules/rules.py`.

## Datos que usa

Todo lo que aparece en pantalla sale de ficheros medidos del repo; nada está inventado:

| Fichero | Qué aporta | Escena |
|---|---|---|
| `data_outcomes_lote1.jsonl` | Corrida real con rule_ids por file_id: `factura_8801.pdf` NO_PAGAR (NO_DOUBLE_PAYMENT), `scan_001.pdf` ESCALAR (7 UNKNOWN de las 8 reglas), `2026-03-19_P008.pdf` ESCALAR (DATE_VALID_NOT_FUTURE) | Traza (5) |
| `data_dryrun.json` | Dry-run del corpus: rung1 2 636 files/s, 0,4 ms mean; rung2 42,1 ms | Escalera (4) |
| `data_drills.json` | 4 drills PASS: provider-caído, backoff-429, crash-reanudación, ledger-corrupto | Resiliencia (7) |
| `data_impacto.json` | ADR-06: reproceso de 108 NO_PAGAR → 86 falsos corregidos, 0 regresiones | ADRs (6) |
| `data_lote1.json` | Lote 1 real: 500 archivos → 433 PAGAR / 22 NO_PAGAR / 45 ESCALAR; 4,162 files/s; 120,1 s; 0,00 € cloud; 471/500 (94,2 %) texto vectorial | Escala (8) |

Las 8 reglas mostradas son exactamente `RULE_CODES` de `src/filemaid/rules/rules.py`
(DATE_VALID_NOT_FUTURE, IBAN_MATCHES_MASTER, IVA_CONSISTENT, NIF_IN_MASTER,
NO_DOUBLE_PAYMENT, ORDER_BELONGS_TO_SUPPLIER, ORDER_PENDING, TOTALS_MUST_MATCH).
El cruce de importe factura↔pedido vive dentro de `ORDER_BELONGS_TO_SUPPLIER`
(rules.py:94–146). Detalle completo en `GUION.md`.
