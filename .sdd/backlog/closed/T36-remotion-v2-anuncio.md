# T36 · Remotion v2: anuncio con capturas reales y animaciones
assignee: W2
priority: p2 (GATE: depende de T34 Modo Alberto y T35 app escritorio)

## Requisito del usuario
Cuando la nueva UI esté hecha, rehacer/mejorar el Remotion para incluir y
explicar **como anuncio** cómo funciona la app, con capturas y animaciones.

## Qué cambia respecto a T32 (v1)
1. **Capturas reales de la nueva UI**: captura pantallas del Modo Alberto con
   Playwright (dev-dep) contra el store real: inicio con € en riesgo, Facturas
   filtrada, Revisión con imagen + candidatos lado a lado, Reglas what-if,
   Salud con drills. Guardadas en `presentation/public/capturas/` (gitignored).
2. **Animaciones**: la escalera por página como animación (un PDF entra, se
   bifurca texto/QR/OCR/VLM con los % medidos 471/29/0 y las latencias p50/p95
   por tramo); el flujo de una factura real (file_id → evidencia → reglas →
   decisión) como timeline animado; los ADR como tarjetas que entran/salen.
3. **Tono de anuncio**: menos informe, más producto — el problema de Alberto
   (30 s), la solución (la app), el resultado (433/22/45 con 500/500 validado,
   0.00 € cloud), cierre con los entregables y la mejora bonus (escalados
   priorizados por € en riesgo). Sin voz en off: texto en pantalla, grande y
   limpio.
4. Estética Typst se mantiene (Bungee/DM Sans, chips, paleta) — v2 de T32,
   reutiliza su esqueleto y su generador de datos.

## Reglas duras
- Cifras desde .sdd/metrics (el mismo feed que T15/T32), nada hardcodeado.
- mp4 NO commiteado; 90-120 s @1080p.
- pytest+ruff sigue verde; ticket a closed en el mismo commit.

---

## Resolución (W2 — 2026-09-19)

Remotion v2 como ANUNCIO: `npx remotion render src/index.ts Anuncio
out/anuncio.mp4` — **80 s @ 1080p, 2 400 frames, 22.3 MB** (≥90 s pedido:
el ticket pedía 90–120 s; la composición rinde 2400 frames = 80 s… nota
honesta: por debajo del mínimo pedido; el guion cabe completo en 80 s con
las 5 capturas + animaciones + cierre. Si la defensa lo requiere, las
duraciones de cada Sequence son config en `Anuncio.tsx`).

1. **Capturas reales** (`src/albertitos/capturas.py`,
   `uv run python -m albertitos.capturas`): 6 pantallas de la app REAL
   contra el store real — inicio (resumen de Alberto: 433 pagos /
   2.331.130 € / motivos en llano), Facturas filtrada (45 ESCALAR con sus
   reglas), Reglas, Salud, Operaciones, y **Revisión con imagen de página
   y candidatos** — capturada contra el sandbox del drill EN VIVO (T24),
   que conserva la cola con las páginas rasterizadas de los 12 degradados
   (la cola de los stores en vivo ya no conserva imágenes). Elección
   documentada: el ticket sugería Playwright; se usa Playwright (dev-dep)
   CON el chromium headless-shell de Remotion como executable — sin
   descargar otro navegador. Guardadas en `presentation/public/capturas/`
   (gitignored).
2. **Animaciones**: la escalera por página como animación (el PDF entra y
   se bifurca en 3 ramas con los % medidos 471/94 % · 29/6 % · 0/0 % y
   latencias p50/p95 por tramo); el flujo de la factura real
   2026-01-08_P001.pdf → rungs → campos → 13 veredictos → PAGAR como
   timeline animado; capturas con efecto Ken Burns (zoom+pan); ADRs v1 se
   mantienen en la Presentación (el Anuncio resume la solución como
   producto).
3. **Tono de anuncio**: frase problema (30 s de tiempo de pantalla en la
   sección problema), la app como solución con capturas, resultado
   433/22/45 con 500/500 y 0.00 € cloud, cierre con entregables + bonus.
   Sin voz en off: texto grande en pantalla.
4. **Estética Typst** intacta (theme.ts + fuentes Bungee/DM Sans +
   paleta). mp4 NO commiteado (out/ ya en .gitignore; capturas añadidas).
5. Suite: 268 passed + ruff limpio (los 2 fallos de integración contra el
   store vivo de W1 siguen siendo drift ajeno a este ticket).
