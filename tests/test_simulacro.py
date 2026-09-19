"""T28 — simulacro de defensa: el guion contra la medición actual.

Sin red: la UI se verifica in-process (TestClient) y los JSON se sembrados
bajo `.sdd/` (estado de trabajo jamás en /tmp).
"""

import json
import shutil
from pathlib import Path

import pytest

from albertitos.simulacro import simulacro, verificar_guion


@pytest.fixture()
def escenario() -> dict[str, Path]:
    """Metrics sembrados + store en formato real + guion con cifras correctas."""
    base = Path(".sdd") / "pytest-tmp" / "simulacro"
    if base.exists():
        shutil.rmtree(base)
    metrics = base / "metrics"
    metrics.mkdir(parents=True)
    (metrics / "lote1.json").write_text(
        json.dumps(
            {
                "distribucion": {"PAGAR": 433, "NO_PAGAR": 22, "ESCALAR": 45},
                "distribucion_final": {"PAGAR": 433, "NO_PAGAR": 22, "ESCALAR": 45},
                "rung4_vlm_local": {"latencia_media_ms": 33870.3, "latencia_max_ms": 60075, "n_invocaciones": 28},
            }
        ),
        encoding="utf-8",
    )
    (metrics / "perfil-carga.json").write_text(
        json.dumps(
            {
                "pantallas": {p: {"p95_ms": 7.7} for p in ("/", "/facturas", "/revision", "/reglas", "/salud")},
                "runners_files_por_s": [108.722, 109.986],
            }
        ),
        encoding="utf-8",
    )
    (metrics / "drills.json").write_text(
        json.dumps({"resumen": {"pass": 4, "fail": 0}}), encoding="utf-8"
    )
    (metrics / "corpus-dryrun.json").write_text(
        json.dumps(
            {"rutas": {"rung1_pdf_text": 471, "raster_no_qr": 29, "rung2_qr_only": 0, "error": 0, "timeout": 0}}
        ),
        encoding="utf-8",
    )
    # store en formato real para la demo (5 decisiones) y el resumen
    store = base / "lote1"
    (store / "state").mkdir(parents=True)
    (store / "state" / "runner.json").write_text(
        json.dumps({"done": 5, "fallos": 0, "total_archivos": 5, "files_per_second": 4.162,
                    "resultados": {"PAGAR": 3, "NO_PAGAR": 1, "ESCALAR": 1},
                    "config_version": "v3.0-test", "rung4_llama_server": "up"}),
        encoding="utf-8",
    )
    import sqlite3

    conn = sqlite3.connect(store / "store.db")
    conn.execute(
        "CREATE TABLE invoices (file_id TEXT, invoice_id TEXT, sha256 TEXT, result TEXT,"
        " rule_codes TEXT, numero_factura TEXT, pedido TEXT, config_version TEXT,"
        " engine_version TEXT, updated_at TEXT, nif TEXT, iban TEXT)"
    )
    for file_id, result, codes, pedido in [
        ("A.pdf", "PAGAR", "NIF_IN_MASTER:PASS", "PO-1"),
        ("B.pdf", "ESCALAR", "IVA_CONSISTENT:UNKNOWN", "PO-2"),
    ]:
        conn.execute(
            "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (file_id, "inv-" + file_id, "0" * 64, result, codes, "F/" + file_id, pedido,
             "v3.0-test", "runner-1.0.0", "2026-09-19T00:00:00", "", ""),
        )
    conn.commit()
    conn.close()
    yield {
        "guion": base / "DEFENSA.md",
        "metrics": metrics,
        "store_ledger": store / "ledger",
        "store_root": store,
        "maestro": FIXTURES_XLSX,
    }
    shutil.rmtree(base)


FIXTURES_XLSX = Path(__file__).parent / "fixtures" / "maestro_fixture.xlsx"


