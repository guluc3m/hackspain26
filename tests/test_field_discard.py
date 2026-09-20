"""Campos descartables y overrides manuales en la revisión (backend).

Contrato del modelo de overrides (el motor sigue decidiendo; ver AGENTS.md §6):

* ``corrected[field] = null`` es el centinela de **descarte**: la lectura
  desaparece (el campo queda sin valor), así que ``escoger`` no colapsa nada y
  toda regla que lo consuma degrada a UNKNOWN — nunca PAGAR.
* ``corrected[field] = <valor>`` inyecta un candidato ``override`` con confianza
  1.0 que pasa por ``escoger`` (tests de formato, umbral, desempate) y aparece
  en ``chosen_candidates`` de la regla que lo consume, incluso si el campo no
  tenía ningún candidato.
* Solo el último override por campo aplica: descartar y volver a declarar un
  valor es reversible.
"""

from __future__ import annotations

import dataclasses

import pytest

from filemaid.parse.extractors import all_extractors
from filemaid.pipeline import Pipeline, apply_overrides, reprocess_from_store
from filemaid.review import resolve_review
from filemaid.rules.engine import evaluate
from filemaid.rules.escoger import escoger, field_selection
from filemaid.rules.rules import all_rules
from filemaid.store import queries
from filemaid.store.pouch import PouchStore, canonical
from filemaid.types import (
    OVERRIDE_EXTRACTOR,
    UNKNOWN_SIN_CANDIDATO_VALIDO,
    ExtractionField,
    Result,
    RuleVerdict,
)
from test_rules_engine import _fields_ok
from test_smoke_pipeline import _make_text_pdf

# Factura real de la escalera de texto: extrae nif/iban/base/total/fecha/iva_amount
# y deja pedido e iva_rate sin candidato alguno. NIF y pedido del maestro real
# (master/proveedores.csv, master/pedidos.csv) hacen el caso decidible.
ESCALAR_CON_NIF = (
    "FACTURA Suministros Garcia SL NIF B12345678 IBAN ES91 2100 0418 4502 0005 1332"
    " TOTAL 121,00 EUR Fecha 15/01/2026 Base 100,00 EUR IVA 21,00 EUR"
)

# Reglas que consumen cada campo (códigos estables de rules.py). El descarte de un
# campo debe degradar exactamente a estas.
CONSUMIDORES: dict[str, tuple[str, ...]] = {
    "base": ("IVA_CONSISTENT", "TOTALS_MUST_MATCH"),
    "fecha": ("DATE_VALID_NOT_FUTURE",),
    "iban": ("IBAN_MATCHES_MASTER",),
    "iva_amount": ("IVA_CONSISTENT", "TOTALS_MUST_MATCH"),
    "iva_rate": ("IVA_CONSISTENT",),
    "nif": ("IBAN_MATCHES_MASTER", "NIF_IN_MASTER", "ORDER_BELONGS_TO_SUPPLIER"),
    "pedido": ("NO_DOUBLE_PAYMENT", "ORDER_BELONGS_TO_SUPPLIER", "ORDER_PENDING"),
    "total": ("ORDER_BELONGS_TO_SUPPLIER", "TOTALS_MUST_MATCH"),
}


def _override_doc(
    field_type: str, after: object, *, before: object = None, timestamp: float = 1.0
) -> dict:
    """Evento de override con la forma que persiste ``queries.write_override``."""
    return {
        "_id": f"event:override:{timestamp}:{field_type}",
        "kind": "event",
        "type": "override",
        "timestamp": timestamp,
        "payload": {
            "field_type": field_type,
            "before": before,
            "after": after,
            "who": "revisor",
            "rung": "review-ui",
            "reason": "prueba",
        },
    }


def _campos(master, *sin: str) -> list[ExtractionField]:
    """Campos de una factura que pagaría, opcionalmente sin los tipos indicados."""
    return [f for f in _fields_ok(master).values() if f.type not in sin]


