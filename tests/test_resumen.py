"""T26 — resumen ejecutivo para Alberto: totales EXACTOS desde el store
sembrado; sin datos ⇒ PENDIENTE, jamás ceros falsos. PDF y HTML (el binario
typst solo compila si está disponible; sin él, el HTML es completo)."""

import shutil
import sqlite3
from pathlib import Path

import pytest

from albertitos.resumen import datos_resumen, generar_resumen
from albertitos.resumen import main as resumen_cli

FIXTURES = Path(__file__).parent / "fixtures"


def _store_sembrado(base: Path) -> None:
    """Store con el esquema REAL del runner: file_id, pedido, rule_codes."""
    base.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(base / "store.db")
    conn.execute(
        "CREATE TABLE invoices (file_id TEXT PRIMARY KEY, invoice_id TEXT,"
        " sha256 TEXT, result TEXT, rule_codes TEXT, numero_factura TEXT,"
        " pedido TEXT, config_version TEXT, engine_version TEXT, updated_at TEXT,"
        " nif TEXT, iban TEXT)"
    )
    decisiones = [
        # PAGAR con importes conocidos: total = 4635.26 + 6540.90 = 11176.16
        ("A.pdf", "PAGAR", "NIF_IN_MASTER:PASS,ORDER_AMOUNT_MATCHES:PASS", "PO-2026-0177"),
        ("B.pdf", "PAGAR", "NIF_IN_MASTER:PASS", "PO-2026-0815"),
        # PAGAR sin pedido en el maestro ⇒ aviso, NO se suma
        ("C.pdf", "PAGAR", "NIF_IN_MASTER:PASS", "PO-INEXISTENTE"),
        # NO_PAGAR: dos motivos
        ("D.pdf", "NO_PAGAR", "ORDER_AMOUNT_MATCHES:FAIL,NIF_IN_MASTER:FAIL", "PO-2026-0177"),
        ("E.pdf", "NO_PAGAR", "ORDER_AMOUNT_MATCHES:FAIL", "PO-2026-0815"),
        ("F.pdf", "NO_PAGAR", "ORDER_AMOUNT_MATCHES:FAIL", "PO-2026-0815"),
        # ESCALAR con importe conocido y otro sin él
        ("G.pdf", "ESCALAR", "IVA_CONSISTENT:UNKNOWN", "PO-2026-0815"),
        ("H.pdf", "ESCALAR", "RUNNER_TIMEOUT:UNKNOWN", ""),
        # duplicado y fantasma para avisos
        ("I.pdf", "NO_PAGAR", "NO_DOUBLE_PAYMENT:FAIL", "PO-2026-0177"),
        ("J.pdf", "NO_PAGAR", "PROVEEDOR_FANTASMA:FAIL,NIF_IN_MASTER:FAIL", ""),
    ]
    for file_id, result, codes, pedido in decisiones:
        conn.execute(
            "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (file_id, "inv-" + file_id, "0" * 64, result, codes, "FA-" + file_id,
             pedido, "v3.0-test", "runner-1.0.0", "2026-09-19T00:00:00", "", ""),
        )
    conn.commit()
    conn.close()


@pytest.fixture()
def escenario() -> dict[str, Path]:
    base = Path(".sdd") / "pytest-tmp" / "resumen"
    if base.exists():
        shutil.rmtree(base)
    _store_sembrado(base / "sdd")
    yield {"store": base / "sdd", "maestro": FIXTURES / "maestro_fixture.xlsx", "base": base}
    shutil.rmtree(base)


def test_totales_son_la_suma_exacta_de_los_pagar(escenario: dict[str, Path]):
    """El TOTAL del resumen = suma EXACTA de los importes del maestro para los
    PAGAR (no inventados); C.pdf no está en el maestro ⇒ no suma, y avisa."""
    datos = datos_resumen(escenario["store"], escenario["maestro"])
    assert datos["pago"]["n"]["valor"] == "3"  # A, B, C (C sin importe)
    assert datos["pago"]["total_eur"]["valor"] == "11,176.16 EUR"  # 4635.26 + 6540.90
    assert datos["pago"]["sin_importe"] == ["C.pdf"]  # avisado, nunca inventado
    # top10 ordenado por importe desc
    top = datos["pago"]["top10"]
    assert top[0]["file_id"] == "B.pdf" and top[0]["importe_eur"] == 6540.90
    assert top[1]["importe_eur"] == 4635.26


