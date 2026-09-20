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

## Audio

El vídeo lleva dos pistas, integradas por Remotion en el render:

- **Voz** (volumen 1.0): narración en español generada con **piper** `es_ES-carlfm-x_low`, una por escena, colocada dentro de la `Sequence` de cada escena según la tabla de colocación de `narracion/SPEC.md` (duraciones reales: esc1 9,72 s … esc8 17,70 s). Los textos narrados son los de `narracion/guion_tts.md` (fuente de verdad, no reescribir). Los wavs servidos en el render viven en `public/narracion/esc{1..8}.wav` (copia de `narracion/esc{1..8}.wav`).
- **Música** (volumen ≈ 0.10–0.14): pad ambiente suave, sin ritmo marcado que compita con la voz. 180 s exactos en `public/music.wav`, generada con `narracion/make_music.py` (solo stdlib).

Regenerar la voz (piper con el modelo `es_ES-carlfm-x_low`):

```sh
# un wav por escena; ajusta --length-scale si el texto no cabe con holgura
for i in 1 2 3 4 5 6 7 8; do
  piper --model es_ES-carlfm-x_low \
    --output_file "narracion/esc$i.wav" < "esc$i.txt"
done
```

Regenerar la música y copiar los wavs a `public/` (ambos comandos desde `video/`, que es el cwd del que parte `make_music.py` para escribir `public/music.wav`):

```sh
python3 narracion/make_music.py        # escribe public/music.wav (180 s exactos, semilla fija: reproducible)
cp narracion/esc{1..8}.wav public/narracion/
```

Comprobar duraciones antes de renderizar (la voz debe caber en su escena con ≥ 0,8 s de holgura):

```sh
for f in narracion/esc{1..8}.wav; do ffprobe -v error -show_entries format=duration -of csv=p=0 "$f"; done
```

## Verificación del render final

Fecha: 2026-09-20 (render **sin audio**, previo a la integración de voz + música de esta rama; los stills y medidas de vídeo siguen siendo válidos). Render completo con el código vigente en la rama
`feat/remotion-polish` (incluye el pulido de escenas de esta rama).

Comando exacto (desde `video/`):

```sh
npx remotion render src/index.tsx filemaid out/filemaid.mp4
```

Medidas (ffprobe de `node_modules/@remotion/compositor-linux-x64-gnu/`):

- Duración: **180,000000 s exactos** (5400 frames).
- Resolución / fps: **1920×1080 @ 30 fps** (avg_frame_rate 30/1).
- Tamaño: **8 603 731 bytes (~8,2 MB)**, < 20 MB.
- sha256: `1c8fcf371d7dfc579e6b489638722704865bbefce6683ac7c00e09c9a873e4d3`.

Stills de verificación en `out/verify-escena{1..8}.png`, generados con
`npx remotion still` 60 frames después del inicio de cada escena
(frames 60 / 420 / 1110 / 1710 / 2610 / 3660 / 4260 / 4860), con las
animaciones ya asentadas. Inspección visual frame a frame:

| Escena | Still | Verificado |
|---|---|---|
| 1 · Portada | `verify-escena1.png` | FILEMAID + chips FACTURA/DECISIÓN/TRAZA, sin solapes |
| 2 · El problema | `verify-escena2.png` | 3 tarjetas (500/Excel/ERP 2009), badges PAGAR teal, NO_PAGAR rojo, ESCALAR naranja |
| 3 · Producto | `verify-escena3.png` | 5 filas de features + screenshot dashboard, sin solapes |
| 4 · Escalera | `verify-escena4.png` | Escalones con latencias medidas (rung1 < 1 ms → VLM local ~1,7 s) |
| 5 · Trazabilidad | `verify-escena5.png` + `verify-escena5b.png` (frame 2700) | Los 8 rule codes visibles en las 3 columnas; NO_PAGAR rojo, ESCALAR naranja |
| 6 · ADRs | `verify-escena6.png` | Motor determinista + ADR-06 con 86 corregidos / 0 regresiones |
| 7 · Resiliencia | `verify-escena7.png` | Drills PASS (provider-caído, backoff-429, crash-reanudación); ledger-corrupto entra con el stagger posterior |
| 8 · Escala | `verify-escena8.png` | 120,1 s ≈ 4,162 files/s, 0,00 € cloud medido |

Nota sobre la escena 5: en el frame 2610 los rule codes aún están entrando
(delay escalonado `40 + i*8 + j*4` desde el inicio de la escena); en el frame
2700 (`verify-escena5b.png`) los 8 códigos de RULE_CODES están asentados en
las tres columnas. Animación viva confirmada comparando ambos frames.

## Cómo se verificó

1. **ffprobe del MP4 final** (binario incluido en
   `node_modules/@remotion/compositor-linux-x64-gnu/`): duración
   180,000000 s, 1920×1080, avg_frame_rate 30/1.
2. **sha256 + tamaño**: `sha256sum out/filemaid.mp4` y `stat -c %s`
   sobre el MP4 renderizado con el código vigente.
3. **Stills por escena**: `npx remotion still` en los frames 60 / 420 /
   1110 / 1710 / 2610 / 3660 / 4260 / 4860 (60 frames tras el inicio de
   cada escena, animaciones asentadas) → `out/verify-escena{1..8}.png`,
   más `out/verify-escena5b.png` (frame 2700) para la escena de
   trazabilidad con los 8 rule codes ya entrados. Inspección visual de
   cada still: sin solapes, colores de badge correctos, datos idénticos
   a los ficheros `data_*.json`.
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
