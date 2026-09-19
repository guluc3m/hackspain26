"""T32 — feed de datos de la presentación Remotion desde .sdd/metrics/.

El JSON nunca se hardcodea: se genera desde la misma evidencia que alimenta
el informe (metrics.json, lote1.json, corpus-dryrun.json, drills.json,
impacto-fix-colapso.json) y cada cifra lleva su etiqueta.
"""

import json

import pytest

from conftest import lote1_estado_real_presente

SECCIONES = ("portada", "problema", "escalera", "decisiones", "numeros",
             "traza", "cierre")


def test_datos_seccionadas_y_etiquetadas(tmp_path):
    datos = json.loads(json.dumps(
        __import__("albertitos.presentacion", fromlist=["generar_datos"])
        .generar_datos(destino=tmp_path / "datos.json")))
    for s in SECCIONES:
        assert datos.get(s), f"falta la sección {s}"
    # cada métrica numérica lleva etiqueta medido/estimado/sin datos
    for m in (datos["problema"]["n_facturas"], datos["numeros"]["validador"]):
        assert m["etiqueta"] in ("medido", "estimado", "sin datos")


def test_determinismo_y_origen_medido(tmp_path):
    if not lote1_estado_real_presente():
        pytest.skip(
            "estado real del lote 1 ausente en este worktree (.sdd/lote1 "
            "gitignored — provisioning T40F4); el test corre completo donde existe"
        )
    a = json.dumps(__import__("albertitos.presentacion",
                              fromlist=["generar_datos"]).generar_datos(
        destino=tmp_path / "a.json"), sort_keys=True)
    b = json.dumps(__import__("albertitos.presentacion",
                              fromlist=["generar_datos"]).generar_datos(
        destino=tmp_path / "b.json"), sort_keys=True)
    assert a == b  # mismo feed ⇒ mismo JSON (determinista, sin timestamps)
    # las cifras provienen de la evidencia real del lote 1 (no inventadas)
    d = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))
    assert d["numeros"]["validador"]["valor"] == "500/500"
    assert str(d["escalera"]["texto_usable"]["valor"]) in (
        "471", str(d["escalera"]["texto_usable"]["valor"]))
    assert int(d["escalera"]["texto_usable"]["valor"]) == 471
    assert d["traza"]["disponible"] is True
    assert d["traza"]["resultado"] in ("PAGAR", "NO_PAGAR", "ESCALAR")


def test_destino_por_defecto_es_presentation_public():
    from albertitos.presentacion import DESTINO_DEFECTO

    assert str(DESTINO_DEFECTO) == "presentation/public/datos.json"