def test_motivos_en_llano_con_ejemplos(escenario: dict[str, Path]):
    datos = datos_resumen(escenario["store"], escenario["maestro"])
    motivos = datos["no_pago"]["motivos"]
    assert datos["no_pago"]["n"]["valor"] == "5"  # D, E, F, I, J
    assert motivos["el importe no coincide con el pedido"]["n"] == 3
    assert set(motivos["el importe no coincide con el pedido"]["ejemplos"]) == {"D.pdf", "E.pdf", "F.pdf"}
    assert motivos["ya consta un pago para ese pedido (duplicado)"]["n"] == 1
    assert motivos["proveedor fantasma: NIF desconocido e IBAN compartido"]["n"] == 1


def test_revisar_ordenado_por_importe_con_placeholder(escenario: dict[str, Path]):
    datos = datos_resumen(escenario["store"], escenario["maestro"])
    assert datos["revisar"]["n"]["valor"] == "2"
    lista = datos["revisar"]["lista"]
    # primero la que tiene importe conocido; la sin importe, al final honesta
    assert lista[0]["file_id"] == "G.pdf"
    assert lista[1]["file_id"] == "H.pdf" and lista[1]["importe_eur"] is None
    assert lista[1]["motivo"] == "el archivo tardó demasiado y quedó sin leer del todo"


def test_hoja_trampa_ignorada():
    """El maestro trae hojas trampa (NO_TOCAR, backup, OLD): se ignoran y avisan."""
    datos = datos_resumen(Path(".sdd/pytest-tmp/resumen/sdd"), FIXTURES / "maestro_fixture.xlsx")
    assert any("Pedidos_2025_OLD" in a for a in datos["avisos"]["maestro"])
    assert any("NO_TOCAR" in a for a in datos["avisos"]["maestro"])


def test_html_y_pdf_se_generan(escenario: dict[str, Path]):
    destino = Path(".sdd/pytest-tmp/resumen_alberto")
    try:
        rutas = generar_resumen(escenario["store"], escenario["maestro"], destino)
        assert rutas["html"].is_file()
        html = rutas["html"].read_text(encoding="utf-8")
        assert "¿Qué pago hoy" in html
        assert "11,176.16 EUR" in html  # suma EXACTA de los PAGAR sembrados
        assert "el importe no coincide con el pedido" in html
        assert "data:image" not in html  # nada que no corresponda
        if "pdf" in rutas:
            from pypdf import PdfReader

            lector = PdfReader(str(rutas["pdf"]))
            texto = "\n".join(p.extract_text() or "" for p in lector.pages)
            assert "Resumen para Alberto" in texto
            assert "11,176.16 EUR" in texto or "11.176,16" in texto or "11176" in texto
        else:
            pytest.skip("binario typst no disponible en este nodo")
    finally:
        for f in ("html", "pdf", "typ"):
            (destino.with_suffix("." + f)).unlink(missing_ok=True)


def test_sin_datos_placeholder_no_ceros_falsos():
    """Store vacío ⇒ PENDIENTE en el total, jamás '0 facturas' como si fuera real."""
    vacio = Path(".sdd/pytest-tmp/resumen-vacio")
    vacio.mkdir(parents=True, exist_ok=True)
    try:
        datos = datos_resumen(vacio, FIXTURES / "maestro_fixture.xlsx")
        assert datos["pago"]["n"]["valor"] == "0"
        assert "PENDIENTE" in datos["pago"]["total_eur"]["valor"]
        generar_resumen(vacio, FIXTURES / "maestro_fixture.xlsx", vacio / "resumen")
        texto = (vacio / "resumen.html").read_text(encoding="utf-8")
        assert "PENDIENTE: sin importes" in texto
    finally:
        shutil.rmtree(vacio)


def test_cli_imprime_rutas(escenario: dict[str, Path], capsys):
    salida = Path(".sdd/pytest-tmp/resumen-cli")
    assert resumen_cli(["--store-root", str(escenario["store"]), "--maestro", str(escenario["maestro"]), "--salida", str(salida)]) == 0
    assert salida.with_suffix(".html").is_file()
    salida.with_suffix(".html").unlink(missing_ok=True)
    salida.with_suffix(".pdf").unlink(missing_ok=True)
    salida.with_suffix(".typ").unlink(missing_ok=True)


