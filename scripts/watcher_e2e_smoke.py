"""Prueba E2E del watcher: ciclo completo en directorio bajo /home/deploy.

Ciclo verificado: PDF aparece en la carpeta vigilada -> estabilidad -> ingesta
(cola real de filemaid.ingest) -> decisión ESCALAR -> notificación al escalado
(notificador Qt offscreen). Dedup: un segundo ciclo con el mismo PDF no reentrega.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path("/home/deploy/hackspain26")
sys.path.insert(0, str(REPO / "src"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("FILEMAID_MASTER", str(REPO / "master"))

from filemaid.desktop.notify import Notificador
from filemaid.desktop.watcher import NOTIFIED_ID, SETTINGS_ID, Watcher
from filemaid.store.pouch import PouchStore

BASE = Path("/home/deploy/hackspain26/.local-informes/e2e-watcher-smoke")
PDF_REAL = REPO / "caja-de-alberto" / "facturas" / "2026-07-09_P010.pdf"


def esperar(cond, segundos: float, desc: str) -> None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError(f"tiempo agotado: {desc}")


class Cfg:
    """AppConfig mínimo: el watcher solo usa cfg.root."""

    def __init__(self, root: Path) -> None:
        self.root = root


def main() -> int:
    if BASE.exists():
        shutil.rmtree(BASE)
    BASE.mkdir(parents=True)
    carpeta = BASE / "facturas"
    carpeta.mkdir()

    store = PouchStore(BASE / "data")
    store.local_put(
        SETTINGS_ID, {"folder": str(carpeta.resolve()), "enabled": True}
    )
    notificador = Notificador()
    notificador.preparar()
    assert notificador.estado()["available"], (
        f"notificador no disponible: {notificador.estado()['detail']}"
    )
    watcher = Watcher(
        Cfg(BASE / "data"),
        notificador,
        poll_s=0.2,
        settle_polls=2,
        reconcile_s=60.0,
    )
    watcher.start()
    try:
        # Fase 1: PDF parcial (copia en curso) -> no se entrega.
        destino = carpeta / "factura.pdf"
        datos = PDF_REAL.read_bytes()
        with destino.open("wb") as f:
            f.write(datos[: len(datos) // 2])
        time.sleep(0.6)
        st = watcher.estado()
        assert st["processed"] == 0, f"parcial entregado: {st}"

        # Fase 2: PDF completo y estable -> ingesta real -> ESCALAR -> notificación.
        destino.write_bytes(datos)
        esperar(
            lambda: len(store.list("decision:")) >= 1, 60.0,
            "el pipeline no produjo ninguna decisión",
        )
        esperar(
            lambda: NOTIFIED_ID in [d.get("_id") for d in [store.local_get(NOTIFIED_ID)] if d],
            30.0,
            "no se registró procedencia de notificación",
        )
        st = watcher.estado()
        assert st["processed"] == 1, f"procesadas != 1: {st}"
        assert st["pending"] == 0, f"pendientes != 0: {st}"
        decisiones = store.list("decision:")
        resultados = {d.get("result") for d in decisiones}
        assert "ESCALAR" in resultados, f"resultados: {resultados}"
        decision = next(d for d in decisiones if d.get("result") == "ESCALAR")
        assert store.local_get(NOTIFIED_ID).get(decision["_id"]), (
            f"procedencia no registrada para {decision['_id']}"
        )
        print(f"[ok] ESCALAR notificada: decision_id={decision['_id']}")

        # Fase 3: dedup — el mismo fichero no se reentrega.
        processed_antes = watcher.estado()["processed"]
        destino.write_bytes(datos)  # mismo contenido, mtime cambia
        time.sleep(1.0)
        assert watcher.estado()["processed"] == processed_antes, "dedup falló"
        print("[ok] dedup: el mismo PDF no se reentrega")
    finally:
        watcher.stop()
    assert watcher.estado()["running"] is False, "el hilo no paró limpio"
    print("[ok] stop limpio del hilo de sondeo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