def _por_tipo(fields: list[ExtractionField]) -> dict[str, ExtractionField]:
    return {f.type: f for f in fields}


def _valores(store: PouchStore, scan_id: str) -> dict[str, list[dict]]:
    return {f["type"]: f["values"] for f in queries.fields_for_scan(store, scan_id)}


def _evaluaciones(store: PouchStore, decision_id: str) -> dict[str, dict]:
    decision = store.get(decision_id)
    assert decision is not None, decision_id
    payload = store.hydrate(decision)["decision"]
    return {e["code"]: e for e in payload["rule_evaluations"]}


def _escalada(cfg, tmp_path, text: str = ESCALAR_CON_NIF) -> tuple[PouchStore, str, str]:
    """Ingesta una factura que escala y devuelve (store, file_key, decision_id)."""
    source = tmp_path / "revision.pdf"
    _make_text_pdf(source, text)
    Pipeline(cfg).process_pdf(source)
    store = PouchStore(cfg.root)
    row = next(r for r in queries.invoice_rows(store) if r["file_id"] == "revision.pdf")
    assert row["result"] == "ESCALAR"
    return store, row["id"], row["decision_id"]


def _cuerpo(decision_id: str, corrected: dict, **extra) -> dict:
    return {
        "who": "alice",
        "expected_decision_id": decision_id,
        "corrected": corrected,
        **extra,
    }


def _estable(decision) -> dict:
    """Decisión sin las medidas de reloj: el motor es puro, la latencia no decide."""
    payload = dataclasses.asdict(decision)
    payload.pop("timings")
    for key in ("extraction_ms", "parser_ms", "evaluation_ms", "total_ms"):
        payload.pop(key)
    return payload


# ------------------------------------------------------- descarte (motor puro)


@pytest.mark.parametrize(("field_type", "consumidores"), sorted(CONSUMIDORES.items()))
def test_descartar_degrada_a_unknown_y_nunca_paga(field_type, consumidores, master, rule_config):
    """Descartar un campo con candidatos deja el campo sin valor y escala."""
    campos = _campos(master)
    base = evaluate(_por_tipo(campos), master, rule_config, "inv-base", "f.pdf")
    assert base.result is Result.PAGAR

    campos, applied = apply_overrides(campos, [_override_doc(field_type, None)])

    assert _por_tipo(campos)[field_type].values == []
    assert applied == [
        {
            "field_type": field_type,
            "value": None,
            "before": None,
            "who": "revisor",
            "rung": "review-ui",
            "reason": "prueba",
            "override_id": f"event:override:1.0:{field_type}",
            "timestamp": 1.0,
            "discarded": True,
        }
    ]

    etiquetas = {r.code for r in all_rules()}
    decision = evaluate(_por_tipo(campos), master, rule_config, "inv-desc", "f.pdf")
    evaluaciones = {e.code: e for e in decision.rule_evaluations}
    # Se contrasta contra el propio juego de reglas del motor: las reglas que
    # consumen el campo son las que degradan, y todas existen.
    assert set(evaluaciones) == etiquetas
    assert set(consumidores) <= etiquetas
    for code in consumidores:
        assert evaluaciones[code].verdict is RuleVerdict.UNKNOWN, code
        assert evaluaciones[code].reason_code
    assert decision.result is Result.ESCALAR


def test_descartar_campo_sin_candidato_ni_extraccion_no_falla(master, rule_config):
    """Descartar un campo que no existe (ni candidatos) es válido y no rompe."""
    campos = _campos(master, "iban")
    assert "iban" not in _por_tipo(campos)

    campos, applied = apply_overrides(campos, [_override_doc("iban", None)])

    assert _por_tipo(campos)["iban"].values == []
    assert applied[0]["discarded"] is True and applied[0]["value"] is None

    decision = evaluate(_por_tipo(campos), master, rule_config, "inv-sin-iban", "f.pdf")
    evaluaciones = {e.code: e for e in decision.rule_evaluations}
    assert evaluaciones["IBAN_MATCHES_MASTER"].verdict is RuleVerdict.UNKNOWN
    assert decision.result is Result.ESCALAR


