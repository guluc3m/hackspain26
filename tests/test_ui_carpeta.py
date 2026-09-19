"""Carpeta elegida por el usuario: escaneo recursivo y proceso desde la UI.

La app debe funcionar en el ordenador de Alberto con CUALQUIER lote y en
cualquier SO (Windows/mac/Linux): nada de rutas hardcodeadas — el usuario
pega la ruta de una carpeta en Operaciones y el sistema la recorre entera
(subcarpetas incluidas) buscando PDFs y los procesa. Los lotes entregados
son solo un caso particular.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from albertitos.emit import list_pdf_files_recursivo
from albertitos.pipeline import PipelineDeps, run_batch
from albertitos.rules import load_config, load_master
from albertitos.run import DEFAULT_RULES
from albertitos.store import Store
from albertitos.ui.app import create_app
from albertitos.ui.demo import demo_records
from conftest import FIXTURES, fixture_path

MASTER_XLSX = fixture_path("maestro_fixture.xlsx")
FECHA_REF = "2026-09-19"


# ---------------------------------------------------------------- escaneo


def _lote_anidado(tmp_path: Path) -> Path:
    """Carpeta con PDFs a distintos niveles (lo que entrega Alberto)."""
    raiz = tmp_path / "facturas"
    (raiz / "sub").mkdir(parents=True)
    (raiz / "sub" / "mas-profundo").mkdir(parents=True)
    fuentes = sorted((FIXTURES / "facturas").glob("*.pdf"))
    shutil.copy(fuentes[0], raiz / "a-raiz.pdf")
    shutil.copy(fuentes[1 % len(fuentes)], raiz / "sub" / "b-sub.PDF")
    shutil.copy(fuentes[2 % len(fuentes)], raiz / "sub" / "mas-profundo" / "c-profundo.pdf")
    # archivos que NO son PDF: el escaneo los ignora
    (raiz / "notas.txt").write_text("no es factura", encoding="utf-8")
    (raiz / "hoja.xlsx").write_bytes(b"no es factura")
    return raiz


def test_escaneo_recursivo_encuentra_todos_los_pdfs(tmp_path: Path):
    raiz = _lote_anidado(tmp_path)
    encontrados = list_pdf_files_recursivo(raiz)
    nombres = {p.name for p in encontrados}
    assert nombres == {"a-raiz.pdf", "b-sub.PDF", "c-profundo.pdf"}


def test_escaneo_recursivo_ignora_lo_que_no_es_pdf(tmp_path: Path):
    raiz = _lote_anidado(tmp_path)
    assert not any(p.suffix == ".txt" or p.suffix == ".xlsx"
                   for p in list_pdf_files_recursivo(raiz))


def test_escaneo_recursivo_orden_determinista(tmp_path: Path):
    raiz = _lote_anidado(tmp_path)
    rutas = [str(p) for p in list_pdf_files_recursivo(raiz)]
    assert rutas == sorted(rutas)
    assert rutas == [str(p) for p in list_pdf_files_recursivo(raiz)]


def test_escaneo_recursivo_carpeta_inexistente_devuelve_vacio(tmp_path: Path):
    assert list_pdf_files_recursivo(tmp_path / "no-existe") == []


def test_escaneo_recursivo_carpetas_vacias(tmp_path: Path):
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    assert list_pdf_files_recursivo(vacia) == []


# ---------------------------------------------------------------- pipeline

def _deps():
    cfg = load_config(DEFAULT_RULES, fecha_referencia=FECHA_REF)
    master = load_master(MASTER_XLSX, hojas_ignoradas=cfg.hojas_ignoradas)
    return PipelineDeps(master=master, config=cfg)


def test_pipeline_recursivo_procesa_subcarpetas(tmp_path: Path):
    """run_batch(recursivo=True) llega a los PDFs anidados, no solo a la raíz."""
    raiz = _lote_anidado(tmp_path)
    store = Store(tmp_path / ".sdd")
    try:
        report = run_batch(raiz, store, _deps(), recursivo=True)
        decididos = {d.file_id for d in store.all_decisions()}
        assert decididos == {"a-raiz.pdf", "b-sub.PDF", "c-profundo.pdf"}
        assert report.procesados == 3
        # idempotencia también en modo recursivo: re-run = no-op
        report2 = run_batch(raiz, store, _deps(), recursivo=True)
        assert report2.procesados == 0
        assert report2.reutilizados == 3
    finally:
        store.close()


def test_pipeline_sin_recursivo_solo_primer_nivel(tmp_path: Path):
    """El modo histórico no cambia: sin recursivo, solo la raíz."""
    raiz = _lote_anidado(tmp_path)
    store = Store(tmp_path / ".sdd")
    try:
        report = run_batch(raiz, store, _deps())
        decididos = {d.file_id for d in store.all_decisions()}
        assert decididos == {"a-raiz.pdf"}
        assert report.procesados == 1
    finally:
        store.close()


# ---------------------------------------------------------------- UI

@pytest.fixture()
def cliente_procesador():
    """App con un procesador falso que graba la carpeta recibida."""
    llamadas: list[Path] = []

    def falso_procesador(carpeta: Path) -> dict:
        llamadas.append(carpeta)
        return {"estado": "listo", "mensaje": "falso lote terminado"}

    app = create_app(records=demo_records(), procesador=falso_procesador)
    return TestClient(app), llamadas, app


def _esperar_lote(app, timeout_s: float = 5.0) -> dict:
    fin = time.monotonic() + timeout_s
    while time.monotonic() < fin:
        lote = app.state.lote
        if lote is not None and lote.get("estado") != "procesando":
            return lote
        time.sleep(0.02)
    raise AssertionError("el lote sigue procesándose: timeout")


def test_operaciones_muestra_formulario_carpeta():
    r = TestClient(create_app(records=demo_records())).get("/")
    assert r.status_code == 200
    assert 'name="carpeta"' in r.text
    assert "Procesar carpeta" in r.text
    assert "subcarpetas" in r.text


def test_ui_procesa_carpeta_con_pdfs(tmp_path: Path):
    llamadas: list[Path] = []

    def falso_procesador(carpeta: Path) -> dict:
        llamadas.append(carpeta)
        return {"estado": "listo", "mensaje": "falso lote terminado"}

    app = create_app(records=demo_records(), procesador=falso_procesador)
    client = TestClient(app)
    raiz = _lote_anidado(tmp_path)

    r = client.post("/operaciones/procesar", data={"carpeta": str(raiz)},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    lote = _esperar_lote(app)
    assert llamadas == [raiz]
    assert lote["estado"] == "listo"
    assert lote["carpeta"] == str(raiz)

    # la página muestra el resultado del último lote
    pagina = client.get("/").text
    assert "falso lote terminado" in pagina


def test_ui_rechaza_carpeta_inexistente_sin_procesar(cliente_procesador):
    client, llamadas, app = cliente_procesador
    r = client.post("/operaciones/procesar", data={"carpeta": str(Path("no/existe"))},
                    follow_redirects=False)
    assert r.status_code == 303
    lote = _esperar_lote(app)
    assert lote["estado"] == "error"
    assert "no existe" in lote["mensaje"]
    assert llamadas == []


def test_ui_rechaza_carpeta_sin_pdfs(cliente_procesador, tmp_path: Path):
    client, llamadas, app = cliente_procesador
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    r = client.post("/operaciones/procesar", data={"carpeta": str(vacia)},
                    follow_redirects=False)
    assert r.status_code == 303
    lote = _esperar_lote(app)
    assert lote["estado"] == "error"
    assert "ningún PDF" in lote["mensaje"]
    assert llamadas == []


def test_ui_comillas_de_copiar_como_ruta(tmp_path: Path):
    """Windows copia las rutas entre comillas: hay que tolerarlas."""
    llamadas: list[Path] = []

    def falso_procesador(carpeta: Path) -> dict:
        llamadas.append(carpeta)
        return {"estado": "listo", "mensaje": "ok"}

    app = create_app(records=demo_records(), procesador=falso_procesador)
    client = TestClient(app)
    raiz = _lote_anidado(tmp_path)
    client.post("/operaciones/procesar", data={"carpeta": f'"{raiz}"'})
    _esperar_lote(app)
    assert llamadas == [raiz]


def test_ui_no_arranca_segundo_lote_mientras_hay_uno_en_curso(tmp_path: Path):
    llamadas: list[Path] = []

    def procesador_lento(carpeta: Path) -> dict:
        llamadas.append(carpeta)
        time.sleep(0.3)
        return {"estado": "listo", "mensaje": "terminado"}

    app = create_app(records=demo_records(), procesador=procesador_lento)
    client = TestClient(app)
    raiz = _lote_anidado(tmp_path)
    client.post("/operaciones/procesar", data={"carpeta": str(raiz)})
    client.post("/operaciones/procesar", data={"carpeta": str(raiz)})
    lote = _esperar_lote(app)
    assert llamadas == [raiz]  # solo el primer POST llegó al procesador
    assert lote["estado"] == "listo"


def test_reglas_por_defecto_viajan_con_el_paquete():
    """Las reglas viven dentro del paquete: nada de rutas de una máquina."""
    assert DEFAULT_RULES.is_file()


def test_maestro_por_variable_de_entorno(tmp_path: Path, monkeypatch):
    """El maestro se localiza con ALBERTITOS_MAESTRO; sin env ni layout
    relativo, devuelve None (degrada con mensaje, jamás una ruta fija)."""
    from albertitos.ui import app as ui_app

    falso = tmp_path / "maestro.xlsx"
    falso.write_bytes(b"no es un excel de verdad, basta para el test de ruta")
    monkeypatch.setenv("ALBERTITOS_MAESTRO", str(falso))
    assert ui_app._maestro_para_resumen() == falso

    monkeypatch.delenv("ALBERTITOS_MAESTRO")
    monkeypatch.chdir(tmp_path)  # sin .sdd/ ni caja-de-alberto relativos
    assert ui_app._maestro_para_resumen() is None


def test_ui_carpeta_entregada_como_lote_completo(tmp_path: Path):
    """Un lote entregado al estilo del corpus (solo PDFs en la raíz) también
    funciona: el escaneo recursivo es un superconjunto del plano."""
    raiz = tmp_path / "lote"
    raiz.mkdir()
    for f in sorted((FIXTURES / "facturas").glob("*.pdf"))[:2]:
        shutil.copy(f, raiz / f.name)
    assert {p.name for p in list_pdf_files_recursivo(raiz)} == {
        f.name for f in sorted((FIXTURES / "facturas").glob("*.pdf"))[:2]
    }
