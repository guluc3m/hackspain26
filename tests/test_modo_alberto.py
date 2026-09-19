"""T34 — Modo Alberto: arranque de un paso + UI sin jerga sin traducir.

- iniciar.sh: sintaxis, arranque real en un puerto de prueba e idempotencia
  (segunda llamada no rompe ni duplica servidor).
- UI: sin jerga sin traducir en el flujo principal (los términos técnicos
  solo dentro de tooltips `title=`), Ayuda/glosario, confirmaciones.
"""

import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from conftest import lote1_estado_real_presente

REPO = Path(__file__).parent.parent
PUERTO_TEST = 8143


def _sin_tooltips(html: str) -> str:
    """Quita los atributos title= (los tooltips guardan el detalle técnico)."""
    return re.sub(r'title="[^"]*"', "", html)


@pytest.fixture(scope="module")
def servidor():
    env = {**dict(__import__("os").environ), "PUERTO": str(PUERTO_TEST)}
    proceso = subprocess.run(
        ["bash", "iniciar.sh"], cwd=REPO, env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    yield proceso
    # mata AMBOS modos de arranque (uvicorn clásico y escritorio pywebview):
    # el pkill de solo "uvicorn albertitos.ui.app" dejaba vivo un servidor
    # escritorio viejo en el mismo puerto → el test servía estado rancio.
    subprocess.run(["pkill", "-f", "uvicorn albertitos.ui.app"], capture_output=True, check=False)
    subprocess.run(["pkill", "-f", "albertitos.desktop"], capture_output=True, check=False)
    time.sleep(1.0)
    # la cadena/anotaciones del test no ensucian la telemetría real
    shutil.rmtree(Path(REPO / ".sdd/telemetria"), ignore_errors=True)


def test_iniciar_sh_arranca_y_es_idempotente(servidor):
    assert proceso_ok(), "la UI no quedó sirviendo tras iniciar.sh"
    assert "Listo. Mira tu navegador" in servidor.stdout
    assert f"http://localhost:{PUERTO_TEST}" in servidor.stdout
    # idempotente: segunda llamada no arranca de nuevo y no rompe
    env = {**dict(__import__("os").environ), "PUERTO": str(PUERTO_TEST)}
    de_nuevo = subprocess.run(
        ["bash", "iniciar.sh"], cwd=REPO, env=env, capture_output=True, text=True, timeout=60, check=False,
    )
    assert de_nuevo.returncode == 0
    assert "ya está encendido" in de_nuevo.stdout
    # y sigue sirviendo (una sola instancia)
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO_TEST}/salud") as r:
        assert r.status == 200


def proceso_ok() -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO_TEST}/", timeout=5) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def test_pantallas_sin_jerga_sin_traducir(servidor):
    """El flujo principal no muestra términos técnicos crudos: solo en
    tooltips (title=) o pantallas técnicas de detalle."""
    import urllib.request

    for ruta in ("/", "/facturas", "/revision", "/reglas", "/salud", "/ayuda"):
        with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO_TEST}{ruta}", timeout=10) as r:
            cuerpo = _sin_tooltips(r.read().decode("utf-8"))
        # jerga prohibida sin traducir en el flujo principal:
        for termino in ("rung1", "rung2", "rung3", "rung4", "rung5", "WAL"):
            assert termino not in cuerpo, f"{ruta}: jerga cruda '{termino}' fuera de tooltips"
    # la Ayuda sí explica los términos técnicos (con su glosario)
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO_TEST}/ayuda", timeout=10) as r:
        ayuda = r.read().decode("utf-8")
    assert "glosario" in ayuda.lower()
    assert "PAGAR" in ayuda and "ESCALAR" in ayuda


def test_inicio_de_alberto_con_un_boton_por_accion(servidor):
    if not lote1_estado_real_presente():
        pytest.skip(
            "estado real del lote 1 ausente en este worktree (.sdd/lote1 "
            "gitignored — provisioning T40F4); el test corre completo donde existe"
        )
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO_TEST}/", timeout=10) as r:
        inicio = r.read().decode("utf-8")
    assert "Lo que te toca hoy" in inicio  # la operación de Alberto primero
    assert "Revisarlas" in inicio  # botón grande hacia Revisión
    # nada de rutas de archivo ni JSON en el flujo principal
    assert "outcomes.jsonl" not in inicio and ".sdd/store.db" not in inicio


def test_confirmaciones_con_consecuencias(servidor):
    if not lote1_estado_real_presente():
        pytest.skip(
            "estado real del lote 1 ausente en este worktree (.sdd/lote1 "
            "gitignored — provisioning T40F4); el test corre completo donde existe"
        )
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO_TEST}/revision", timeout=10) as r:
        revision = r.read().decode("utf-8")
    assert "confirm(" in revision  # diálogo de confirmación
    assert "recalculará" in revision  # lenguaje de consecuencias


def test_ayuda_en_la_ui(servidor):
    if not lote1_estado_real_presente():
        pytest.skip(
            "estado real del lote 1 ausente en este worktree (.sdd/lote1 "
            "gitignored — provisioning T40F4); el test corre completo donde existe"
        )
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO_TEST}/ayuda", timeout=10) as r:
        assert "Ayuda y glosario" in r.read().decode("utf-8")