def test_ultimo_override_por_campo_decide_y_es_reversible(master):
    """Descartar y volver a declarar un valor: solo aplica el override más nuevo."""
    descarte_viejo = _override_doc("nif", None, timestamp=1.0)
    valor_nuevo = _override_doc("nif", "B12345678", timestamp=2.0)
    valor_viejo = _override_doc("nif", "B12345678", timestamp=1.0)
    descarte_nuevo = _override_doc("nif", None, timestamp=2.0)

    campos, applied = apply_overrides(_campos(master), [valor_nuevo, descarte_viejo])
    nif = _por_tipo(campos)["nif"]
    assert [(c.extractor, c.value, c.confidence) for c in nif.values][0] == (
        OVERRIDE_EXTRACTOR,
        "B12345678",
        1.0,
    )
    assert [a["field_type"] for a in applied] == ["nif"] and "discarded" not in applied[0]

    campos, applied = apply_overrides(_campos(master), [descarte_nuevo, valor_viejo])
    assert _por_tipo(campos)["nif"].values == []
    assert [a["field_type"] for a in applied] == ["nif"]
    assert applied[0]["discarded"] is True and applied[0]["value"] is None

    campos, applied = apply_overrides(
        _campos(master),
        [
            _override_doc("nif", None, timestamp=1.0),
            valor_nuevo,
            _override_doc("nif", None, timestamp=3.0),
        ],
    )
    assert _por_tipo(campos)["nif"].values == []
    assert len(applied) == 1 and applied[0]["discarded"] is True


# --------------------------------------------------- override manual (motor puro)


def test_override_manual_en_campo_sin_candidatos_fluye_por_escoger(master, rule_config):
    """Un valor manual sobre un campo sin candidatos decide la regla (PASS)."""
    sin_nif = _campos(master, "nif")
    previo = evaluate(_por_tipo(sin_nif), master, rule_config, "inv-pre", "f.pdf")
    assert previo.result is Result.ESCALAR  # el campo ausente degrada a UNKNOWN

    campos, applied = apply_overrides(sin_nif, [_override_doc("nif", "B12345678")])
    nif = _por_tipo(campos)["nif"]
    assert [(c.extractor, c.value, c.confidence) for c in nif.values] == [
        (OVERRIDE_EXTRACTOR, "B12345678", 1.0)
    ]
    assert applied[0]["value"] == "B12345678" and "discarded" not in applied[0]

    seleccion = escoger(nif, field_selection(rule_config.seleccion, "nif"))
    assert seleccion.candidate.extractor == OVERRIDE_EXTRACTOR
    assert seleccion.candidate.confidence == 1.0
    assert seleccion.candidate.value == "B12345678"

    decision = evaluate(_por_tipo(campos), master, rule_config, "inv-override", "f.pdf")
    evaluaciones = {e.code: e for e in decision.rule_evaluations}
    assert evaluaciones["NIF_IN_MASTER"].verdict is RuleVerdict.PASS
    assert (
        evaluaciones["NIF_IN_MASTER"].chosen_candidates["nif"]
        == "override@1.00 (mayor confianza)"
    )
    assert decision.result is Result.PAGAR


def test_override_manual_con_formato_invalido_no_supera_escoger(master, rule_config):
    """El valor manual es un candidato más: el test de formato de escoger manda."""
    campos, _ = apply_overrides(_campos(master, "nif"), [_override_doc("nif", "NO-ES-NIF")])

    decision = evaluate(_por_tipo(campos), master, rule_config, "inv-override-ko", "f.pdf")
    evaluaciones = {e.code: e for e in decision.rule_evaluations}
    assert evaluaciones["NIF_IN_MASTER"].verdict is RuleVerdict.UNKNOWN
    assert evaluaciones["NIF_IN_MASTER"].reason_code == UNKNOWN_SIN_CANDIDATO_VALIDO
    assert decision.result is not Result.PAGAR


