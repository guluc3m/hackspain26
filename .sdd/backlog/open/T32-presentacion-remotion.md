# T32 · Presentación Remotion: "qué hicimos y por qué" (estilo Typst)
assignee: W2
priority: p2

## Objetivo
Vídeo presentacional (Remotion, mp4) que explica el proyecto: qué construimos,
por qué cada decisión, resultados medidos. Estética HEREDADA de la plantilla
Typst del informe (docs/report/): mismas fuentes (Bungee + DM Sans en
docs/report/fonts/), misma paleta y lenguaje visual (chips, tarjetas, acentos).

## Contenido (cada cifra desde .sdd/metrics/, nunca hardcodeada sin fuente)
1. Portada: título + chips (FACTURA · DECISIÓN · TRAZA), estilo portada del PDF.
2. El problema: 500 facturas, 3 resultados, normas de pago, Alberto.
3. Arquitectura: la escalera por página (471 texto usable / 29 raster / 0 QR,
   rung 4 serializado, rung 5 deepseek) — diagrama animado.
4. Decisiones (ADRs): reglas-como-datos v3→v4, no-LLM-en-la-decisión,
   revisión humana no bloqueante, colapso de candidatos con provenance (87/108
   falsos medidos → fix), ERP fuera de scope con costura.
5. Números: files/s medidos, latencias p50/p95 por rung, coste (0.00 € cloud
   lote 1), drills 4/4 PASS, validador 500/500 verde, distribución final
   (433/22/45).
6. Trazabilidad: un ejemplo real end-to-end (file_id → ledger → evidencia →
   reglas → resultado) como secuencia.
7. Cierre: entrega (2 JSONL + plan) y el bonus (escalados priorizados por €).

## Cómo
- npm NO está instalado: node v26 sí (~/.local/bin). Instala npm vía el
  tarball oficial de Node (incluye npm/npx) en ~/.local/ o usa corepack si
  existe. Sin root.
- `npx create-video@latest` (template blank/TS) en `presentation/` dentro de
  la solución; render headless: `npx remotion render src/index.ts <Comp> out.mp4`
  (Chromium headless se descarga solo). PONLO BONITO PERO SIMPLE: menos es más
  — transiciones limpias, tipografía grande, datos en tarjetas.
- El mp4 final NO se commitea (añádelo al .gitignore local); va aparte, junto a
  los entregables si el usuario quiere incluirlo en la defensa.
- Presupuesto de tiempo: 60-90 s a ~30 fps, 1920x1080.

## Criterios de aceptación
- `presentation/` compila y renderiza un mp4 ≥45 s con las 7 secciones.
- Las fuentes Bungee/DM Sans cargan (localFont o @font-face desde docs/report/fonts).
- Datos dinámicos: las cifras se leen de un JSON generado por el mismo flujo
  que alimenta el informe (no duplicar hardcodeo).
- pytest+ruff sigue verde (Remotion no toca el paquete Python); ticket a closed
  en el mismo commit.