def _escribir_guion(ruta: Path, total_cifras_ok: bool = True) -> None:
    """Guion mínimo con las afirmaciones que el simulacro contrasta."""
    distribucion = "433/22/45" if total_cifras_ok else "999/999/999"
    p95 = "7,7 ms" if total_cifras_ok else "999 ms"
    ruta.write_text(
        f"""
Régimen completo MEDIDO (perfil de carga, T23): la UI responde con peor p95
< 12 ms (medido {p95} con 500 facturas cargadas), 108–110 archivos/s por
runner, 4/4 PASS (drills), 471/500 (94,2 %) texto usable.
Distribución final: {distribucion}. 433 PAGAR.
Demo paso 1: resumen ejecutivo (¿qué pago hoy?): TOTAL.
Fuentes: `.sdd/metrics/lote1.json`, `.sdd/metrics/perfil-carga.json`,
`.sdd/metrics/drills.json`, `.sdd/metrics/corpus-dryrun.json`.
""",
        encoding="utf-8",
    )


def test_simulacro_verde_con_estado_coherente(escenario: dict[str, Path]):
    _escribir_guion(escenario["guion"], total_cifras_ok=True)
    (escenario["store_ledger"]).mkdir(parents=True, exist_ok=True)
    (escenario["store_ledger"] / "ledger.jsonl").write_text(
        json.dumps({"config_version": "v3.0-test", "event": "decision", "file_id": "A.pdf",
                    "invoice_id": "inv-A", "result": "PAGAR", "rule_codes": "X:PASS", "sha256": "0" * 64}) + "\n",
        encoding="utf-8",
    )
    destino = Path(".sdd/pytest-tmp/simulacro.json")
    try:
        reporte = simulacro(
            guion_path=escenario["guion"],
            metrics_dir=escenario["metrics"],
            store_ledger=escenario["store_ledger"],
            maestro_path=escenario["maestro"],
            destino=destino,
        )
        fallidos = [x["check"] for x in reporte["verificaciones"] if not x["pass"]]
        assert reporte["resumen"]["fail"] == 0, fallidos
        assert not fallidos, fallidos
        assert destino.is_file()
        datos = json.loads(destino.read_text(encoding="utf-8"))
        assert all(x["pass"] for x in datos["verificaciones"])
        # el resumen ejecutivo quedó listo para la demo (paso 1)
        assert any(x["check"] == "resumen-ejecutivo-demo" and x["pass"] for x in datos["verificaciones"])
    finally:
        destino.unlink(missing_ok=True)
        shutil.rmtree(Path(".sdd/review-queue"), ignore_errors=True)


def test_guion_con_cifras_erroneas_falla(escenario: dict[str, Path]):
    """Guion con cifras erróneas ⇒ ROJO con causa (se actualiza el guion, nunca
    se finge)."""
    (escenario["store_ledger"]).mkdir(parents=True, exist_ok=True)
    (escenario["store_ledger"] / "ledger.jsonl").write_text(
        json.dumps({"config_version": "v3.0-test", "event": "decision", "file_id": "A.pdf",
                    "invoice_id": "inv-A", "result": "PAGAR", "rule_codes": "X:PASS", "sha256": "0" * 64}) + "\n",
        encoding="utf-8",
    )
    _escribir_guion(escenario["guion"], total_cifras_ok=False)  # 999/999/999
    destino = Path(".sdd/pytest-tmp/simulacro-rojo.json")
    try:
        reporte = simulacro(
            guion_path=escenario["guion"],
            metrics_dir=escenario["metrics"],
            store_ledger=escenario["store_ledger"],
            maestro_path=escenario["maestro"],
            destino=destino,
        )
        fallidos = [x["check"] for x in reporte["verificaciones"] if not x["pass"]]
        assert "distribucion-final-433-22-45" in fallidos
        assert reporte["resumen"]["fail"] >= 1
    finally:
        destino.unlink(missing_ok=True)
        shutil.rmtree(Path(".sdd/review-queue"), ignore_errors=True)


def test_verificaciones_individuales(escenario: dict[str, Path]):
    _escribir_guion(escenario["guion"], total_cifras_ok=True)
    v = verificar_guion(
        escenario["guion"], escenario["metrics"], escenario["store_ledger"], escenario["maestro"]
    )
    por_check = {x["check"]: x["pass"] for x in v}
    assert por_check["dryrun-471-29-0"] is True
    assert por_check["perfil-p95-pantallas"] is True  # 7,7 ms citado = medido 7.7
    assert por_check["runners-files-por-segundo"] is True
    assert por_check["drills-4-sobre-4"] is True
