"""T16 — UI contra el store REAL del lote 1 (formato del runner).

Fixture sintético en el FORMATO REAL (event=decision, rule_codes como cadena,
review.jsonl con campos+imágenes) — no depende de que exista el worktree de
W1. Además, si `.sdd/lote1` (→ /home/deploy/fleet/w1/.sdd) está disponible,
se prueba el store real truncado a 50 filas (rápido; nunca se copia a git ni
se escribe en él).
"""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from albertitos.ui.app import create_app
from albertitos.ui.ledger import estado_runner
from conftest import lote1_estado_real_presente

LOTE1 = Path(".sdd/lote1")  # symlink → /home/deploy/fleet/w1/.sdd (SOLO LECTURA)


# ----------------------------------------------------- fixture formato real


@pytest.fixture()
def lote_real_formato() -> Path:
    """Ledger en el formato REAL del runner (event=decision + rule_codes
    string) + review.jsonl (kind=fields con imágenes) + state/runner.json."""
    base = Path(".sdd") / "pytest-tmp" / "lote-fmt"
    if base.exists():
        shutil_rmtree(base)
    (base / "ledger").mkdir(parents=True)
    (base / "review-queue").mkdir(parents=True)
    (base / "state").mkdir(parents=True)

    decisiones = [
        ("A.pdf", "inv-a", "PAGAR", "NIF_IN_MASTER:PASS,TOTALS_MUST_MATCH:PASS"),
        ("B.pdf", "inv-b", "NO_PAGAR", "NIF_IN_MASTER:FAIL,PROVEEDOR_FANTASMA:FAIL"),
        ("C.pdf", "inv-c", "ESCALAR", "TOTALS_MUST_MATCH:PASS,IVA_CONSISTENT:UNKNOWN"),
        ("D.pdf", "inv-d", "ESCALAR", "NIF_IN_MASTER:PASS,NO_EMBEDDED_INSTRUCTIONS:UNKNOWN"),
        ("E.pdf", "inv-e", "PAGAR", "NIF_IN_MASTER:PASS,ORDER_PENDING:PASS"),
    ]
    with (base / "ledger" / "ledger.jsonl").open("w", encoding="utf-8") as fh:
        for file_id, iid, result, codes in decisiones:
            fh.write(
                json.dumps(
                    {
                        "config_version": "v3.0-2026-09-19",
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
    with (base / "review-queue" / "review.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "kind": "fields",
                    "invoice_id": "inv-c",
                    "file_id": "C.pdf",
                    "estado": "PENDIENTE",
                    "page": 1,
                    "fields": {
                        "lectura_pagina": [
                            {
                                "extractor": "vlm",
                                "value": "TOTAL 1210,00 EUR",
                                "confidence": 0.62,
                            },
                            {
                                "extractor": "cloud_vlm",
                                "value": "TOTAL 121,00 EUR",
                                "confidence": 0.71,
                            },
                        ]
                    },
                    "page_images": {"1": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="},
                }
            )
            + "\n"
        )
    (base / "state" / "runner.json").write_text(
        json.dumps(
            {
                "done": 5,
                "fallos": 0,
                "pendientes": 0,
                "total_archivos": 5,
                "files_per_second": 4.162,
                "resultados": {"PAGAR": 2, "NO_PAGAR": 1, "ESCALAR": 2},
                "config_version": "v3.0-2026-09-19",
                "engine_version": "runner-1.0.0",
                "rung4_llama_server": "up",
                "rung4_secuencial": True,
                "actualizado": "2026-09-18T23:52:49",
            }
        ),
        encoding="utf-8",
    )
    yield base
    shutil_rmtree(base)


def shutil_rmtree(base: Path) -> None:

    shutil.rmtree(base)


@pytest.fixture()
def cliente_lote(lote_real_formato: Path) -> TestClient:
    app = create_app(store_dir=lote_real_formato / "ledger")
    return TestClient(app)


# ------------------------------------------------------- pantallas demo-ready


def test_operaciones_con_estado_runner(lote_real_formato: Path):
    c = TestClient(create_app(store_dir=lote_real_formato / "ledger"))
    r = c.get("/")
    assert r.status_code == 200
    assert "Estado del runner" in r.text
    assert "4.162" in r.text  # files/s medido del runner.json
    assert "v3.0-2026-09-19" in r.text  # versión de reglas real
    assert "347" not in r.text  # los números son del fixture, no del lote 1


def test_facturas_filtro_y_busqueda():
    """Store real = objetivo móvil (W1 sigue escribiendo): consistencia interna."""
    if not lote1_estado_real_presente():
        pytest.skip(
            "estado real del lote 1 ausente en este worktree (.sdd/lote1 "
            "gitignored — provisioning T40F4); el test corre completo donde existe"
        )
    c = TestClient(create_app(store_dir=Path(".sdd/lote1/ledger")))
    assert c.get("/facturas").status_code == 200
    r = c.get("/facturas", params={"result": "ESCALAR"})
    assert r.status_code == 200
    assert "Escalar" in r.text
    tabla = r.text.split("<table>")[1].split("</table>")[0]
    assert "Pagar\n" not in tabla
    # búsqueda por file_id: solo resultados que contienen el patrón
    r = c.get("/facturas", params={"q": "2026-01-08_P001"})
    assert r.status_code == 200
    assert "2026-01-08_P001.pdf" in r.text
    assert "2026-01-11_P007.pdf" not in r.text
    # paginación: el total del propio render ⇒ páginas = ceil(total / 50)
    r1 = c.get("/facturas")
    total = int(
        r1.text.split("factura(s) — página ")[0].split("<p>")[-1].strip()
    )
    n_paginas = -(-total // 50)
    assert f"página 1 de {n_paginas}" in r1.text
    r2 = c.get("/facturas", params={"pagina": n_paginas})
    assert r2.status_code == 200
    assert f"página {n_paginas} / {n_paginas}" in r2.text


def test_revision_escalados_paginados():
    """El store real es un objetivo móvil (W1 puede seguir escribiendo): el
    test valida CONSISTENCIA INTERNA del render, no números congelados."""
    c = TestClient(create_app(store_dir=Path(".sdd/lote1/ledger")))
    r = c.get("/revision")
    assert r.status_code == 200
    n_cola = int(r.text.split("En cola: <strong>")[1].split("</strong>")[0])
    con_img = int(r.text.split("con imagen disponible: ")[1].split(" ")[0])
    n_paginas = int(r.text.split("página 1 de ")[1].split(".")[0])
    assert n_cola > 0 and n_paginas == -(-n_cola // 6)
    assert 0 <= con_img <= n_cola
    r2 = c.get("/revision", params={"pagina": n_paginas})
    assert r2.status_code == 200  # renderiza TODO sin bloquear
    # alguna página muestra imagen real de página (las hay: 24 entradas)
    alguna = any(
        "/revision/imagen/" in c.get("/revision", params={"pagina": p}).text
        for p in range(1, n_paginas + 1)
    )
    assert alguna or con_img == 0


def test_reglas_umbrales_reales_y_sin_confianza():
    if not lote1_estado_real_presente():
        pytest.skip(
            "estado real del lote 1 ausente en este worktree (.sdd/lote1 "
            "gitignored — provisioning T40F4); el test corre completo donde existe"
        )
    c = TestClient(create_app(store_dir=Path(".sdd/lote1/ledger")))
    r = c.get("/reglas")
    assert r.status_code == 200
    assert "v3.0-2026-09-19" in r.text  # versión real del snapshot
    r = c.get(
        "/reglas",
        params={"codigo": "DATE_VALID_NOT_FUTURE", "nuevo_umbral": "0.5"},
    )
    assert r.status_code == 200
    assert "Sin confianzas medidas" in r.text  # el runner no registra confianza


def test_salud_con_llama_y_drills():
    c = TestClient(create_app(store_dir=Path(".sdd/lote1/ledger")))
    r = c.get("/salud")
    assert r.status_code == 200
    assert "up" in r.text  # llama-server medido por el runner
    assert "4 pass / 0 fail" in r.text  # drills T12


def test_override_lote_va_al_sdd_local_jamas_al_store_externo(lote_real_formato: Path):
    """El store del lote es SOLO LECTURA: los overrides van al .sdd local."""
    app = create_app(store_dir=lote_real_formato / "ledger")
    destino = Path(app.state.override_dir)
    assert not str(destino.resolve()).startswith(str(lote_real_formato.resolve()))
    r = TestClient(app).post(
        "/revision/inv-c/resolver",
        data={"file_id": "C.pdf", "campo": "total", "valor": "121,00 EUR", "nota": "dígito de más"},
    )
    assert r.status_code == 200
    assert "121,00 EUR" in TestClient(app).get("/revision").text
    # limpiar la cola local creada por la prueba
    cola = Path(".sdd/review-queue/overrides.jsonl")
    if cola.exists():
        lineas = [
            x for x in cola.read_text(encoding="utf-8").splitlines() if "inv-c" not in x
        ]
        cola.write_text(("\n".join(lineas) + "\n") if lineas else "", encoding="utf-8")


def test_estado_runner_si_existe(lote_real_formato: Path):
    e = estado_runner(lote_real_formato / "ledger")
    assert e is not None
    assert e["done"] == "5"
    assert e["resultados"]["ESCALAR"] == "2"


# ------------------------------------------- store REAL truncado (si existe)


@pytest.mark.skipif(
    not Path(".sdd/lote1/ledger/ledger.jsonl").is_file(),
    reason="store real del lote 1 no disponible en este nodo",
)
def test_store_real_truncado_50_filas():
    """Fixture del ledger real truncado a 50 filas para velocidad (no se copia a git)."""
    base = Path(".sdd") / "pytest-tmp" / "lote1-truncado"
    if base.exists():
        shutil_rmtree(base)
    (base / "ledger").mkdir(parents=True)
    origen = Path(".sdd/lote1/ledger/ledger.jsonl")
    todas = origen.read_text(encoding="utf-8").splitlines()
    # corte representativo: las primeras 20 + 30 ESCALAR (de los 45 reales)
    # + las filas del ledger de los invoice_id que SÍ tienen entrada en la
    # cola de revisión real (con imagen), para que el join decida↔campos encuentre
    escaladas = [x for x in todas if '"result": "ESCALAR"' in x][:30]
    rev = Path(".sdd/lote1/review-queue/review.jsonl")
    iids_rev: set[str] = set()
    if rev.is_file():
        iids_rev = {
            json.loads(x).get("invoice_id", "")
            for x in rev.read_text(encoding="utf-8").splitlines()
        }
    de_cola = [x for x in todas if json.loads(x).get("invoice_id") in iids_rev]
    lineas = list(dict.fromkeys(todas[:20] + escaladas + de_cola))
    # garantiza que los 3 primeros ítems de revisión (con imagen) tienen su
    # decisión en el ledger truncado — si el corte anterior los dejó fuera,
    # añade sus filas explícitamente
    rev_items = [
        json.loads(x) for x in (rev.read_text().splitlines() if rev.is_file() else [])
    ]
    iids_necesarios = {str(i.get("invoice_id", "")) for i in rev_items[:3]}
    presentes = {json.loads(x).get("invoice_id") for x in lineas}
    for iid in sorted(iids_necesarios - presentes):
        fila = next((x for x in todas if json.loads(x).get("invoice_id") == iid), None)
        if fila:
            lineas.append(fila)
    lineas = lineas[:50]
    (base / "ledger" / "ledger.jsonl").write_text(
        "\n".join(lineas) + "\n", encoding="utf-8"
    )
    # filas de la cola de revisión real cuyos invoice_id están garantizados
    # en el ledger truncado (ver arriba) — hasta 3 con imagen real
    (base / "review-queue").mkdir()
    if rev.is_file():
        rev_lineas = [
            x
            for x in rev.read_text(encoding="utf-8").splitlines()
            if json.loads(x).get("invoice_id") in iids_rev
        ][:3]
        (base / "review-queue" / "review.jsonl").write_text(
            ("\n".join(rev_lineas) + "\n") if rev_lineas else "",
            encoding="utf-8",
        )
    try:
        c = TestClient(create_app(store_dir=base / "ledger"))
        for ruta in ("/", "/facturas", "/revision", "/reglas", "/salud"):
            assert c.get(ruta).status_code == 200, ruta
        texto = c.get("/facturas").text
        assert "2026-01-08_P001.pdf" in texto  # file_id EXACTO del lote real
        r = c.get("/revision")
        assert "En cola: <strong>" in r.text
        # imágenes de página si la cola de revisión real las conserva; si W1
        # la vació (post-reprocesado), la degradación honesta se muestra
        rev_real = Path(".sdd/lote1/review-queue/review.jsonl")
        con_imagen = any(
            "/revision/imagen/" in c.get("/revision", params={"pagina": p}).text
            for p in range(1, 9)
        )
        assert con_imagen or "Sin imagen almacenada" in c.get("/revision").text
        del rev_real
    finally:
        shutil_rmtree(base)
