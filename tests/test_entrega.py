"""T37 — cierre de entrega: repo de entrega válido + entrega.json verificable.

El repo de entrega vive en ~/delivery-repo (fuera de git). Los tests verifican
que entrega.json (sha256 de los entregables) coincide con los ficheros
reales; si el repo no está en este nodo, se saltan con motivo claro.
"""

import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
DELIVERY = Path.home() / "delivery-repo"
ENTREGA = REPO / ".sdd" / "metrics" / "entrega.json"

CONTRATO = ("outcomes.jsonl", "outcomes_lote2.jsonl", "albertitos_plan.pdf")


@pytest.fixture()
def entrega() -> dict:
    if not ENTREGA.is_file():
        pytest.skip("entrega.json no generado aún")
    return json.loads(ENTREGA.read_text(encoding="utf-8"))


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def test_entrega_json_estructura(entrega: dict):
    assert entrega["kind"] == "entrega-cierre"
    assert entrega["reglas"]["config_version"].startswith("v3.0")
    assert entrega["distribucion"]["final_post_fix"] == {
        "PAGAR": 433, "NO_PAGAR": 22, "ESCALAR": 45,
    }
    assert entrega["impacto_fix_t18"]["reprocesados"] == 108
    # checklist de defensa en verde (T28)
    sim = entrega["checklist_defensa"]["simulacro"]
    assert sim["pass"] == 15 and sim["fail"] == 0


def test_sha256_de_los_entregables_cuadran(entrega: dict):
    if not DELIVERY.is_dir():
        pytest.skip("repo de entrega no montado en este nodo")
    for e in entrega["entregables"]:
        ruta = DELIVERY / e["file"]
        assert ruta.is_file(), e["file"]
        assert sha256(ruta) == e["sha256"], e["file"]


def test_repo_de_entrega_valido_y_sin_secretos(entrega: dict):
    if not DELIVERY.is_dir():
        pytest.skip("repo de entrega no montado en este nodo")
    presentes = sorted(p.name for p in DELIVERY.iterdir() if p.name != ".git")
    esperados = sorted(
        e["file"] for e in entrega["entregables"]
    )
    assert presentes == esperados, presentes
    assert set(ENTREGA and entrega["falta"]) <= set(CONTRATO)
    # higiene de secretos sobre TODO lo que va al repo de entrega
    for nombre in presentes:
        contenido = (DELIVERY / nombre).read_bytes()
        bajo = contenido.lower()
        assert b"apikey" not in bajo
        assert b"facturas2009" not in bajo
        assert b"sk-" not in bajo or nombre == "albertitos_plan.pdf"  # PDF binario comprimido
