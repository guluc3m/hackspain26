"""T31 — telemetría continua: stats por rung, stats VLM, sonda y cadena encadenada.

Sin red (la sonda down ⇒ «sin datos») y ficheros bajo `.sdd/` (estado de
trabajo jamás en /tmp).
"""

import json
import shutil
from pathlib import Path

import pytest

from albertitos.telemetria import (
    EventChain,
    sonda_llama,
    stats_por_rung,
    stats_vlm,
)


@pytest.fixture()
def registros() -> list[dict]:
    """Filas de evidencia reales (formato ledger) con un rung 5 con coste."""
    def ev(stage, extractor, lat, outcome, cfg="v3.0", cost=None, detail="d"):
        rec = {
            "kind": "evidence", "invoice_id": "X", "stage": stage,
            "extractor": extractor, "extractor_version": "v", "config_version": cfg,
            "sha256": "0" * 64, "latency_ms": lat, "confidence": None,
            "outcome": outcome, "detail": detail,
        }
        if cost is not None:
            rec["cost_eur"] = cost
        return rec

    return [
        ev("extract:rung1_pdf_text", "pypdf", 100, "ok"),
        ev("extract:rung1_pdf_text", "pypdf", 300, "ok"),
        ev("extract:rung1_pdf_text", "pypdf", 0, "skipped:sin_texto"),
        ev("extract:rung3_tesseract", "tesseract", 2000, "ok"),
        ev("extract:rung3_tesseract", "tesseract", 4000, "ok"),
        ev("extract:rung3_tesseract", "tesseract", 0, "error", detail="http 500"),
        ev("extract:rung4_vlm", "vlm", 15000, "ok"),
        ev("extract:rung5_cloud_vlm", "cloud_vlm", 1500, "ok", detail="cache miss"),
        ev("extract:rung5_cloud_vlm", "cloud_vlm", 0, "skipped:sin_credenciales"),
    ]


# ------------------------------------------------------------------ escalera


def test_escalera_medidas_exactas(registros):
    stats = stats_por_rung(registros)
    h = stats["ventanas"]["historico"]["rungs"]
    # rung1: 2 ejecuciones con latencia (100, 300) + 1 skipped
    r1 = h["rung1"]
    assert r1["n"] == 3 and r1["p50_ms"] == 300.0 and r1["p95_ms"] == 300.0
    assert r1["ratio_descarte"] == round(100 * 1 / 3, 1)
    # rung3: 2 latencias + 1 error (el error no añade latencia)
    r3 = h["rung3"]
    assert r3["n"] == 3 and r3["errores"] == 1 and r3["p50_ms"] == 4000.0
    # % de filas consumidas por rung sobre el total de filas (9):
    # rung1 3/9, rung3 3/9, rung4 1/9, rung5 2/9
    assert h["rung1"]["pct_filas"] == round(100 * 3 / 9, 1)
    assert h["rung5"]["pct_filas"] == round(100 * 2 / 9, 1)


def test_escalera_ventanas(registros):
    """Corrida actual = config_version de la ÚLTIMA fila (append-only)."""
    stats = stats_por_rung(registros)
    corrida = stats["ventanas"]["corrida_actual"]["rungs"]
    # la última fila es rung5 skipped ⇒ corrida actual solo tiene esa config
    assert "rung5" in corrida
    # sin timestamps en las filas ⇒ «última hora» sin datos, no inventados
    hora = stats["ventanas"]["ultima_hora"]
    assert hora["rungs"] == {} and hora["sin_timestamps"] == len(registros)
    # con timestamps sí calcula la ventana
    con_ts = [{**r, "timestamp": 0.0} for r in registros]
    stats_ts = stats_por_rung(con_ts, ahora=100000.0)
    assert stats_ts["ventanas"]["ultima_hora"]["rungs"] == {}  # fuera de hora
    con_ts_reciente = [{**r, "timestamp": 999999.0} for r in registros]
    stats2 = stats_por_rung(con_ts_reciente, ahora=999999.0 + 10)
    assert stats2["ventanas"]["ultima_hora"]["total_filas"] > 0


