"""Ventana nativa (pywebview) con la misma UI Vue.

La app (Python) aloja el front construido (frontend/dist) y expone a la UI un
puente (window.pywebview.api) capaz de llamar a los dos motores de la
arquitectura: engines.extraction y engines.decision.

Todas las llamadas a los motores están SIN DEFINIR: los métodos del puente
existen como superficie de contrato y propagan NotImplementedError. La UI
sigue consumiendo la referencia sintética (frontend/src/mock/data.ts, targets
*_syncth), así que la ventana funciona igual que el front en navegador.
"""

from __future__ import annotations

import os
from pathlib import Path

from filemaid.engines import DecisionEngine, ExtractionEngine


class Api:
    """Superficie expuesta a la UI: window.pywebview.api.

    ping es infraestructura del puente; extraer y decidir son las llamadas a
    los motores, aún sin definir.
    """

    def __init__(self) -> None:
        self.extraction = ExtractionEngine()
        self.decision = DecisionEngine()

    def ping(self) -> str:
        """Comprueba que el puente JS -> Python está vivo."""
        return "pong"

    def extraer(self, file_id: str) -> object:
        """PDF -> campos: llamada al motor de extracción (sin definir).

        La resolución de la ruta del PDF a partir del file_id se definirá
        junto con la llamada.
        """
        return self.extraction.extraer(file_id)

    def decidir(self, invoice_id: str) -> object:
        """Campos -> decisión: llamada al motor de decisión (sin definir).

        La carga de los campos almacenados para la factura se definirá junto
        con la llamada; los argumentos son provisionales.
        """
        # llamada sin definir: el motor lanza NotImplementedError
        return self.decision.decidir([], invoice_id, invoice_id)


def _dist_index() -> Path:
    """Índice del build de la UI (frontend/dist), relativo a este módulo."""
    return Path(__file__).resolve().parents[3] / "frontend" / "dist" / "index.html"


def ui_destino() -> str:
    """Qué carga la ventana: URL de dev (ALBERTITOS_UI_URL) o el build dist."""
    url = os.environ.get("ALBERTITOS_UI_URL", "")
    if url:
        return url
    dist = _dist_index()
    if dist.exists():
        return str(dist)
    raise SystemExit(
        "UI no construida: pnpm --dir frontend build_syncth "
        "(o ALBERTITOS_UI_URL=http://127.0.0.1:5173 con dev_syncth)"
    )


def main() -> int:
    try:
        import webview
    except ImportError:
        raise SystemExit("falta pywebview: uv sync --extra desktop")

    webview.create_window(
        "albertitos — decisión de facturas",
        ui_destino(),
        js_api=Api(),
        width=1280,
        height=860,
    )
    try:
        webview.start()
    except Exception as exc:
        # sin GTK/QT con extensiones Python en el sistema (p.ej. entorno sin
        # raíz), la ventana nativa no puede abrirse
        raise SystemExit(f"la ventana nativa no pudo arrancar: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