# ---------------------------------------------------------------- revisión real


def test_revision_descarta_un_campo_con_candidatos(cfg, tmp_path):
    store, key, decision_id = _escalada(cfg, tmp_path)

    resultado = resolve_review(
        store, cfg, key, _cuerpo(decision_id, {"nif": None})
    )

    assert resultado["review_state"] == "resolved"
    assert resultado["result"] == Result.ESCALAR  # nunca PAGAR
    token = resultado["decision_id"].removeprefix("decision:")

    assert _valores(store, token)["nif"] == []
    evaluaciones = _evaluaciones(store, resultado["decision_id"])
    for code in CONSUMIDORES["nif"]:
        assert evaluaciones[code]["verdict"] == RuleVerdict.UNKNOWN, code

    evento = store.get(f"event:override:{token}:nif")
    assert evento is not None
    payload = store.hydrate(evento)["payload"]
    assert payload["after"] is None
    assert payload["before"] == "B12345678"
    assert payload["reason"] == "campo descartado en revisión"
    assert payload["who"] == "alice"

    decision = store.hydrate(store.get(resultado["decision_id"]))
    assert decision["overrides_applied"] == [
        {
            "field_type": "nif",
            "value": None,
            "before": "B12345678",
            "who": "alice",
            "rung": "review-ui",
            "reason": "campo descartado en revisión",
            "override_id": f"event:override:{token}:nif",
            "timestamp": evento["timestamp"],
            "discarded": True,
        }
    ]


def test_revision_descarta_un_campo_sin_candidatos(cfg, tmp_path):
    store, key, decision_id = _escalada(cfg, tmp_path)
    assert queries.invoice_detail(store, key)["field_status"]["iva_rate"]["has_value"] is False

    resultado = resolve_review(store, cfg, key, _cuerpo(decision_id, {"iva_rate": None}))

    assert resultado["result"] == Result.ESCALAR
    token = resultado["decision_id"].removeprefix("decision:")
    assert _valores(store, token)["iva_rate"] == []
    evaluaciones = _evaluaciones(store, resultado["decision_id"])
    assert evaluaciones["IVA_CONSISTENT"]["verdict"] == RuleVerdict.UNKNOWN

    payload = store.hydrate(store.get(f"event:override:{token}:iva_rate"))["payload"]
    assert payload["after"] is None and payload["before"] is None
    assert payload["reason"] == "campo descartado en revisión"

    detail = queries.invoice_detail(store, key)
    assert detail["field_status"]["iva_rate"]["discarded"] is True
    assert detail["field_status"]["iva_rate"]["has_value"] is False


def test_revision_override_manual_decide_pagar(cfg, tmp_path):
    """Dos campos sin candidato, declarados a mano: la factura llega a PAGAR."""
    store, key, decision_id = _escalada(cfg, tmp_path)
    assert queries.invoice_detail(store, key)["field_status"]["pedido"]["candidates"] == 0

    resultado = resolve_review(
        store, cfg, key, _cuerpo(decision_id, {"iva_rate": 21, "pedido": "P-2026-001"})
    )

    assert resultado["result"] == Result.PAGAR
    evaluaciones = _evaluaciones(store, resultado["decision_id"])
    assert evaluaciones["ORDER_PENDING"]["verdict"] == RuleVerdict.PASS
    assert evaluaciones["ORDER_PENDING"]["chosen_candidates"]["pedido"] == "override@1.00"
    assert evaluaciones["IVA_CONSISTENT"]["verdict"] == RuleVerdict.PASS

    token = resultado["decision_id"].removeprefix("decision:")
    valores = _valores(store, token)
    assert [(c["extractor"], c["value"], c["confidence"]) for c in valores["pedido"]] == [
        (OVERRIDE_EXTRACTOR, "P-2026-001", 1.0)
    ]
    assert [(c["extractor"], c["value"], c["confidence"]) for c in valores["iva_rate"]] == [
        (OVERRIDE_EXTRACTOR, 21, 1.0)
    ]


