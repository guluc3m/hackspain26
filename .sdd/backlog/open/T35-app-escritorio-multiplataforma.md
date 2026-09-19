# T35 · App de escritorio multiplataforma (Windows/Mac/Linux) para Alberto
assignee: W2
priority: p1

## Requisito del usuario
El proyecto debe funcionar también en Windows y Mac, con mejor integración que
"te abre un navegador" — algo tipo app Electron "O SIMILAR, seguramente haya
una opción mejor".

## Decisión de enfoque (ADR en el informe — nuevo ADR-06/D-06)
- **Electron descartado con argumento**: runtime de ~200 MB, toolchain Node
  adicional, y NO se pueden compilar/firmar .app/.exe de macOS/Windows desde
  Linux (la máquina de build debe ser el OS destino). Para una demo de
  hackathon el coste no compensa.
- **Elegido: `pywebview`** (Python puro, ya nuestro stack): ventana nativa con
  el webview del OS (WebKit en Mac, WebView2/Edge en Windows, GTK en Linux),
  sin navegador, sin Node. `src/albertitos/desktop.py`:
  `uv run python -m albertitos.desktop` → arranca uvicorn en un hilo (puerto
  efímero o 8000), espera /health, y abre `webview.create_window` apuntando a
  la UI. Cerrar la ventana ⇒ apaga el servidor limpio.
- **Fallback PWA**: manifest + service worker en la UI — desde el navegador
  "Instalar aplicación" da lo mismo sin nada extra.
- **Launchers por OS**: `iniciar.sh` (Linux/Mac), `iniciar.command` (macOS
  doble-clic), `iniciar.bat` + `iniciar.ps1` (Windows) — todos llaman lo mismo
  e imprimen la URL si el webview no está disponible.
- **Límite honesto (etiquétalo en el informe)**: un instalador .exe/.dmg
  firmado requiere una máquina por OS; desde Linux entregamos fuente +
  arranque de un paso, suficiente para la defensa.

## Criterios de aceptación
- `uv run python -m albertitos.desktop` abre la ventana con la UI real (en
  Linux con GTK webkit; si el paquete del webview falta, fallback automático
  al navegador con aviso claro en español).
- pywebview añadido a pyproject con justificación; tests del bootstrap: el
  servidor en hilo responde /health y se apaga limpio (sin webview en CI).
- iniciar.sh/.bat/.command presentes e idempotentes; pytest+ruff verde;
  ticket a closed en el mismo commit.
