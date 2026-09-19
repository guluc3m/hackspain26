"""T20 — guion de defensa: 4 secciones + checklist + fuentes existentes.

Regla del ticket: cada cifra citada debe existir en .sdd/metrics/ con fuente.
El test valida que DEFENSA.md exista, tenga las 4 secciones y el checklist,
que TODOS los ficheros de evidencia citados existan, y que los números
estrella del guion estén realmente en los JSON medidos.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
DEFENSA = REPO / "docs" / "report" / "DEFENSA.md"


def test_guion_existe_con_4_secciones_y_checklist():
    texto = DEFENSA.read_text(encoding="utf-8")
    for seccion in (
        "## 1. Demo y contexto (2 min)",
        "## 2. Arquitectura y ADRs (2 min)",
        "## 3. Trazabilidad, escala y coste (4 min)",
        "## 4. Resiliencia (2 min)",
    ):
        assert seccion in texto, seccion
    assert "## Checklist operativo" in texto
    assert "## Plan B" in texto  # qué mostrar si algo falla en vivo
    assert "uvicorn" in texto and "ALBERTITOS_STORE" in texto  # comandos reales
    # la demo no improvisa: las faltas de datos se declaran PENDIENTE
    assert "PENDIENTE-MEDICIÓN" in texto


def test_todos_los_ficheros_citados_existen():
    """Cada ruta `.sdd/...` citada en el guion existe en disco (fuente real)."""
    texto = DEFENSA.read_text(encoding="utf-8")
    rutas = set(re.findall(r"`(\.sdd/[A-Za-z0-9_\-./]+)`", texto))
    assert rutas, "el guion debe citar sus fuentes"
    for ruta in sorted(rutas):
        p = Path(REPO / ruta)
        assert p.exists() or p.resolve().exists(), f"fuente citada inexistente: {ruta}"


def test_numeros_estrella_estan_en_los_json_medidos():
    """Los datos centrales del guion salen de los JSON, no de memoria."""
    dry = json.loads((REPO / ".sdd/metrics/corpus-dryrun.json").read_text(encoding="utf-8"))
    assert dry["rutas"]["rung1_pdf_text"] == 471
    assert dry["rutas"]["raster_no_qr"] == 29
    assert dry["rutas"]["rung2_qr_only"] == 0

    lote = json.loads((REPO / ".sdd/metrics/lote1.json").read_text(encoding="utf-8"))
    # esquema estable a través de T14→T18→T22: o lote completo (n=500) o
    # registro de reproceso T18 (n=subset, con distribucion→distribucion_final)
    if lote["n_archivos"] == 500:
        assert lote.get("fallos", 0) == 0 or lote.get("validador") == "OK"
        dist = lote["distribucion"]
    else:
        dist = lote["distribucion_final"]
    assert sum(dist.values()) == 500
    assert set(dist) <= {"PAGAR", "NO_PAGAR", "ESCALAR"}
    # files_per_s evolucionó de float a dict con nota — solo exigir que exista
    assert lote.get("files_per_s")

    drills = json.loads((REPO / ".sdd/metrics/drills.json").read_text(encoding="utf-8"))
    assert drills["resumen"] == {"pass": 4, "fail": 0}

    outcomes = (REPO / ".sdd/metrics/outcomes-lote1.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(outcomes) == 500


def test_el_guion_declara_sus_pendientes():
    texto = DEFENSA.read_text(encoding="utf-8")
    # exactitud y reprocesado siguen pendientes: se dicen, no se inventan
    assert "PENDIENTE-MEDICIÓN(T14-referencia)" in texto
    # y se prohíbe improvisar
    assert "PROHIBIDO" in texto