def test_revision_descartar_y_volver_a_declarar_el_valor(cfg, tmp_path):
    """Un override posterior con valor sustituye por completo al descarte."""
    store, key, decision_id = _escalada(cfg, tmp_path)
    descartado = resolve_review(store, cfg, key, _cuerpo(decision_id, {"nif": None}))
    token = descartado["decision_id"].removeprefix("decision:")
    assert _valores(store, token)["nif"] == []

    repuesto = resolve_review(
        store, cfg, key, _cuerpo(f"decision:{token}", {"nif": "B87654321"})
    )

    assert repuesto["result"] == Result.ESCALAR  # el humano corrige la lectura, no el pago
    token2 = repuesto["decision_id"].removeprefix("decision:")
    valores = _valores(store, token2)
    assert [(c["extractor"], c["value"], c["confidence"]) for c in valores["nif"]][0] == (
        OVERRIDE_EXTRACTOR,
        "B87654321",
        1.0,
    )
    evaluaciones = _evaluaciones(store, repuesto["decision_id"])
    assert evaluaciones["NIF_IN_MASTER"]["verdict"] == RuleVerdict.PASS
    assert (
        evaluaciones["NIF_IN_MASTER"]["chosen_candidates"]["nif"]
        == "override@1.00 (mayor confianza)"
    )


def test_detalle_expone_campos_soportados_y_marcas(cfg, tmp_path):
    store, key, decision_id = _escalada(cfg, tmp_path)

    detail = queries.invoice_detail(store, key)
    assert detail["supported_fields"] == sorted({name for name, _, _ in all_extractors()})
    assert sorted(detail["field_status"]) == detail["supported_fields"]
    assert set(detail["supported_fields"]) <= set(detail["fields"])
    assert detail["fields"]["iva_rate"] == []  # sin candidatos, pero presente
    assert detail["field_status"]["iva_rate"] == {
        "has_value": False,
        "discarded": False,
        "candidates": 0,
        "last_override": None,
    }
    assert detail["field_status"]["nif"]["has_value"] is True

    resolve_review(store, cfg, key, _cuerpo(decision_id, {"nif": None}))

    detail = queries.invoice_detail(store, key)
    assert detail["fields"]["nif"] == []
    estado = detail["field_status"]["nif"]
    assert estado["discarded"] is True
    assert estado["has_value"] is False and estado["candidates"] == 0
    assert estado["last_override"]["after"] is None
    assert estado["last_override"]["before"] == "B12345678"
    assert estado["last_override"]["who"] == "alice"
    assert estado["last_override"]["reason"] == "campo descartado en revisión"


def test_recalculo_determinista_byte_a_byte(cfg, tmp_path):
    store, key, decision_id = _escalada(cfg, tmp_path)
    resolve_review(store, cfg, key, _cuerpo(decision_id, {"nif": None, "pedido": "P-2026-001"}))

    primera, _ = reprocess_from_store(store, cfg, "revision.pdf", key, scan_id="det-1")
    segunda, _ = reprocess_from_store(store, cfg, "revision.pdf", key, scan_id="det-2")

    assert primera.result == segunda.result == Result.ESCALAR
    assert canonical(_estable(primera)) == canonical(_estable(segunda))


def test_intento_idempotente_con_nulos_y_conflicto(cfg, tmp_path):
    store, key, decision_id = _escalada(cfg, tmp_path)
    cuerpo = _cuerpo(decision_id, {"nif": None})

    primero = resolve_review(store, cfg, key, cuerpo)
    assert resolve_review(store, cfg, key, cuerpo) == primero  # mismo intento: comprometido

    with pytest.raises(RuntimeError):
        resolve_review(store, cfg, key, _cuerpo(decision_id, {"nif": "B12345678"}))

    assert resolve_review(store, cfg, key, cuerpo) == primero
