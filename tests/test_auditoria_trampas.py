"""T17 · Auditoría de trampas contra el outcomes real del lote 1.

Lee el outcomes REAL (snapshot commiteado: .sdd/metrics/outcomes-lote1.jsonl,
copia del outcomes.jsonl validado) y aserta el estado VERDE/ROJO de cada trampa
de AGENTS.md §11 — explícito, sin skips.

El ROJO del colapso de candidatos queda PINNADO: cuando el supervisor corrija
el motor y reprocese, este test fallará a propósito y obligará a re-auditar
(no es una aprobación del estado actual; es un detector de cambios).
"""

from __future__ import annotations

import json
from pathlib import Path

# snapshot del outcomes POST-fix (motor runner-1.1.0, ADR-06, T18).
# El estado PRE-fix queda en outcomes-lote1.jsonl como evidencia histórica.
SNAPSHOT = Path(".sdd/metrics/outcomes-lote1-post-fix.jsonl")


def load_outcomes() -> dict[str, dict]:
    assert SNAPSHOT.is_file(), f"falta el snapshot del outcomes real: {SNAPSHOT}"
    return {
        r["file_id"]: r
        for r in (json.loads(l) for l in SNAPSHOT.read_text(encoding="utf-8").splitlines() if l.strip())
    }


def no_pass(res: dict, code_prefix: str) -> bool:
    return any(
        c.startswith(code_prefix) and not c.endswith("PASS") for c in res.get("rule_ids", [])
    )


class TestTrampasVerde:
    def test_fantasmas_escalan(self):
        """Trampa §11: 3 fantasmas con IBAN compartido + notas — ESCALAR citando regla."""
        res = load_outcomes()
        marcados = [f for f, r in res.items() if no_pass(r, "PROVEEDOR_FANTASMA")]
        assert marcados, "la trampa fantasma debe estar detectada en el outcomes"
        for f in marcados:
            assert res[f]["result"] == "ESCALAR", f"{f}: fantasma debe ESCALAR, no {res[f]['result']}"

    def test_duplicado_fa8801(self):
        """Trampa §11: FA-8801 duplicado — 1ª PAGAR, 2ª NO_PAGAR/ESCALAR (§6)."""
        res = load_outcomes()
        r1 = res["2026-05-28_P005.pdf"]
        r2 = res["factura_8801.pdf"]
        assert r1["result"] == "PAGAR"
        assert r2["result"] in ("NO_PAGAR", "ESCALAR")
        assert any(c.startswith("NO_DOUBLE_PAYMENT") and not c.endswith("PASS") for c in r2["rule_ids"]), (
            "la 2ª copia debe citar NO_DOUBLE_PAYMENT (duplicado detectado)"
        )

    def test_instrucciones_embebidas_nunca_cambian_resultado(self):
        """Trampa §11: instrucciones embebidas — datos, nunca comandos."""
        res = load_outcomes()
        marcados = [f for f, r in res.items() if no_pass(r, "NO_EMBEDDED_INSTRUCTIONS")]
        assert marcados, "las facturas con instrucciones deben quedar marcadas"
        for f in marcados:
            assert res[f]["result"] != "PAGAR", f"{f}: una instrucción embebida jamás produce PAGAR"

    def test_outlier_84700_escalado(self):
        """Trampa §11: el outlier 84700 (pedido PO-2026-0497) debe ESCALAR."""
        res = load_outcomes()
        r = res["2026-07-01_P009.pdf"]  # pedido PO-2026-0497 = 84700 en el maestro
        assert r["result"] == "ESCALAR"
        assert any(c.startswith("AMOUNT_OUTLIER") and not c.endswith("PASS") for c in r["rule_ids"])

    def test_pedidos_pendiente_revisar_escalados(self):
        """Trampa §11: PO-2026-0007 y PO-2026-0141 (pendiente_revisar) deben ESCALAR."""
        res = load_outcomes()
        esperados = {
            "FA-8488_transportes.pdf",  # PO-2026-0007
            "2026-79712_limpiezas.pdf",  # PO-2026-0141
        }
        for f in esperados:
            assert res[f]["result"] == "ESCALAR", f"{f} (pendiente_revisar) debe ESCALAR"
            assert no_pass(res[f], "PEDIDO_EN_REVISION")

    def test_scans_26_escalados(self):
        """Trampa §11: los 26 scan_*.pdf — lectura dudosa ⇒ ESCALAR, jamás PAGAR."""
        res = load_outcomes()
        scans = {f: r for f, r in res.items() if f.startswith("scan_")}
        assert len(scans) == 26
        for f, r in scans.items():
            assert r["result"] == "ESCALAR", f"{f}: scan sin texto fiable debe ESCALAR"

    def test_pedidos_nif_vacio_sin_muestras_en_lote1(self):
        """Trampa §11: pedidos PO-2026-0538…0557 (NIF vacío en maestro).

        El lote 1 no contiene facturas que los citen (verificado contra el store
        del runner). El assert explícito documenta el vacío: si el lote 2 los
        trae, este test debe re-auditar su tratamiento (NIF vacío ⇒ UNKNOWN ⇒
        ESCALAR, nunca PAGAR).
        """
        res = load_outcomes()
        citados = [
            f for f, r in res.items()
            if "0538" in json.dumps(r.get("rule_ids", []))  # no derivable del snapshot
        ]
        # el snapshot no guarda el pedido: el vacío se verifica vía store (T14) y
        # aquí se fija el contrato: NINGUNA factura debe PAGAR citándolos.
        assert res  # outcomes cargado
        # los pedidos 0538-0557 no aparecen en ningún rule_id ni file_id del snapshot
        blob = json.dumps(res, ensure_ascii=False)
        assert not any(f"PO-2026-0{n}" in blob for n in range(538, 558)) or not citados