def test_escalera_coste_rung5_con_formula_t9(registros):
    """Rung 5 sin cost_eur ⇒ nº llamadas × precio (fórmula T9 intacta)."""
    stats = stats_por_rung(registros)
    r5 = stats["ventanas"]["historico"]["rungs"]["rung5"]
    # 1 llamada emitida (la skipped no factura) × 0.004 EUR
    assert r5["coste_eur"] == 0.004
    # con cost_eur presente, se usa el medido (2 filas × 0.01) + la fórmula
    con_coste = registros + [
        {**r, "cost_eur": 0.01}
        for r in registros if r["stage"] == "extract:rung5_cloud_vlm"
    ]
    stats2 = stats_por_rung(con_coste)
    assert stats2["ventanas"]["historico"]["rungs"]["rung5"]["coste_eur"] == round(0.02 + 0.004, 4)


# --------------------------------------------------------------------- VLM


def test_stats_vlm_por_componente(registros):
    vlm = stats_vlm(registros)
    r4 = vlm["rung4_llama_server"]
    assert r4["n_invocaciones"] == 1 and r4["latencia_media_ms"] == 15000.0
    assert r4["coste_eur"]["valor"] == "0.0000 EUR (local)"
    r5 = vlm["rung5_cloud"]
    # 1 llamada emitida, 0 cacheadas ⇒ facturable 1 × precio
    assert r5["n_invocaciones"] == 1 and r5["cache_miss"] == 1
    assert r5["coste_eur"]["etiqueta"] == "medido×precio estimado"
    # con 1 invocación sin truncado ⇒ 0.0 % MEDIDO (no None)
    assert r5["tasa_truncado"] == 0.0


def test_stats_vlm_cache_y_truncado(registros):
    filas = registros + [
        {**r, "detail": "cache hit", "outcome": "ok"}
        for r in registros
        if r["stage"] == "extract:rung5_cloud_vlm" and r["outcome"] == "ok"
    ] + [
        {**r, "detail": "salida truncada: 200 tokens", "outcome": "truncated"}
        for r in registros if r["stage"] == "extract:rung5_cloud_vlm"
    ]
    vlm = stats_vlm(filas)
    r5 = vlm["rung5_cloud"]
    assert r5["cache_hit"] == 1  # el hit registrado
    assert r5["tasa_truncado"] is not None


def test_stats_vlm_sin_datos(registros):
    vacio = [r for r in registros if "rung4" not in r["stage"] and "rung5" not in r["stage"]]
    vlm = stats_vlm(vacio)
    assert vlm["rung4_llama_server"]["etiqueta"] == "sin datos"
    assert vlm["rung4_llama_server"]["n_invocaciones"] == 0


# --------------------------------------------------------------------- sonda


def test_sonda_down_no_inventa():
    s = sonda_llama("http://127.0.0.1:1", timeout_s=0.5)
    assert s["estado"] == ("down", "medido")
    assert "modelo" not in s  # sin datos, jamás ceros falsos


# ----------------------------------------------------------------- EventChain


def test_cadena_encadenada_y_verificacion(tmp_path: Path):
    cadena = EventChain(tmp_path / "actividad.jsonl")
    cadena.append("override-revision", {"file_id": "a.pdf"})
    cadena.append("anotacion-humana", {"nota": "mirar G.pdf"})
    cadena.append("corrida-lote2", {"n": 40})
    verif = cadena.verificar()
    assert verif["integra"] is True and verif["n"] == 3
    eventos = cadena.leer()
    # cada evento sella el hash del anterior
    assert eventos[1]["prev_hash"] == eventos[0]["hash"]
    assert eventos[2]["prev_hash"] == eventos[1]["hash"]


