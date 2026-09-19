from __future__ import annotations

from albertitos.rules.base import RuleContext
from albertitos.rules.escoger import ELEGIDO, FieldSelection, escoger, field_selection
from albertitos.types import ExtractionField


def _field(tipo: str, *candidatos: tuple[str, object, float]) -> ExtractionField:
    f = ExtractionField(type=tipo)
    for extractor, valor, conf in candidatos:
        f.add(extractor, valor, conf)
    return f


def test_trim_de_valores_de_texto():
    f = _field("nif", ("tesseract", " B12345678 ", 0.9))
    sel = escoger(f, FieldSelection())
    assert sel.candidate.value == "B12345678"
    assert sel.candidate is not None and sel.why


def test_formato_rechaza_candidato_mal_formado():
    f = _field(
        "nif",
        ("tesseract", "12345678", 0.95),  # sin letra: rechazado por formato
        ("pypdf", "B12345678", 0.6),
    )
    sel = escoger(f, field_selection({"fields": {"nif": {"format_tests": ["NIF_FORMAT"]}}}, "nif"))
    assert sel.candidate.extractor == "pypdf"
    estados = {a.extractor: a.status for a in sel.audit}
    assert estados["tesseract"] == "RECHAZADO_FORMATO:NIF_FORMAT"
    assert estados["pypdf"] == ELEGIDO


def test_formato_nie_y_nif_de_maestro_pasan():
    for nif in ("B12345678", "X1234567R", "B-87654321"):
        f = _field("nif", ("pypdf", nif, 0.9))
        sel = escoger(
            f, field_selection({"fields": {"nif": {"format_tests": ["NIF_FORMAT"]}}}, "nif")
        )
        assert sel.candidate is not None, nif


def test_peso_del_extractor_cambia_la_puntuacion():
    f = _field(
        "total",
        ("cloud_vlm", 121.50, 0.9),  # 0.9 × 0.8 = 0.72
        ("pypdf", 121.00, 0.8),  # 0.8 × 1.0 = 0.80
    )
    sel = escoger(
        f, field_selection({"default_extractor_weights": {"pypdf": 1.0, "cloud_vlm": 0.8}}, "total")
    )
    assert sel.candidate.value == 121.00


def test_umbral_de_puntuacion_descarta_todo():
    f = _field("nif", ("tesseract", "B12345678", 0.4))
    sel = escoger(f, field_selection({"fields": {"nif": {"score_threshold": 0.5}}}, "nif"))
    assert sel.candidate is None
    assert "umbral" in sel.reason
    assert sel.audit[0].status == "RECHAZADO_UMBRAL"


def test_empate_mismo_valor_da_igual_el_extractor():
    f = _field("total", ("pypdf", 121.0, 0.8), ("tesseract", 121.0, 0.8))
    sel = escoger(f, FieldSelection(extractor_weights={"pypdf": 1.0, "tesseract": 1.0}))
    assert sel.candidate.extractor == "pypdf"
    assert "idénticos" in sel.why


def test_empate_valor_distinto_desempata_ranking():
    f = _field(
        "nif",
        ("vlm", "B99999999", 0.8),
        ("pypdf", "B12345678", 0.8),
    )
    cfg = {
        "default_extractor_weights": {"pypdf": 1.0, "vlm": 1.0},
        "fields": {"nif": {"extractor_ranking": ["pypdf", "vlm"]}},
    }
    sel = escoger(f, field_selection(cfg, "nif"))
    assert sel.candidate.value == "B12345678"
    assert "ranking" in sel.why


def test_ranking_por_defecto_alfabetico():
    f = _field("nif", ("zz", "B99999999", 0.8), ("aa", "B12345678", 0.8))
    sel = escoger(f, FieldSelection())
    assert sel.candidate.extractor == "aa"


def test_determinismo():
    f = _field("nif", ("tesseract", "B12345678", 0.7), ("pypdf", " B12345678 ", 0.7))
    cfg = {"fields": {"nif": {"format_tests": ["NIF_FORMAT"]}}}
    a = escoger(f, field_selection(cfg, "nif"))
    b = escoger(f, field_selection(cfg, "nif"))
    assert (a.candidate, a.why, [(x.extractor, x.status) for x in a.audit]) == (
        b.candidate,
        b.why,
        [(x.extractor, x.status) for x in b.audit],
    )


def test_pick_integrado_con_umbral_y_formato():
    ctx = RuleContext(
        fields={
            "nif": _field(
                "nif",
                ("tesseract", "garbage", 0.99),
                ("pypdf", "B12345678", 0.8),
            ),
        },
        master=None,
        seleccion={"fields": {"nif": {"format_tests": ["NIF_FORMAT"]}}},
    )
    cand, err = ctx.pick("nif", 0.7)
    assert err is None and cand.value == "B12345678"

    detallada = ctx.pick_detailed("nif", 0.7)
    assert {a.status for a in detallada.audit} >= {ELEGIDO, "RECHAZADO_FORMATO:NIF_FORMAT"}


def test_pick_confianza_baja_da_unknown():
    ctx = RuleContext(
        fields={"nif": _field("nif", ("pypdf", "B12345678", 0.3))},
        master=None,
    )
    cand, err = ctx.pick("nif", 0.7)
    assert cand is None
    assert "umbral" in err


def test_pick_formato_rechaza_todo_da_motivo():
    ctx = RuleContext(
        fields={"iban": _field("iban", ("pypdf", "no-es-un-iban", 0.9))},
        master=None,
        seleccion={"fields": {"iban": {"format_tests": ["IBAN_FORMAT"]}}},
    )
    cand, err = ctx.pick("iban")
    assert cand is None
    assert "formato" in err


def test_pick_sin_campo():
    ctx = RuleContext(fields={}, master=None)
    cand, err = ctx.pick("total")
    assert cand is None and "sin campo" in err


def test_amount_formatos():
    assert (
        escoger(
            _field("total", ("pypdf", "1.234,56 €", 0.9)),
            FieldSelection(format_tests=("AMOUNT_POSITIVE",)),
        ).candidate.value
        == "1.234,56 €"
    )
    assert (
        escoger(
            _field("total", ("pypdf", "N/A", 0.9)), FieldSelection(format_tests=("AMOUNT_FORMAT",))
        ).candidate
        is None
    )
    assert (
        escoger(
            _field("total", ("pypdf", -5.0, 0.9)), FieldSelection(format_tests=("AMOUNT_POSITIVE",))
        ).candidate
        is None
    )
    assert (
        escoger(
            _field("iva_amount", ("pypdf", 0.0, 0.9)),
            FieldSelection(format_tests=("AMOUNT_NON_NEGATIVE",)),
        ).candidate
        is not None
    )


def test_fecha_formato():
    ok = _field("fecha", ("pypdf", "01/01/2026", 0.9))
    ko = _field("fecha", ("pypdf", "31/02/2026", 0.9))
    assert escoger(ok, FieldSelection(format_tests=("DATE_FORMAT",))).candidate is not None
    assert escoger(ko, FieldSelection(format_tests=("DATE_FORMAT",))).candidate is None
