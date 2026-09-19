"""T22 · Auditoría POST-fix: trampas VERDE, provenance de los 86 y lote1.json.

Los artefactos commiteados (auditoria-postfix.json/md, lote1.json, snapshot
outcomes-lote1-post-fix.jsonl) se generan con tools/audit_postfix.py y
tools/lote1_metrics.py desde el store real; el test congela sus invariantes.
"""

from __future__ import annotations

import json
from pathlib import Path

POSTFIX_MD = Path(".sdd/metrics/auditoria-postfix.md")
POSTFIX_JSON = Path(".sdd/metrics/auditoria-postfix.json")
SNAPSHOT = Path(".sdd/metrics/outcomes-lote1-post-fix.jsonl")
LOTE1 = Path(".sdd/metrics/lote1.json")


class TestProvenanceDeLos86:
    def test_estado_verde_y_cero_fallas(self):
        d = json.loads(POSTFIX_JSON.read_text())
        assert d["estado"] == "VERDE"
        assert d["fallas_provenance"] == []
        assert d["n_nuevos_pagar"] == 86  # 87 falsos T17 − 1 duplicado (§6)

    def test_muestra_de_20_con_tolerancia_respetada(self):
        d = json.loads(POSTFIX_JSON.read_text())
        muestra = d["muestra_provenance"]
        assert len(muestra) == 20
        for m in muestra:
            assert m["matchea_tolerancia"] is True
            assert abs(float(m["candidato_elegido"]) - float(m["importe_maestro"])) <= 0.01
            assert m["extractor"]  # provenance: quién produjo el candidato
            assert m["feature_ref"]  # provenance: feature que lo produjo


class TestGenuinosSinRegresion:
    def test_14_genuinos_se_mantienen_no_pagar(self):
        d = json.loads(POSTFIX_JSON.read_text())
        assert d["genuinos_verificados"] == 14
        assert d["genuinos_esperados"] == 14

    def test_distribucion_de_los_22_no_pagar(self):
        d = json.loads(POSTFIX_JSON.read_text())
        dist = d["distribucion_no_pagar"]
        # 22 archivos; los códigos coexisten (un archivo puede fallar varias reglas)
        assert dist["ORDER_AMOUNT_MATCHES"] == 14
        assert dist["IBAN_MATCHES_MASTER"] == 7
        assert dist["IVA_CONSISTENT"] == 6
        assert dist["TOTALS_MUST_MATCH"] == 3
        assert dist["NO_DOUBLE_PAYMENT"] == 2
        # y suman 22 archivos con ≥1 FAIL
        res = {
            r["file_id"]: r
            for r in (json.loads(l) for l in SNAPSHOT.read_text().splitlines() if l.strip())
        }
        con_fail = sum(
            1 for r in res.values() if r["result"] == "NO_PAGAR"
            and any(c.endswith("FAIL") for c in r["rule_ids"])
        )
        assert con_fail == 22


class TestLote1Schema:
    def test_lote1_describe_las_500(self):
        lote = json.loads(LOTE1.read_text())
        assert lote["n_archivos"] == 500
        assert lote["distribucion"] == {"PAGAR": 433, "NO_PAGAR": 22, "ESCALAR": 45}
        assert sum(lote["distribucion"].values()) == 500
        assert lote.get("files_per_s")  # medido en la corrida completa
        assert lote.get("fallos", 0) == 0 or lote.get("validador") == "OK"

    def test_rungs_invocados_medidos(self):
        lote = json.loads(LOTE1.read_text())
        rungs = lote["rungs_invocados"]
        assert rungs["rung1_pdf_text"] == 471
        assert rungs["unresolved"] == 29  # los 29 raster agotaron la escalera
        assert sum(rungs.values()) == 500

    def test_diff_del_subset_va_separado(self):
        """El schema de impacto no se mezcla con el de lote1/auditoría."""
        diff = json.loads(Path(".sdd/metrics/impacto-fix-colapso.json").read_text())
        assert diff["kind"] == "impacto-fix-colapso"
        lote = json.loads(LOTE1.read_text())
        assert "impacto" not in lote
        assert lote.get("reproceso_t18", {}).get("diff") is None


class TestTablaVerdeRojo:
    def test_todas_las_trampas_verde_en_el_md(self):
        md = POSTFIX_MD.read_text()
        assert "## Veredicto: VERDE" in md
        # las trampas citan su estado
        for fila in ("3 proveedores fantasma", "Duplicado FA-8801",
                     "Instrucciones embebidas", "26 scan_*.pdf"):
            assert fila in md
        assert "VERDE" in md
        assert "## Veredicto: ROJO" not in md