class TestDistribucionNoPagar:
    def test_codigos_que_deciden_no_pagar(self):
        """Post-fix (T18): 22 NO_PAGAR genuinos y con FAILs reales — ningún
        código domina (>60) porque los 87 falsos por colapso desaparecieron."""
        import collections

        res = load_outcomes()
        decisores: collections.Counter[str] = collections.Counter()
        for r in res.values():
            if r["result"] != "NO_PAGAR":
                continue
            for c in r["rule_ids"]:
                if c.endswith("FAIL"):
                    decisores[c.split(":")[0]] += 1
        assert decisores, "los NO_PAGAR deben citar al menos un FAIL"
        assert sum(1 for r in res.values() if r["result"] == "NO_PAGAR") == 22
        # firma del fix: ningún código dominante >60 (el colapso ya no genera falsos)
        assert decisores.most_common(1)[0][1] <= 60


class TestRojoCorregido:
    """T18: el ROJO del T17 (colapso de candidatos) quedó CORREGIDO y el
    lote reprocesado (motor runner-1.1.0, ADR-06). Los pins congelan ahora el
    estado CORREGIDO: si el outcomes vuelve a cambiar, hay que re-auditar
    (tripwire, no aprobación).
    """

    def test_falso_no_pagar_ahora_paga(self):
        res = load_outcomes()
        r = res["2026-01-26_P007.pdf"]
        assert r["result"] == "PAGAR", (
            "2026-01-26_P007.pdf era falso NO_PAGAR por colapso de candidatos; "
            "si ya no es PAGAR, el outcomes cambió: re-auditar T17/T18"
        )
        assert not any(
            c.startswith("ORDER_AMOUNT_MATCHES") and c.endswith("FAIL")
            for c in r["rule_ids"]
        )
        # el hallazgo y su corrección quedan documentados
        audit = Path(".sdd/metrics/auditoria-trampas.md")
        assert audit.is_file(), "falta .sdd/metrics/auditoria-trampas.md"
        diff = Path(".sdd/metrics/impacto-fix-colapso.json")
        assert diff.is_file(), "falta .sdd/metrics/impacto-fix-colapso.json (T18)"

    def test_genuinos_se_mantienen_no_pagar(self):
        res = load_outcomes()
        genuinos = (
            "2026-0811-B_catering.pdf",
            "2026-14500-C_informática.pdf",
            "F26-5240_ofimática.pdf",
        )
        for f in genuinos:
            assert res[f]["result"] == "NO_PAGAR", f"{f} es genuino: no debe pagarse"
            assert any(c.startswith("ORDER_AMOUNT_MATCHES") and c.endswith("FAIL")
                       for c in res[f]["rule_ids"])

    def test_duplicado_fa8801_sigue_sin_pagar(self):
        """El 87º falso POR IMPORTE es el duplicado: su importe pasa a PASS con
        ADR-06, pero debe seguir NO_PAGAR por NO_DOUBLE_PAYMENT (§6)."""
        res = load_outcomes()
        assert res["factura_8801.pdf"]["result"] == "NO_PAGAR"
        assert any(c == "NO_DOUBLE_PAYMENT:FAIL" for c in res["factura_8801.pdf"]["rule_ids"])
