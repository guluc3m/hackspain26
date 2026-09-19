"""Esquema dinámico del store: campo `extra` (JSON) + registro de variables
nuevas con nombre (`invoice_attrs`) — migración ligera de DBs viejas."""

from __future__ import annotations

import json
import sqlite3

from albertitos.store import Store
from albertitos.types import Decision, RuleVerdict


def _decision(file_id: str, result: str = "ESCALAR") -> Decision:
    return Decision(
        invoice_id=f"inv-{file_id}",
        file_id=file_id,
        result=result,
        rule_verdicts=[RuleVerdict(code="TOTALS_MUST_MATCH", outcome="PASS",
                                   reason="ok", consumed={})],
        config_snapshot={"config_version": "v-test"},
    )


# --------------------------------------------------------------- extra JSON


def test_extra_se_guarda_y_se_lee(tmp_path):
    """Campos no previstos (otro país) sobreviven al round-trip del store."""
    store = Store(tmp_path / "sdd")
    extra = {"ruc": "20123456789", "moneda": "PEN", "monto_soles": 1250.5}
    store.record_decision(
        _decision("2026-05-28_P005.pdf"), "sha-ruc",
        numero_factura="FA-8801", pedido="P-01", engine_version="ev",
        extra=extra,
    )
    sd = store.decision_for("2026-05-28_P005.pdf")
    assert sd.extra == extra
    # también en el histórico por run
    assert store.run_decisions("base")[0].extra == extra
    # el JSON en disco es legible y estable (sort_keys)
    row = sqlite3.connect(tmp_path / "sdd" / "store.db").execute(
        "SELECT extra FROM invoices WHERE file_id='2026-05-28_P005.pdf'"
    ).fetchone()
    assert json.loads(row[0]) == extra
    store.close()


def test_extra_vacio_por_defecto(tmp_path):
    """Sin `extra`, todo sigue igual: los campos fijos y las queries no cambian."""
    store = Store(tmp_path / "sdd")
    store.record_decision(
        _decision("factura_8801.pdf", result="PAGAR"), "sha-0",
        numero_factura="FA-8801", pedido="P-02", engine_version="ev",
        nif="B12345678", iban="ES6614910001213000098877",
    )
    sd = store.decision_for("factura_8801.pdf")
    assert sd.extra == {}
    assert sd.nif == "B12345678"
    assert sd.iban == "ES6614910001213000098877"
    assert sd.result == "PAGAR"
    assert store.known_attr_keys() == []
    store.close()


# ------------------------------------------------- registro de variables nuevas


def test_campo_nuevo_se_registra_sin_perder_datos(tmp_path):
    """Una variable nueva (ej. RUC peruano) se registra con nombre y no toca
    los campos fijos: nif/iban/result siguen intactos y filtrables."""
    store = Store(tmp_path / "sdd")
    d = _decision("factura_peru.pdf")
    store.record_decision(
        d, "sha-pe",
        numero_factura="F-001", pedido="P-03", engine_version="ev",
        nif="", iban="",
        extra={"ruc": "20123456789", "moneda": "PEN", "monto_soles": 1250.5},
    )
    # registro clave-valor por factura, consultable/filtrable
    assert store.attrs_for("factura_peru.pdf") == {
        "monto_soles": "1250.5", "moneda": "PEN", "ruc": "20123456789",
    }
    assert store.files_with_attr("moneda", "PEN") == ["factura_peru.pdf"]
    assert store.files_with_attr("moneda", "EUR") == []
    assert store.files_with_attr("ruc") == ["factura_peru.pdf"]
    assert store.known_attr_keys() == ["moneda", "monto_soles", "ruc"]
    # nada de lo que ya funcionaba se ha perdido
    sd = store.decision_for("factura_peru.pdf")
    assert sd.result == "ESCALAR"
    assert sd.numero_factura == "F-001"
    # primera aparición de cada variable nueva queda en el ledger (trazabilidad)
    nuevos = [e for e in store.ledger_events() if e["event"] == "new_field"]
    assert {e["key"] for e in nuevos} == {"ruc", "moneda", "monto_soles"}
    store.close()


def test_variable_repetida_no_duplica_evento(tmp_path):
    """La segunda factura con RUC reutiliza la variable: un solo new_field."""
    store = Store(tmp_path / "sdd")
    for i, fid in enumerate(("a.pdf", "b.pdf")):
        store.record_decision(
            _decision(fid), f"sha-{i}",
            numero_factura=f"F-{i}", pedido="P", engine_version="ev",
            extra={"ruc": "20...1"},
        )
    assert len([e for e in store.ledger_events()
                if e["event"] == "new_field"]) == 1
    assert store.files_with_attr("ruc") == ["a.pdf", "b.pdf"]
    store.close()


# --------------------------------------------------------------- DB vieja migra


def test_db_vieja_migra_sin_perder_datos(tmp_path):
    """Un store creado antes del esquema dinámico (sin `extra` ni
    `invoice_attrs`) se abre, migra con ALTER TABLE y conserva sus filas."""
    root = tmp_path / "sdd"
    root.mkdir(parents=True)
    conn = sqlite3.connect(root / "store.db")
    conn.executescript(
        """
        CREATE TABLE invoices (
            file_id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            result TEXT NOT NULL,
            rule_codes TEXT NOT NULL,
            numero_factura TEXT,
            pedido TEXT,
            config_version TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            nif TEXT DEFAULT '',
            iban TEXT DEFAULT ''
        );
        INSERT INTO invoices (file_id, invoice_id, sha256, result, rule_codes,
            numero_factura, pedido, config_version, engine_version, updated_at,
            nif, iban)
        VALUES ('vieja.pdf', 'inv-v', 'sha-v', 'PAGAR', 'TOTALS_MUST_MATCH:PASS',
            'F-100', 'P-100', 'v-old', 'e-old', '2026-01-01T00:00:00',
            'B99999999', 'ES9121000418450200051332');
        """
    )
    conn.commit()
    conn.close()

    store = Store(root)  # migración bajo demanda
    sd = store.decision_for("vieja.pdf")
    assert sd.result == "PAGAR"
    assert sd.nif == "B99999999"
    assert sd.iban == "ES9121000418450200051332"
    assert sd.extra == {}  # columna nueva, fila vieja intacta
    # la DB migrada sigue operativa: acepta campos nuevos de otro país
    store.record_decision(
        _decision("vieja.pdf", result="NO_PAGAR"), "sha-v2",
        numero_factura="F-100", pedido="P-100", engine_version="e-old",
        nif="B99999999", iban="ES9121000418450200051332",
        extra={"ruc": "10456789012", "moneda": "PEN"},
    )
    assert store.decision_for("vieja.pdf").extra["ruc"] == "10456789012"
    assert store.attrs_for("vieja.pdf")["moneda"] == "PEN"
    # y el histórico de la decisión vieja no se ha borrado
    row = sqlite3.connect(root / "store.db").execute(
        "SELECT result, nif FROM invoices WHERE file_id='vieja.pdf'"
    ).fetchone()
    assert row == ("NO_PAGAR", "B99999999")
    store.close()