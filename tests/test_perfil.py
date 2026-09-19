"""T23 — perfil de carga: el JSON se genera desde una corrida sembrada (sin red
externa; loopback permitido). Los componentes reales (UI + runner) se lanzan
de verdad contra stores temporales bajo `.sdd/` — jamás contra el store real.
"""

import json
import shutil
from pathlib import Path

import pytest

from albertitos.perfil import perfilar_carga

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def escenario(tmp_store: Path) -> dict[str, Path]:
    """Store sembrado para la UI (formato real) + 3 PDFs con capa de texto."""
    base = Path(".sdd") / "pytest-tmp" / "perfil"
    if base.exists():
        shutil.rmtree(base)
    (base / "ledger").mkdir(parents=True)
    (base / "review-queue").mkdir()

    # 5 decisiones reales en formato runner (3 PAGAR, 1 NO_PAGAR, 1 ESCALAR)
    datos = [
        ("A.pdf", "inv-a", "PAGAR", "NIF_IN_MASTER:PASS,TOTALS_MUST_MATCH:PASS"),
        ("B.pdf", "inv-b", "NO_PAGAR", "NIF_IN_MASTER:FAIL,PROVEEDOR_FANTASMA:FAIL"),
        ("C.pdf", "inv-c", "ESCALAR", "TOTALS_MUST_MATCH:PASS,IVA_CONSISTENT:UNKNOWN"),
        ("D.pdf", "inv-d", "PAGAR", "NIF_IN_MASTER:PASS"),
        ("E.pdf", "inv-e", "PAGAR", "NIF_IN_MASTER:PASS"),
    ]
    with (base / "ledger" / "ledger.jsonl").open("w", encoding="utf-8") as fh:
        for file_id, iid, result, codes in datos:
            fh.write(
                json.dumps(
                    {
                        "config_version": "v3.0-test",
                        "event": "decision",
                        "file_id": file_id,
                        "invoice_id": iid,
                        "result": result,
                        "rule_codes": codes,
                        "sha256": "0" * 64,
                    }
                )
                + "\n"
            )
    # PDFs con capa de texto para los runners (fixtures del corpus)
    pdfs = base / "facturas"
    pdfs.mkdir()
    for nombre in sorted(p.name for p in (FIXTURES / "facturas").glob("*.pdf"))[:3]:
        shutil.copy(FIXTURES / "facturas" / nombre, pdfs / nombre)
    yield {
        "store_ledger": base / "ledger",
        "facturas": pdfs,
        "base": base,
        "tmp_store": tmp_store,
    }
    shutil.rmtree(base)


@pytest.fixture()
def tmp_store() -> Path:
    base = Path(".sdd") / "pytest-tmp" / "perfil-tmpstores"
    base.mkdir(parents=True, exist_ok=True)
    return base


def test_perfil_json_generado_desde_corrida_sembrada(escenario: dict[str, Path]):
    destino = Path(".sdd") / "pytest-tmp" / "perfil-carga.json"
    try:
        perfilar_carga(
            store_ledger=escenario["store_ledger"],
            facturas_dir=escenario["facturas"],
            ui_port=8131,
            ui_requests=1,
            runner_limit=3,
            n_runners=1,
            root=Path(".sdd") / "pytest-tmp" / "perfil-run",
            json_destino=destino,
        )
        assert destino.is_file()
        datos = json.loads(destino.read_text(encoding="utf-8"))
        # lo pedido por el ticket
        assert datos["regimen"]["ui_arrancada"] is True
        assert "ui" in datos["componentes"]
        assert datos["componentes"]["ui"]["rss_mb"] is not None
        assert datos["ram_sistema"]["etiqueta"] == "medido"
        for pantalla in ("/", "/facturas", "/revision", "/reglas", "/salud"):
            m = datos["pantallas"][pantalla]
            assert m["n"] == 1 and m["etiqueta"] == "medido"
            assert m["p95_ms"] is not None
        # runners reales corrieron y midieron
        assert len(datos["componentes"]) >= 2  # ui + al menos 1 runner
        assert datos["concurrencia"]["etiqueta"] == "medido"
        assert "nota_mas_ram" in datos["concurrencia"]
        # fórmula de coste intacta: el perfil no la toca (T9)
        assert "fuentes" in datos
    finally:
        destino.unlink(missing_ok=True)
        shutil.rmtree(Path(".sdd") / "pytest-tmp" / "perfil-run")


def test_rojo_si_ui_degrada():
    """UI > 2 s/página ⇒ ROJO con causa, documentado (no parcheado a mano)."""
    from albertitos.perfil import ROJO_P95_MS, rojos_de

    resumen = {p: {"p95_ms": 10000.0, "etiqueta": "medido"} for p in ("/", "/facturas")}
    rojos = rojos_de(resumen)
    assert rojos and "p95 10000.0 ms" in rojos[0]["causa"]

    resumen_ok = {p: {"p95_ms": 120.0, "etiqueta": "medido"} for p in ("/", "/facturas")}
    assert rojos_de(resumen_ok) == []
    assert ROJO_P95_MS == 2000.0
