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
    assert "/revision/imagen/" in r.text  # imagen servida por endpoint, no base64 en el HTML
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


# -------------------------------------------------- Modo Alberto: clon fresco
# Regresión: sin maestro (caja-de-alberto vacía / nodo sin submodule), la rama
# sin datos de _pendiente_alberto devolvía un dict SIN las claves pagado_*;
# el guard de la plantilla (`is not none`) da True con Undefined ⇒ `/` moría
# en 500 y el lanzador decía «No arrancó en 30 s».


def test_operaciones_sin_store_degrada_sin_romper(monkeypatch):
    """Clon fresco sin store: `/` responde 200 con la nota, jamás 500."""
    with TestClient(create_app(records=demo_records())) as c:
        r = c.get("/")
    assert r.status_code == 200
    assert "Lo que te toca hoy" in r.text


def test_pendiente_forma_completa_sin_datos():
    """La rama sin datos devuelve la MISMA forma (claves presentes a None):
    una clave ausente sería Undefined y el guard de la plantilla fallaría."""
    import albertitos.ui.app as ui_app

    d = ui_app._pendiente_alberto(Path(".sdd/pytest-tmp/no-existe"))
    assert set(d) == {"n", "pagado_n", "pagado_total", "no_pago_n", "nota"}
    assert d["n"] is None and d["pagado_n"] is None


def test_pendiente_con_store_sembrado(tmp_path: Path):
    """Camino con datos: conteos por resultado directamente del store."""
    from albertitos.store import Store
    from albertitos.types import Decision, RuleVerdict

    def dec(file_id: str, result: str) -> Decision:
        return Decision(
            invoice_id=f"inv-{file_id}", file_id=file_id, result=result,
            rule_verdicts=[RuleVerdict(code="TOTALS_MUST_MATCH", outcome="PASS",
                                       reason="ok", consumed={})],
            config_snapshot={"config_version": "v-test"},
        )

    store = Store(tmp_path)
    store.record_decision(dec("A.pdf", "PAGAR"), "s1", numero_factura="F1",
                          pedido="P1", engine_version="ev")
    store.record_decision(dec("B.pdf", "ESCALAR"), "s2", numero_factura="F2",
                          pedido="P2", engine_version="ev")
    import albertitos.ui.app as ui_app

    d = ui_app._pendiente_alberto(tmp_path)
    assert d["n"] == {"valor": "1"}          # ESCALAR espera decisión
    assert d["pagado_n"] == {"valor": "1"}
    assert d["no_pago_n"] == {"valor": "0"}
