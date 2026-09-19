"""T18 · El diff del reprocesado es EXACTAMENTE el esperado.

Esperado (ticket T18 + medida real): 86 NO_PAGAR→PAGAR (los 87 falsos del
T17 por importe, menos el duplicado FA-8801 que DEBE seguir sin pagar por
NO_DOUBLE_PAYMENT), los 14 genuinos y los 7 con otros FAIL se mantienen
NO_PAGAR, y 0 regresiones en el resto de los 500.
"""

from __future__ import annotations

import json
from pathlib import Path

PRE = Path(".sdd/metrics/outcomes-lote1.jsonl")  # ANTES (T14/T17, runner-1.0.0)
POST = Path(".sdd/metrics/outcomes-lote1-post-fix.jsonl")  # DESPUÉS (runner-1.1.0)
DIFF = Path(".sdd/metrics/impacto-fix-colapso.json")


def load(path: Path) -> dict[str, dict]:
    return {
        r["file_id"]: r
        for r in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())
    }


class TestDiffReprocesado:
    def test_diff_con_cero_regresiones(self):
        diff = json.loads(DIFF.read_text())
        resumen = diff["resumen"]
        assert resumen["regresiones"] == 0, "ningún resultado puede empeorar (ticket T18)"
        assert resumen["otros_cambios"] == 0, "solo los 108 NO_PAGAR afectados cambian"

    def test_exactamente_86_no_pagar_a_pagar(self):
        """87 falsos por importe (T17) − 1 duplicado que DEBE seguir sin pagar."""
        diff = json.loads(DIFF.read_text())
        resumen = diff["resumen"]
        assert resumen["no_pagar_a_pagar"] == 86
        desv = resumen["desviacion_esperada"]
        assert desv["delta"] == 1
        assert desv["files"] == ["factura_8801.pdf"]

    def test_cada_cambio_es_falso_no_pagar_del_t17(self):
        """Los archivos que giran a PAGAR son exactamente los falsos del T17."""
        diff = json.loads(DIFF.read_text())
        flip = {c["file_id"] for c in diff["cambios"] if c["despues"] == "PAGAR"}
        assert len(flip) == 86
        assert "2026-01-26_P007.pdf" in flip
        assert "factura_8801.pdf" not in flip
        pre = load(PRE)
        assert all(pre[f]["result"] == "NO_PAGAR" for f in flip)

    def test_genuinos_y_otros_se_mantienen(self):
        pre, post = load(PRE), load(POST)
        genuinos = (
            "2026-0811-B_catering.pdf",
            "2026-14500-C_informática.pdf",
            "F26-5240_ofimática.pdf",
        )
        for f in genuinos:
            assert pre[f]["result"] == post[f]["result"] == "NO_PAGAR"
        # 0 regresiones en los 392 que no son NO_PAGAR: byte a byte el mismo resultado
        for f, r in pre.items():
            if f not in genuinos and r["result"] != "NO_PAGAR":
                assert post[f]["result"] == r["result"], f"{f}: regreso no esperado"

    def test_distribucion_final_y_validador(self):
        post = load(POST)
        dist: dict[str, int] = {}
        for r in post.values():
            dist[r["result"]] = dist.get(r["result"], 0) + 1
        assert dist == {"PAGAR": 433, "NO_PAGAR": 22, "ESCALAR": 45}
        assert len(post) == 500
        diff = json.loads(DIFF.read_text())
        assert diff["validacion"] == "OK"