def test_cadena_dela_a_la_manipulacion(tmp_path: Path):
    """Alterar un evento intermedio rompe la verificación (trazabilidad total)."""
    cadena = EventChain(tmp_path / "actividad.jsonl")
    cadena.append("e1")
    cadena.append("e2")
    cadena.append("e3")
    ruta = tmp_path / "actividad.jsonl"
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    manipulada = json.loads(lineas[1])
    manipulada["evento"] = "MANIPULADO"
    lineas[1] = json.dumps(manipulada, ensure_ascii=False)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    verif = cadena.verificar()
    assert verif["integra"] is False and verif["roto_en_seq"] == 2


# ------------------------------------------------------- UI: Operaciones/Actividad


def test_operaciones_con_escalera_y_actividad():
    from fastapi.testclient import TestClient

    from albertitos.ui.app import create_app

    base = Path(".sdd") / "pytest-tmp" / "telemetria"
    if base.exists():
        shutil.rmtree(base)
    (base / "lote1" / "ledger").mkdir(parents=True)
    (base / "lote1" / "ledger" / "ledger.jsonl").write_text(
        json.dumps({"config_version": "v3.0-t", "event": "decision", "file_id": "A.pdf",
                    "invoice_id": "inv-A", "result": "PAGAR", "rule_codes": "X:PASS",
                    "sha256": "0" * 64}) + "\n"
        + json.dumps({"config_version": "v3.0-t", "event": "decision", "file_id": "B.pdf",
                      "invoice_id": "inv-B", "result": "ESCALAR", "rule_codes": "Y:UNKNOWN",
                      "sha256": "1" * 64}) + "\n",
        encoding="utf-8",
    )
    c = TestClient(create_app(store_dir=base / "lote1" / "ledger"))
    r = c.get("/")
    assert r.status_code == 200
    assert "¿Quién lee cada factura" in r.text and "Los lectores con IA" in r.text
    assert "medido" in r.text
    # pantalla Actividad con la cadena
    r2 = c.get("/actividad")
    assert r2.status_code == 200 and "Cadena íntegra" in r2.text
    r3 = c.post("/actividad/anotar", data={"nota": "mirar B.pdf"})
    assert r3.status_code == 200
    assert "anotacion-humana" in c.get("/actividad").text
    # el override en Revisión también queda sellado en la cadena
    c.post("/revision/inv-B/resolver", data={"file_id": "B.pdf", "campo": "total", "valor": "121"})
    assert "override-revision" in c.get("/actividad").text
    shutil.rmtree(base)


def test_impacto_loader_unificado():
    """T38-S8: acepta el schema T18 y el T13; ninguno ⇒ None."""
    from albertitos.ui.ledger import leer_impactos

    base = Path(".sdd") / "pytest-tmp" / "impacto-loader"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    try:
        assert leer_impactos(base) is None  # sin datos ⇒ None, no ceros
        # schema T18 (real hoy)
        (base / "impacto-fix-colapso.json").write_text(
            json.dumps({"reprocesados": 108, "resumen": {"no_pagar_a_pagar": 86, "regresiones": 0},
                        "validacion": "OK"}),
            encoding="utf-8",
        )
        d = leer_impactos(base)
        assert d["fuente"] == "impacto-fix-colapso.json"
        assert d["reprocesados"] == "108" and d["cambios"] == "86" and d["regresiones"] == "0"
        # schema T13 (futuro lote 2): manda si existe
        (base / "impacto.json").write_text(
            json.dumps({"resumen": {"cambios": 12, "regresiones": 1}, "validacion": "OK"}),
            encoding="utf-8",
        )
        d2 = leer_impactos(base)
        assert d2["fuente"] == "impacto.json" and d2["cambios"] == "12"
        # y en la UI: la pantalla Actividad lo muestra
        from fastapi.testclient import TestClient

        from albertitos.ui.app import create_app

        app = create_app(records=[])
        r = TestClient(app).get("/actividad")
        assert "Último reprocesado" in r.text and "108" in r.text
    finally:
        shutil.rmtree(base)
