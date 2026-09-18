"""T5 — UI de operaciones: las 5 pantallas responden 200 con datos sembrados.

Los tests inyectan los registros (fixture del store) en memoria; además se
prueba el lector de ledger sobre ficheros reales dentro de `.sdd/` (estado de
trabajo nunca en /tmp).
"""

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from albertitos.ui.app import create_app
from albertitos.ui.demo import demo_records
from albertitos.ui.ledger import build_view, load_ledger


def cliente() -> TestClient:
    return TestClient(create_app(records=demo_records()))


# ------------------------------------------------------------- las 5 pantallas


def test_operaciones_responde_200():
    r = cliente().get("/")
    assert r.status_code == 200
    assert "Operaciones" in r.text
    assert "medido" in r.text  # todo número lleva su etiqueta
    assert "v4" in r.text  # versión de reglas activa


def test_facturas_responde_200():
    r = cliente().get("/facturas")
    assert r.status_code == 200
    # file_id EXACTO, nunca normalizado
    assert "2026-05-28_P005.pdf" in r.text
    assert "factura_8801.pdf" in r.text
    assert "NO_DOUBLE_PAYMENT" in r.text  # códigos de regla visibles


def test_detalle_factura_responde_200():
    r = cliente().get("/facturas/INV-0002")
    assert r.status_code == 200
    assert "factura_8801.pdf" in r.text
    assert "pypdf" in r.text  # cadena de evidencia
    assert "latency" not in r.text  # sin inglés técnico


def test_detalle_factura_inexistente_404():
    assert cliente().get("/facturas/NO-EXISTE").status_code == 404


def test_revision_responde_200():
    r = cliente().get("/revision")
    assert r.status_code == 200
    assert "escan_ilegible_07.pdf" in r.text
    assert "data:image/png;base64," in r.text  # imagen de página junto a candidatas
    assert "los extractores discrepan" in r.text  # desacuerdo resaltado


def test_reglas_responde_200():
    r = cliente().get("/reglas")
    assert r.status_code == 200
    assert "v4" in r.text
    assert "TOTALS_MUST_MATCH" in r.text


def test_salud_responde_200():
    r = cliente().get("/salud")
    assert r.status_code == 200
    assert "cloud_vlm" in r.text  # fallo de proveedor visible
    assert "degradado" in r.text


# ------------------------------------------------------------------ interacción


def test_what_if_cambia_umbral():
    c = cliente()
    r = c.get("/reglas", params={"codigo": "TOTALS_MUST_MATCH", "nuevo_umbral": "0.3"})
    assert r.status_code == 200
    # INV-0004 tiene confianza 0.51 < 0.8; con umbral 0.3 pasaría a PASS
    assert "escan_ilegible_07.pdf" in r.text
    assert "Pasaría a" in r.text


def test_override_se_encola_con_provenance():
    c = cliente()
    r = c.post(
        "/revision/INV-0004/resolver",
        data={"file_id": "escan_ilegible_07.pdf", "campo": "total", "valor": "1210.00", "nota": "visto en imagen"},
    )
    assert r.status_code == 200  # TestClient sigue la redirección 303 hasta /revision
    assert "1210.00" in r.text
    assert "Correcciones guardadas" in r.text
    assert "visto en imagen" in r.text  # provenance visible


def test_override_sin_store_dir_no_escribe_disco(tmp_path: Path):
    """Sin override_dir los overrides viven en memoria: la UI jamás toca el store."""
    app = create_app(records=demo_records())
    assert app.state.override_dir is None
    r = TestClient(app).post(
        "/revision/INV-0005/resolver",
        data={"file_id": "factura_outlier_44.pdf", "campo": "total", "valor": "121.0"},
    )
    assert r.status_code == 200  # redirección 303 seguida hasta /revision


# ------------------------------------------------------------- lectura del ledger


def test_lector_ledger_sobre_ficheros():
    """El lector lee *.jsonl reales desde .sdd/ (jamás /tmp) y es tolerante."""
    destino = Path(".sdd") / "pytest-tmp" / "ledger-ui"
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    try:
        (destino / "decisiones.jsonl").write_text(
            '{"kind": "decision", "invoice_id": "X1", "file_id": "a.pdf",'
            ' "result": "PAGAR", "rule_verdicts": [], "config_snapshot": {}}\n'
            "linea corrupta que se ignora\n",
            encoding="utf-8",
        )
        vista = build_view(load_ledger(destino))
        assert len(vista.decisions) == 1
        assert vista.decisions[0].file_id == "a.pdf"
    finally:
        shutil.rmtree(destino.parent)


def test_demo_cuando_ledger_vacio():
    """Sin datos: la app sirve datos de prueba marcados como tales."""
    app = create_app(store_dir=Path(".sdd/pytest-tmp/ledger-inexistente"))
    assert app.state.demo is True
    r = TestClient(app).get("/")
    assert "datos de prueba" in r.text


def test_pantallas_sin_datos_no_explotan():
    app = create_app(records=[{"kind": "decision", "invoice_id": "Z", "file_id": "z.pdf", "result": "ESCALAR", "rule_verdicts": [], "config_snapshot": {}}])
    c = TestClient(app)
    for ruta in ("/", "/facturas", "/revision", "/reglas", "/salud"):
        assert c.get(ruta).status_code == 200, ruta
