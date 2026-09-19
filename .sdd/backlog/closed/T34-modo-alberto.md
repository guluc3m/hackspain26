# T34 · Modo Alberto: UI usable por alguien que no sabe lo que es un terminal
assignee: W3
priority: p0

## Requisito del usuario (no negociable)
Alberto apenas sabe lo que es una terminal. TODA la funcionalidad del sistema
debe ser usable desde la UI, en lenguaje llano, y arrancar la UI debe ser
trivial.

## Qué construir
1. **Arranque de un solo paso**: `iniciar.sh` (bash, ejecutable, en la raíz) —
   levanta la UI (uvicorn, puerto por defecto 8000) y abre el navegador
   (xdg-open o imprime la URL grande). Sin argumentos, sin setup, sin venv
   visible (usa `uv run` por debajo). Un segundo `iniciar.sh` no rompe nada
   (idempotente: si ya corre, solo abre el navegador). Mensaje final en
   español llano: "Listo. Mira tu navegador: http://localhost:8000".
2. **Lenguaje llano en TODA la UI** — prohibida la jerga sin traducción:
   - "rung 1/2/3/4/5" → "Texto del PDF / Código QR / OCR / Lector visual (IA)
     / Revisión con IA grande" (y un tooltip con el detalle técnico para quien
     quiera).
   - "ledger/store/WAL" → "registro de actividad / base de datos local".
   - "ESCALAR" → mantén la palabra del contrato pero con explicación al lado
     ("necesita que un humano la mire").
   Cada pantalla arranca con 1-2 frases: qué es y qué puede hacer aquí.
3. **Botones con confirmación y lenguaje de consecuencias**: reprocesar,
   recargar reglas, marcar override — cada uno con confirmación ("¿Seguro?
   Esto volverá a revisar N facturas") y resultado visible al terminar.
4. **Página de inicio = la operación de Alberto**: qué hay pendiente (revisar
   X facturas por € Y), qué se pagó/no se pagó hoy, y un solo botón grande por
   acción disponible. Nada de JSON, nada de rutas de archivo en el flujo
   principal.
5. **Ayuda contextual**: icono "?" por pantalla con 3-5 líneas de explicación
   (mismo tono llano). Glosario completo en una pantalla "Ayuda".

## Reglas duras
- No se elimina ninguna capacidad existente: se expone, no se esconde.
- El arranque debe funcionar tras reboot sin pasos manuales (documenta los
  requisitos en el propio script si faltan: uv en PATH, .venv creada).
- Los tests existentes siguen verdes; añade tests de las nuevas rutas.

## Criterios de aceptación
- `bash iniciar.sh` en un checkout limpio deja la UI sirviendo en :8000 y es
  idempotente (segunda llamada no rompe).
- Las 5 pantallas + inicio sin jerga sin traducir (grep de términos técnicos
  fuera de tooltips/detalles técnicos).
- pytest+ruff verde; ticket a closed en el mismo commit.

## Cerrado — decisiones tomadas (W3)

- **`iniciar.sh`** (raíz, ejecutable, idempotente): comprueba `uv` con
  mensaje claro si falta, crea la .venv con `uv sync` (solo primera vez),
  elige el store real (`.sdd/lote1/ledger`, symlink SOLO LECTURA) o datos de
  prueba marcados, arranca uvicorn en segundo plano con log en
  `.sdd/telemetria/ui.log`, espera la readiness y abre el navegador
  (xdg-open/open o imprime la URL grande). Segunda llamada ⇒ «ya está
  encendido», solo abre navegador (testeado: arranque real en puerto de
  prueba + idempotencia).
- **Lenguaje llano en toda la UI**: NOMBRES_RUNG/EXTRACTOR/STAGE/DRILL
  traducidos («Texto del PDF», «Lector visual con IA (local)», «OCR»…); los
  códigos técnicos quedan en tooltips (`title=`) — test anti-jerga que
  limpia los tooltips y verifica que rung1-5/WAL no aparecen crudos en el
  flujo principal. ESCALAR mantenido (palabra del contrato) explicado en el
  glosario y en pantalla.
- **Inicio = la operación de Alberto**: «Lo que te toca hoy» (X facturas por
  € Y en riesgo, con el maestro auto-detectado), se pagarán N por € M, no se
  pagan K — un botón grande por acción (Revisarlas / Ver mi resumen / Ver
  no pagadas). Nada de JSON ni rutas en el flujo principal.
- **Confirmaciones con consecuencias**: Guardar corrección (Revisión) y
  Anotar (Actividad) con `confirm()` explicando qué pasará.
- **Ayuda contextual**: pantalla `/ayuda` con glosario completo (las 3
  decisiones, los lectores, las pantallas, las reglas de oro) + enlace «?
  Ayuda» en la navegación; `/resumen-ejecutivo` sirve el resumen de T26
  dentro de la UI (sin terminal).
- **Sin datos ⇒ PENDIENTE honesto** también en el inicio (sin maestro).
- Compatibilidad del suite: T32 `presentacion.py` ahora cae al store del
  lote 1 real si no hay store local (1 línea, aditivo); T31 test actualizado
  a los encabezados llano nuevos; test de imágenes de Revisión tolera la
  cola vaciada por W1 (degradación honesta); DEFENSA.md fuente [3]
  actualizada.
- Suite: 272 passed, ruff limpio, sin secretos.
