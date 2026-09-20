# SPEC — Refinamiento narrativo del vídeo (CONTRATO entre agentes)

Fuente de verdad narrativa: `video/narracion/guion_tts.md` (textos YA grabados en
`video/narracion/esc{1..8}.wav`, duraciones abajo). NO reescribir los textos.

## Duraciones y colocación de voz (scene start → delay de entrada)

| # | Escena | Frames | Dur s | Voz dur s | Voz empieza (frame local) |
|---|--------|--------|-------|-----------|---------------------------|
| 1 | portada     | 360  | 12 | 9,72  | 30  |
| 2 | problema    | 690  | 23 | 21,02 | 30  |
| 3 | producto    | 600  | 20 | 17,37 | 36  |
| 4 | escalera    | 900  | 30 | 24,41 | 60  |
| 5 | traza       | 1050 | 35 | 27,48 | 75  |
| 6 | adrs        | 600  | 20 | 15,98 | 45  |
| 7 | resiliencia | 600  | 20 | 17,35 | 30  |
| 8 | escala      | 600  | 20 | 17,70 | 30  |

`SCENES` en `src/scenes.ts` NO cambia (5400 frames exactos). Los wavs se sirven con
`staticFile('narracion/escN.wav')` → deben copiarse a `video/public/narracion/escN.wav`.

## Contrato técnico (intocable)

- Paleta `C` de scenes.ts; sin gradientes; radius 0–2px; bordes 1–2px tinta.
- Máx 5 bullets visibles; animaciones `fade`/`rise`/`spring` existentes; stagger vivo.
- Datos SOLO de METRICS/ESCALERA/DRILLS/REGLAS/CASO_* (nada inventado).
- `Escena`/`SectionKicker`/`Frame` siguen usándose; índices idx=0..7 intactos.
- Compilable: `npx tsc --noEmit` desde `video/` sin errores.
- Salida visual sigue 1920×1080@30fps, 5400 frames.

## Narrativa por escena: PROBLEMA → SOLUCIÓN → BENEFICIO/CAVEAT (menos jerga)

Cada escena se estructura en 3 tiempos visuales sincronizados con la voz
(reparto de frames local orientativo: P ≈ 25%, S ≈ 45%, B/C ≈ 30%).
Kicker nuevo: subtítulo humano, no técnico. El texto EN PANTALLA se acorta:
la voz narra; la pantalla muestra lo esencial (la voz es quien cuenta).

1. **Portada** — Hook. P: «500 facturas al mes» (número gigante animado).
   S: filemaid lee, comprueba y decide. B: «y siempre enseña la prueba».
   Mantener FILEMAID + chips.
2. **El problema de Alberto** — P: decidir parece fácil (chip PAGAR/NO_PAGAR/ESCALAR).
   S (caveats de las 2 alternativas ingenuas, dos tarjetas tachadas con tono entretenido):
   «LLM: lento y a veces inventa» · «OCR clásico: se rinde con un escaneo malo».
   B/C: la norma «ante duda razonable, escalar antes que pagar» + tarjeta
   «lo que Alberto necesita: precisión · rapidez · prueba».
3. **El producto** — P: «¿y quién hace el trabajo nocturno?». S: los 5 pasos del
   flujo (mantener lista) + captura rotando. B/C: «tú solo miras cuando algo
   huele raro» (notificación). Sin recargar: la voz lleva el detalle.
4. **La escalera de confianza** — P: «una página difícil ¿quién la lee?».
   S: los 7 escalones (mantener tabla, simplificar cabeceras: QUÉ/COSTE).
   B/C: «94 % se resuelve gratis y al instante» (métrica destacada) +
   caveat «y si un escalón falla, degrada con calma: el lote nunca se para».
5. **Trazabilidad** — P: «¿por qué NO se paga esta?». S: 3 casos reales
   (mantener columnas y reglas). B: «todo se puede auditar: nada se inventa»
   (chips de evidencia). Menos siglas en pantalla; la voz explica.
6. **Reglas deterministas / ADRs** — P: «una IA que decide distinto cada vez no
   es pagable». S: motor puro, misma entrada ⇒ misma salida byte a byte.
   B/C: ADR-06 (86 falsos NO_PAGAR corregidos, 0 regresiones) + «8 decisiones
   escritas (ADRs)»; caveat: la política FAIL→NO_PAGAR/ESCALAR es dato, no código.
7. **Resiliencia** — P: «¿y si algo cae a mitad del lote?». S: 4 drills PASS.
   B/C: «reanudar nunca duplica ni re-factura» + lema «caerse no es opción:
   degradar».
8. **Escala y coste** — P: «¿cuánto cuesta?». S: la fórmula con números (tabla).
   B: «500 facturas en 2 min · 0,00 € cloud». Caveat/plan: más volumen =
   concurrencia; nuevo formato = 1 extractor. Cierre: «Alberto duerme. Y paga
   lo justo.» (línea final grande).

## Audio

- Voz: `<Audio src={staticFile('narracion/escN.wav')} />` dentro del `Sequence`
  de cada escena (o `<Sequence from={sceneStart + delay}>`), volumen 1.0.
- Música: `video/public/music.wav` (180 s, la genera el worker B), volumen
  ≈ 0.10–0.14, loop no necesario (dura exacto). Suave: pad ambiente, sin ritmo
  marcado que compita con la voz.
- El render final debe llevar audio integrado (Remotion lo hace con <Audio>).

## Entregables por agente

- **Worker A** (código): FilemaidVideo.tsx reescrito con la narrativa de este
  spec + etiquetas `<Audio>` de voz y música. scenes.ts solo comentarios si algo.
- **Worker B** (audio): copiar wavs a `video/public/narracion/`; generar
  `video/public/music.wav` (script `video/narracion/make_music.py`, stdlib only);
  verificar duraciones con ffprobe/wave.
- **Worker C** (docs): reescribir `video/GUION.md` (nueva estructura P→S→B/C,
  colocación de voz, tabla de duraciones) y la sección de audio de `video/README.md`.