# ------------------------------------------------------------- T30 · riesgo


def test_plan_riesgo_sumas_acumuladas_exactas(escenario: dict[str, Path]):
    """Plan por dinero en riesgo: orden desc, acumulado y % EXACTOS contra el
    store sembrado (escaladas: G 6540.90; H sin importe)."""
    datos = datos_resumen(escenario["store"], escenario["maestro"])
    riesgo = datos["riesgo"]
    assert riesgo["total_en_riesgo_eur"]["valor"] == "6,540.90 EUR"
    assert riesgo["sin_importe"] == 1  # H: sin pedido en el maestro
    plan = riesgo["plan"]
    assert [p["file_id"] for p in plan] == ["G.pdf"]
    assert plan[0]["acumulado_eur"] == 6540.90
    assert plan[0]["pct_acumulado"] == 100.0  # única con importe ⇒ cubre el 100 %
    # para cubrir el 80 % del riesgo basta la primera (6540.90 ≥ 0.8·6540.90)
    assert riesgo["para_cubrir_80_pct"]["valor"] == "1"


def test_plan_riesgo_matematica_exacta(escenario: dict[str, Path]):
    """80 % con dos facturas: el mínimo k es 1 si la mayor ≥ 80 % del total."""
    # ampliar el store con una segunda escalada de importe para probar el k
    conn = sqlite3.connect(escenario["store"] / "store.db")
    conn.execute(
        "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("K.pdf", "inv-K", "0" * 64, "ESCALAR", "IVA_CONSISTENT:UNKNOWN", "FA-K",
         "PO-2026-0177", "v3.0-test", "runner-1.0.0", "2026-09-19T00:00:00", "", ""),
    )
    conn.commit()
    conn.close()
    datos = datos_resumen(escenario["store"], escenario["maestro"])
    plan = datos["riesgo"]["plan"]
    # escaladas con importe: G (6540.90) y K (4635.26) → total 11176.16
    assert datos["riesgo"]["total_en_riesgo_eur"]["valor"] == "11,176.16 EUR"
    assert [p["file_id"] for p in plan] == ["G.pdf", "K.pdf"]
    assert plan[0]["acumulado_eur"] == 6540.90
    assert plan[0]["pct_acumulado"] == round(100 * 6540.90 / 11176.16, 1)
    assert plan[1]["acumulado_eur"] == 11176.16
    assert plan[1]["pct_acumulado"] == 100.0
    # 6540.90 < 0.8 × 11176.16 (= 8940.93) ⇒ hacen falta las DOS
    assert datos["riesgo"]["para_cubrir_80_pct"]["valor"] == "2"


def test_plan_riesgo_html_y_pdf(escenario: dict[str, Path]):
    destino = Path(".sdd/pytest-tmp/resumen_riesgo")
    try:
        rutas = generar_resumen(escenario["store"], escenario["maestro"], destino)
        html = rutas["html"].read_text(encoding="utf-8")
        assert "Plan por dinero en riesgo" in html
        assert "6,540.90 EUR" in html  # riesgo del escenario sembrado
        assert "80 %" in html
        if "pdf" in rutas:
            from pypdf import PdfReader

            texto = "\n".join(p.extract_text() or "" for p in PdfReader(str(rutas["pdf"])).pages)
            assert "Plan por dinero en riesgo" in texto
        else:
            pytest.skip("binario typst no disponible")
    finally:
        for f in ("html", "pdf", "typ"):
            destino.with_suffix("." + f).unlink(missing_ok=True)


def test_plan_riesgo_sin_datos_placeholder(escenario: dict[str, Path]):
    """Sin importes ⇒ PENDIENTE honesto, jamás '0 EUR' fingido."""
    datos = datos_resumen(Path(".sdd/pytest-tmp/resumen-vacio"), escenario["maestro"])
    assert "PENDIENTE" in datos["riesgo"]["total_en_riesgo_eur"]["valor"]
    assert datos["riesgo"]["plan"] == []
    assert datos["riesgo"]["para_cubrir_80_pct"]["valor"] == "PENDIENTE"
