"""Tests de T13: reprocesado dirigido, diff de impacto, regla v4 como datos."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from albertitos.emit import emit_outcomes
from albertitos.reprocess import (
    RUN_BASE,
    ReprocessConfig,
    apply_master_patch,
    load_patch,
    reprocesar,
    write_impact,
)
from albertitos.rules import load_config, load_master
from albertitos.run import Runner, RunnerConfig
from albertitos.store import Store
from conftest import FIXTURES

FECHA_REF = "2026-09-19"
RULES_V3 = Path("src/albertitos/rules/regla_v3.yaml")
RULES_V4 = Path("src/albertitos/rules/regla_v4.yaml")
LOTE10 = FIXTURES / "lote10"
MAESTRO10 = FIXTURES / "maestro_lote10.xlsx"


def _cfg_fecha():
    return load_config(RULES_V3, fecha_referencia=FECHA_REF)


def _lote10_en(tmp_path: Path) -> Path:
    dst = tmp_path / "pdfs"
    dst.mkdir(parents=True, exist_ok=True)
    for f in sorted(LOTE10.glob("*.pdf")):
        shutil.copy(f, dst / f.name)
    return dst


def _base_run(tmp_path: Path, pdfs: Path) -> None:
    """Corre el lote completo con la v3 y emite outcomes.jsonl."""
    cfg = RunnerConfig(
        facturas_dir=pdfs,
        outcomes_path=tmp_path / "outcomes.jsonl",
        store_root=tmp_path / ".sdd",
        rules_yaml=RULES_V3,
        master_path=MAESTRO10,
        fecha_referencia=FECHA_REF,
        use_rung4=False,
    )
    Runner(cfg).run()
    emit_outcomes(Store(tmp_path / ".sdd"), tmp_path / "outcomes.jsonl")


# ---------------------------------------------------------------- v4 datos


def test_v4_desactivada_es_noop_exacto_de_v3():

    from test_rules import IBAN_P002, _decide, _fields  # noqa: F401

    fields = _fields()
    d3 = _decide(fields)
    v4 = load_config(RULES_V4, fecha_referencia=FECHA_REF)
    d4 = _decide(fields, cfg=v4)
    assert d3.result == d4.result == "PAGAR"
    codes3 = [v.code for v in d3.rule_verdicts]
    codes4 = [v.code for v in d4.rule_verdicts]
    assert codes3 == codes4  # sin REGLA_V4 en el set activo
    assert "REGLA_V4" not in codes4
    assert v4.reglas_pendientes == ("REGLA_V4",)


def test_v4_activada_cambia_lo_esperado(tmp_path):
    """activa: true en el yaml = cambio de DATOS; el motor no cambia."""
    activo = tmp_path / "regla_v4_activa.yaml"
    texto = RULES_V4.read_text()
    activo.write_text(texto.replace("activa: false", "activa: true"))

    from test_rules import _decide, _fields

    fields = _fields()  # total 4635.26 > mínimo
    fields_baja = _fields(total=5.00, base=4.13, iva_amount=0.87,
                          pedido="PO-2026-0177")
    d_alta = _decide(fields, cfg=load_config(activo, fecha_referencia=FECHA_REF))
    d_baja = _decide(fields_baja,
                     cfg=load_config(activo, fecha_referencia=FECHA_REF))
    assert d_alta.result == "PAGAR"  # por encima del mínimo
    assert d_baja.result == "ESCALAR"  # total < importe_minimo ⇒ anomalía
    codes = [v.code for v in d_baja.rule_verdicts if v.outcome == "UNKNOWN"]
    assert "REGLA_V4" in codes


def test_v4_parametros_son_datos(tmp_path):
    """El umbral de REGLA_V4 vive en el yaml: cambiarlo no toca código."""
    activo = tmp_path / "regla_v4_min100.yaml"
    activo.write_text(RULES_V4.read_text().replace("activa: false",
                                                   "activa: true")
                      .replace("importe_minimo: 10.0", "importe_minimo: 100.0"))

    from test_rules import _decide, _fields

    cfg100 = load_config(activo, fecha_referencia=FECHA_REF)
    d = _decide(_fields(total=50.00, base=41.32, iva_amount=8.68,
                        pedido="PO-2026-0177"), cfg=cfg100)
    assert d.result == "ESCALAR"  # 50 < 100 con el yaml ajustado
    assert cfg100.params_for("REGLA_V4")["importe_minimo"] == 100.0


# ---------------------------------------------------------------- parche


def test_patch_valida_y_aplica_en_memoria():
    patch = load_patch(FIXTURES / "patch_po.yaml")
    master = load_master(MAESTRO10, hojas_ignoradas=load_config(
        RULES_V3, fecha_referencia=FECHA_REF).hojas_ignoradas)
    ped = min(patch["pedidos"])
    importe_antes = master.pedidos[ped].importe
    parcheado, resumen = apply_master_patch(master, patch)
    assert parcheado.pedidos[ped].importe == 1.00
    assert parcheado.pedidos[ped].importe != importe_antes
    assert parcheado.sha256 == master.sha256  # el Excel NO cambia
    assert resumen["pedidos"][ped]["antes"]["importe"] == importe_antes
    # maestro original intacto (inmutabilidad)
    assert master.pedidos[ped].importe == importe_antes


def test_patch_rechaza_campos_desconocidos(tmp_path):
    p = tmp_path / "malo.yaml"
    p.write_text("proveedores:\n  P001:\n    password: hola\n")
    try:
        load_patch(p)
    except ValueError as e:
        assert "campos desconocidos" in str(e)
    else:
        raise AssertionError("debería rechazar campos desconocidos")


# ---------------------------------------------------------------- integración


def _patch_pedidos_usados():
    """El pedido del parche es el primero del lote10 (con 1 sola factura)."""
    import yaml

    data = yaml.safe_load((FIXTURES / "patch_po.yaml").read_text())
    return next(iter(data["pedidos"]))


def test_reprocesado_dirigido_diff_exacto(tmp_path):
    """Cambia UN importe del maestro ⇒ el diff muestra EXACTAMENTE las
    facturas que cruzan con ese pedido y ninguna otra."""
    pdfs = _lote10_en(tmp_path)
    _base_run(tmp_path, pdfs)
    store = Store(tmp_path / ".sdd")
    ped = _patch_pedidos_usados()
    antes = {d.file_id: d.result for d in store.run_decisions(RUN_BASE)}
    con_ese_pedido = [f for f, r in antes.items()
                      if (store.decision_for(f).pedido == ped)]
    assert len(con_ese_pedido) == 1  # pedido único en el lote10
    n_escalados_antes = sum(1 for r in antes.values() if r == "ESCALAR")
    store.close()

    cfg = ReprocessConfig(
        facturas_dir=pdfs,
        store_root=tmp_path / ".sdd",
        rules_yaml=RULES_V3,
        master_path=MAESTRO10,
        fecha_referencia=FECHA_REF,
        patch_path=FIXTURES / "patch_po.yaml",
        patch=load_patch(FIXTURES / "patch_po.yaml"),
        run_id="repro-patch",
        use_rung4=False,
        outcomes_path=tmp_path / "outcomes.jsonl",
    )
    impacto = reprocesar(cfg)
    afectados_diff = [c["file_id"] for c in impacto["cambios"]]
    assert impacto["resumen"]["objetivo"] == 1
    assert afectados_diff == con_ese_pedido
    assert set(afectados_diff) == set(afectados_diff)  # sin duplicados
    # el resto del lote no se tocó (nº afectados = nº que cruza)
    assert impacto["resumen"]["afectados"] >= 1
    assert impacto["resumen"]["escalados_despues"] >= n_escalados_antes


def test_reprocesado_determinista_mismo_parche_mismo_diff(tmp_path):
    pdfs = _lote10_en(tmp_path)
    _base_run(tmp_path, pdfs)
    def _cfg():
        return ReprocessConfig(
            facturas_dir=pdfs,
            store_root=tmp_path / ".sdd",
            rules_yaml=RULES_V3,
            master_path=MAESTRO10,
            fecha_referencia=FECHA_REF,
            patch_path=FIXTURES / "patch_po.yaml",
            patch=load_patch(FIXTURES / "patch_po.yaml"),
            run_id="repro-det",
            use_rung4=False,
            outcomes_path=tmp_path / "outcomes.jsonl",
        )

    i1 = reprocesar(_cfg())
    i2 = reprocesar(_cfg())
    import json

    j1 = json.dumps(i1, sort_keys=True)
    j2 = json.dumps(i2, sort_keys=True)
    assert j1 == j2  # mismo parche ⇒ mismo diff byte a byte


def test_historico_coexiste_jamas_sobreescribe(tmp_path):
    pdfs = _lote10_en(tmp_path)
    _base_run(tmp_path, pdfs)
    store = Store(tmp_path / ".sdd")
    antes = {d.file_id: d.result for d in store.run_decisions(RUN_BASE)}
    store.close()
    reprocesar(ReprocessConfig(
        facturas_dir=pdfs, store_root=tmp_path / ".sdd",
        rules_yaml=RULES_V3, master_path=MAESTRO10,
        fecha_referencia=FECHA_REF,
        patch_path=FIXTURES / "patch_po.yaml",
        patch=load_patch(FIXTURES / "patch_po.yaml"),
        run_id="repro-hist", use_rung4=False,
        outcomes_path=tmp_path / "outcomes.jsonl",
    ))
    store = Store(tmp_path / ".sdd")
    assert "repro-hist" in store.run_ids()
    assert RUN_BASE in store.run_ids()
    despues_base = {d.file_id: d.result for d in store.run_decisions(RUN_BASE)}
    despues_repro = {d.file_id: d.result for d in store.run_decisions("repro-hist")}
    # el run base sigue intacto (jamás se sobreescribe)
    assert despues_base == antes
    # y el diff del histórico muestra EXACTAMENTE el cambio del pedido tocado
    comunes = set(despues_base) & set(despues_repro)
    cambiados = [f for f in comunes if despues_base[f] != despues_repro[f]]
    assert len(cambiados) == 1
    store.close()


def test_diff_y_reporte_legibles(tmp_path):
    pdfs = _lote10_en(tmp_path)
    _base_run(tmp_path, pdfs)
    impacto = reprocesar(ReprocessConfig(
        facturas_dir=pdfs, store_root=tmp_path / ".sdd",
        rules_yaml=RULES_V3, master_path=MAESTRO10,
        fecha_referencia=FECHA_REF,
        patch_path=FIXTURES / "patch_po.yaml",
        patch=load_patch(FIXTURES / "patch_po.yaml"),
        run_id="repro-diff", use_rung4=False,
        outcomes_path=tmp_path / "outcomes.jsonl",
    ))
    json_path, txt_path = write_impact(impacto, tmp_path / "metrics")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["run_base"] == RUN_BASE and data["run_nuevo"] == "repro-diff"
    for c in data["cambios"]:
        assert c["antes"] in ("PAGAR", "NO_PAGAR", "ESCALAR")
        assert c["despues"] in ("PAGAR", "NO_PAGAR", "ESCALAR", "AUSENTE")
        assert c["regla"]
    reporte = txt_path.read_text(encoding="utf-8")
    assert "IMPACTO DEL REPROCESADO" in reporte
    assert "afectados:" in reporte
    if data["cambios"]:
        assert data["cambios"][0]["file_id"] in reporte


def test_reprocesar_sin_objetivo_falla_con_mensaje(tmp_path):
    pdfs = _lote10_en(tmp_path)
    _base_run(tmp_path, pdfs)
    try:
        reprocesar(ReprocessConfig(
            facturas_dir=pdfs, store_root=tmp_path / ".sdd",
            rules_yaml=RULES_V3, master_path=MAESTRO10,
            fecha_referencia=FECHA_REF, run_id="vacio",
            use_rung4=False, outcomes_path=tmp_path / "outcomes.jsonl",
        ))
    except ValueError as e:
        assert "nada que reprocesar" in str(e)
    else:
        raise AssertionError("debería fallar sin objetivos")


def test_all_scaled_reprocesa_los_escalados(tmp_path):
    pdfs = _lote10_en(tmp_path)
    shutil.copy(FIXTURES / "scans" / "scan_001.pdf", pdfs / "scan_001.pdf")
    _base_run(tmp_path, pdfs)
    store = Store(tmp_path / ".sdd")
    escalados = [
        d.file_id for d in store.run_decisions(RUN_BASE)
        if d.result == "ESCALAR"
    ]
    store.close()
    assert escalados, "el lote10 debe tener al menos un ESCALAR en base"
    impacto = reprocesar(ReprocessConfig(
        facturas_dir=pdfs, store_root=tmp_path / ".sdd",
        rules_yaml=RULES_V3, master_path=MAESTRO10,
        fecha_referencia=FECHA_REF,
        all_scaled=True, run_id="repro-scaled", use_rung4=False,
        outcomes_path=tmp_path / "outcomes.jsonl",
    ))
    assert impacto["resumen"]["objetivo"] == len(escalados)
    assert impacto["resumen"]["reprocesados"] == len(escalados)


# ---------------------------------------------------------------- helpers


def scaled_files(store: Store, pdfs: set[str]) -> tuple[str, ...]:
    from albertitos.reprocess import scaled_files as _sf

    return _sf(store, pdfs)
