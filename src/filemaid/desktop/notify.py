"""Notificaciones nativas de escritorio (Qt) con sonda de capacidad honesta.

La bandeja del sistema debe vivir en el hilo de la GUI. `preparar()` se llama en
el hilo principal (antes de `webview.start()`), donde se crea el objeto Qt con
afinidad a ese hilo; `notificar()` es seguro desde cualquier hilo: encola el
mensaje y lo entrega al hilo de la GUI mediante una conexión en cola.

Si Qt o la bandeja del sistema no están disponibles, `disponible` es False y
`notificar()` devuelve False sin hacer nada: quien llama debe mostrar un error
en la interfaz, nunca afirmar que la notificación se entregó.
"""

from __future__ import annotations

import logging
import queue
import threading

log = logging.getLogger(__name__)

# Espera máxima a que el hilo de la GUI confirme el intento de entrega.
_ESPERA_S = 3.0


class Notificador:
    """Bandeja Qt con entrega real; sin bandeja, degrada de forma explícita."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._puente = None
        self._disponible = False
        self._detalle = "notificador no preparado"

    def preparar(self) -> None:
        """Crea el objeto Qt y lo fija al hilo de la GUI (idempotente).

        Puede llamarse antes de `webview.start()` (hilo principal, que será el
        de la GUI) o desde el evento `loaded` de pywebview, que NO corre en el
        hilo de la GUI: en ese caso el objeto se mueve al hilo de la GUI para
        que la bandeja se cree allí.
        """
        with self._lock:
            if self._puente is not None:
                return
            try:
                from qtpy.QtCore import QMetaObject, QObject, Qt, QThread, Slot
                from qtpy.QtGui import QColor, QIcon, QPixmap
                from qtpy.QtWidgets import QApplication, QSystemTrayIcon
            except ImportError as exc:
                self._detalle = f"Qt no disponible: {exc}"
                return

            notificador = self

            class _Puente(QObject):
                def __init__(self) -> None:
                    super().__init__()
                    self._cola: queue.Queue = queue.Queue()
                    self._bandeja = None
                    self._probado = False

                def _asegurar(self) -> None:
                    if self._probado:
                        return
                    self._probado = True
                    if not QSystemTrayIcon.isSystemTrayAvailable():
                        notificador._marcar(
                            False, "el escritorio no ofrece bandeja de notificaciones"
                        )
                        return
                    pixmap = QPixmap(16, 16)
                    pixmap.fill(QColor("#2d6a4f"))
                    bandeja = QSystemTrayIcon(QIcon(pixmap))
                    bandeja.setToolTip("filemaid")
                    bandeja.show()
                    self._bandeja = bandeja
                    notificador._marcar(True, "bandeja del sistema disponible")

                @Slot()
                def procesar(self) -> None:
                    self._asegurar()
                    while True:
                        try:
                            titulo, cuerpo, evento, resultado = self._cola.get_nowait()
                        except queue.Empty:
                            break
                        if self._bandeja is None:
                            resultado["ok"] = False
                        else:
                            self._bandeja.showMessage(
                                titulo, cuerpo, QSystemTrayIcon.Information, 10000
                            )
                            resultado["ok"] = True
                        evento.set()

                def probar(self) -> None:
                    QMetaObject.invokeMethod(self, "procesar", Qt.QueuedConnection)

                def encolar(self, titulo: str, cuerpo: str) -> bool:
                    evento = threading.Event()
                    resultado: dict = {}
                    self._cola.put((titulo, cuerpo, evento, resultado))
                    QMetaObject.invokeMethod(self, "procesar", Qt.QueuedConnection)
                    if not evento.wait(_ESPERA_S):
                        return False
                    return bool(resultado.get("ok"))

            self._puente = _Puente()
            app = QApplication.instance()
            if app is not None and QThread.currentThread() is not app.thread():
                # `loaded` de pywebview corre en un hilo propio: el objeto debe
                # vivir en el hilo de la GUI para crear allí la bandeja.
                self._puente.moveToThread(app.thread())
            self._detalle = "notificador preparado; bandeja pendiente del hilo de la GUI"

    def probar(self) -> None:
        """Fuerza la sonda de capacidad en el hilo de la GUI (no bloquea)."""
        with self._lock:
            puente = self._puente
        if puente is None:
            return
        try:
            puente.probar()
        except Exception:
            log.exception("no se pudo sondear la bandeja del sistema")

    def notificar(self, titulo: str, cuerpo: str) -> bool:
        """Intenta una notificación nativa; True solo si el SO la aceptó."""
        with self._lock:
            puente = self._puente
        if puente is None:
            return False
        try:
            return puente.encolar(titulo, cuerpo)
        except Exception:
            log.exception("no se pudo emitir la notificación nativa")
            return False

    def estado(self) -> dict:
        with self._lock:
            return {"available": self._disponible, "detail": self._detalle}

    def _marcar(self, disponible: bool, detalle: str) -> None:
        with self._lock:
            self._disponible = disponible
            self._detalle = detalle
