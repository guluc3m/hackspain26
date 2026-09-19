"""T36 — capturas reales de la UI para el anuncio (pantallas y degradación)."""

from albertitos.capturas import DESTINO_DEFECTO, pantallas


def test_pantallas_cubre_las_cinco_rutas_de_la_app():
    base = "http://127.0.0.1:8000"
    pant = pantallas(base)
    nombres = [n for n, _ in pant]
    assert set(nombres) == {"facturas", "revision", "reglas", "salud",
                            "operaciones"}
    for n, u in pant:
        assert u.startswith(base)
    # facturas llega filtrada (anuncio: el resultado visible)
    assert any("result=ESCALAR" in u for _, u in pant)


def test_destino_es_presentation_public_capturas():
    assert str(DESTINO_DEFECTO) == "presentation/public/capturas"
