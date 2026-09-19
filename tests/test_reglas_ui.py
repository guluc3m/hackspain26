"""Regresión: TODA regla del motor tiene descripción llana y la UI la muestra
en hover (title) y en la página /reglas."""

from __future__ import annotations

import inspect
import re

from fastapi.testclient import TestClient

import albertitos.rules.engine as engine_mod
from albertitos.ui.app import DESCRIPCIONES_REGLAS, create_app


def _codigos_engine() -> set[str]:
    """Los códigos que el motor define con @rule("...") — la única fuente."""
    return set(re.findall(r'@rule\("([A-Z_0-9]+)"\)', inspect.getsource(engine_mod)))


def test_toda_regla_del_engine_tiene_descripcion():
    """Nada de códigos sin explicar: si añades una regla, añades su descripción."""
    codigos = _codigos_engine()
    assert codigos, "el motor debe definir reglas con @rule"
    faltan = codigos - set(DESCRIPCIONES_REGLAS)
    assert not faltan, f"reglas sin descripción en la UI: {sorted(faltan)}"
    assert all(d.strip() for d in DESCRIPCIONES_REGLAS.values())


def test_hover_y_explicacion_en_la_ui():
    """Los <code> de reglas llevan title= con la descripción y /reglas la lista."""
    with TestClient(create_app()) as c:
        html = c.get("/reglas").text
        assert "Qué significa cada regla" in html
        for cod, desc in list(DESCRIPCIONES_REGLAS.items())[:3]:
            assert cod in html
            assert desc in html
        # en facturas el código lleva tooltip
        fac = c.get("/facturas?result=ESCALAR").text
        assert "title=" in fac
