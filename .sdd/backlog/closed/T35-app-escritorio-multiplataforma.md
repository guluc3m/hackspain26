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

---

## Resolución (W2 — 2026-09-19)

Implementado, con el ADR en el informe (renumerado **ADR-07**: el ADR-06 que
asumía el ticket lo ocupó el fix de colapso de T18).

- **Electron descartado con argumento (ADR-07 en `albertitos_plan.typ`)**:
  runtime ~200 MB, toolchain Node extra y un .exe/.dmg firmado exige una
  máquina por OS (no compilable desde Linux). Elegido **pywebview**:
  ventana nativa del OS (WebKit/WebView2/GTK) sobre la MISMA UI FastAPI/HTMX,
  sin Node ni navegador. pywebview entra como extra opcional `desktop`
  (pyproject, con justificación inline): la base y los tests no lo necesitan.
- **`src/albertitos/desktop.py`** (`uv run python -m albertitos.desktop`):
  uvicorn en hilo daemon con puerto EFÍMERO (el puerto real se lee del socket
  de uvicorn — `config.port` queda en 0), espera a que la UI responda
  (20 s), abre la ventana nativa; cerrarla ⇒ apagado limpio
  (`should_exit`). Sin webview o si el init del webkit falla (p. ej. GTK sin
  webkit2gtk): aviso claro en español + navegador con la misma UI + Ctrl+C.
  El store lo decide ALBERTITOS_STORE (contrato T5).
- **Launchers idempotentes de un paso**: `iniciar.sh` (Linux/Mac),
  `iniciar.command` (macOS doble-clic), `iniciar.bat` + `iniciar.ps1`
  (Windows) — los cuatro verifican uv e imprimen/abren la URL.
- **Tests** (tests/test_desktop.py, 6): servidor en hilo responde 200 y se
  apaga limpio; ALBERTITOS_STORE honrado; degradación a navegador SIN
  pywebview (monkeypatch del import) y con webview pero init del webkit
  roto (RuntimeError ⇒ False, nunca excepción); ventana sana bloquea y
  devuelve True; launchers presentes y ejecutables.
- **PDF recompilado** localmente para validar el typst (rc=0; el PDF no se
  commitea — solo el .typ).
- Suite: 266 passed + ruff limpio. Nota honesta: 2 tests de integración
  ajenos a este ticket fallan por drift del store vivo de W1
  (`.sdd/lote1/review-queue/review.jsonl` ya no existe en su lado) —
  preexistentes, fuera de mi dominio; en solitario mis ficheros están 100 %
  verdes.
