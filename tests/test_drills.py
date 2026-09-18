"""T12 — drills de resiliencia: corren en tests con mocks, sin red real.

Estado de trabajo bajo `.sdd/` (jamás /tmp). drills.json refleja el resultado
por drill con mediciones.
"""

import json
import shutil
from pathlib import Path

import pytest

from albertitos.drills import (
    drill_backoff_429,
    drill_crash_reanudacion,
    drill_ledger_corrupto,
    drill_rung5_provider_caido,
    ejecutar_drills,
)
from albertitos.drills import (
    main as drills_main,
)


@pytest.fixture()
def root() -> Path:
    base = Path(".sdd") / "pytest-tmp" / "drills"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    yield base
    shutil.rmtree(base.parent)


def test_drill_rung5_caido_degrada_sin_abortar(root: Path):
    r = drill_rung5_provider_caido(root)
    m = r["mediciones"]
    assert r["pass"], r["detalle"]
    assert m["intentos_cloud"] == 3  # max_retries(2) + 1
    assert m["error_en_evidencia"] is True
    assert "provider-failed" in m["motivo_evidencia"]
    assert m["pagina_en_cola_revision"] is True  # ESCALAR, con motivo
    assert m["lote_continua"] is True  # degradación, no aborte


def test_drill_backoff_429_respetado(root: Path):
    r = drill_backoff_429(root)
    m = r["mediciones"]
    assert r["pass"], r["detalle"]
    assert m["n_llamadas"] == 3  # 429, 429, 200 — ninguna llamada extra
    assert m["delays_aplicados"] == m["delays_esperados"]
    assert m["delays_aplicados"][0] == 0.05  # Retry-After 2.0 con cap 0.05
    assert m["exito"] is True


def test_drill_crash_reanudacion_sin_duplicados(root: Path):
    r = drill_crash_reanudacion(root)
    m = r["mediciones"]
    assert r["pass"], r["detalle"]
    assert m["decididos_tras_crash"] < m["n_archivos"]  # el crash cortó el lote
    assert m["reanudacion_completa"] is True
    assert m["sin_duplicados"] is True
    assert m["duplicados_en_store"] == 0
    assert m["reutilizados_por_cache"] == m["decididos_tras_crash"]


def test_drill_ledger_corrupto_tolerado(root: Path):
    r = drill_ledger_corrupto(root)
    m = r["mediciones"]
    assert r["pass"], r["detalle"]
    assert m["registros_validos"] == 2
    assert m["lineas_corruptas_ignoradas"] == 3
    assert m["sin_datos_inventados"] is True


def test_drills_json_se_genera(root: Path):
    destino = Path(".sdd") / "pytest-tmp" / "drills.json"
    try:
        reporte = ejecutar_drills(root, destino)
        assert destino.is_file()
        datos = json.loads(destino.read_text(encoding="utf-8"))
        assert len(datos["drills"]) == 4
        assert all(d["pass"] for d in datos["drills"]), [d["detalle"] for d in datos["drills"] if not d["pass"]]
        assert datos["resumen"] == {"pass": 4, "fail": 0}
        assert reporte["resumen"]["fail"] == 0
    finally:
        destino.unlink(missing_ok=True)


def test_cli_exit_codes(root: Path, capsys):
    destino = Path(".sdd") / "pytest-tmp" / "drills-cli.json"
    try:
        assert drills_main(["--root", str(root), "--destino", str(destino)]) == 0
        salida = capsys.readouterr().out
        assert "[PASS]" in salida
        # un drill fallido ⇒ exit 1 (se simula manipulando el reporte)
        datos = json.loads(destino.read_text(encoding="utf-8"))
        datos["drills"][0]["pass"] = False
        datos["resumen"] = {"pass": 3, "fail": 1}
        destino.write_text(json.dumps(datos), encoding="utf-8")
        reporte = json.loads(destino.read_text(encoding="utf-8"))
        assert reporte["resumen"]["fail"] == 1  # drills.json refleja resultados
    finally:
        destino.unlink(missing_ok=True)
