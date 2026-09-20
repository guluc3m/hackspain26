"""Cierre acotado de procesos hijos propios, en POSIX y Windows.

Al cerrar la app solo se termina lo que ella misma arrancó (el sidecar
llama.cpp, el ayudante de aprovisionamiento). Se actúa siempre sobre un handle
`Popen` propio, nunca sobre un PID descubierto por nombre, para no tocar
procesos ajenos ni servidores reutilizados de otra instancia.
"""

from __future__ import annotations

import os
import signal
import subprocess

DEFAULT_TIMEOUT = 5.0


def terminate_tree(proc: subprocess.Popen, timeout: float = DEFAULT_TIMEOUT) -> bool:
    """Termina `proc` y sus descendientes; True si salió dentro de `timeout`.

    Primero se pide el cierre (SIGTERM, o `taskkill /T` en Windows) y solo si no
    termina a tiempo se fuerza (SIGKILL). Nunca lanza: el cierre de la app no
    debe caerse porque un hijo ya hubiera muerto.
    """
    if proc.poll() is not None:
        return True
    _signal(proc, force=False)
    if _wait(proc, timeout):
        return True
    _signal(proc, force=True)
    return _wait(proc, timeout)


def _wait(proc: subprocess.Popen, timeout: float) -> bool:
    try:
        proc.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


def _signal(proc: subprocess.Popen, *, force: bool) -> None:
    if os.name == "nt":
        # En Windows no hay SIGTERM para procesos de consola: `taskkill /F /T`
        # es la única forma fiable de terminar el árbol completo.
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    sig = signal.SIGKILL if force else signal.SIGTERM
    pgid = _own_group(proc)
    if pgid is not None:
        try:
            os.killpg(pgid, sig)
            return
        except OSError:
            pass
    try:
        proc.send_signal(sig)
    except OSError:
        pass


def _own_group(proc: subprocess.Popen) -> int | None:
    """PGID del hijo si lidera su propio grupo; None en cualquier otro caso.

    Solo se señala un grupo que el hijo lidera (`start_new_session=True`):
    señalar un grupo heredado podría alcanzar procesos ajenos, y señalar el
    grupo propio mataría a este proceso.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except OSError:
        return None
    return pgid if pgid == proc.pid else None
