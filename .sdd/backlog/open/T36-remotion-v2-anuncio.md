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
