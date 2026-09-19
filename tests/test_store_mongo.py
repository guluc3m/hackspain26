"""Capa Mongo dinámica — tests con FAKES (sin servidor Mongo ni pymongo)."""

from __future__ import annotations

import sys
import types

from albertitos.store import Store
from albertitos.store_mongo import MongoInvoiceBackend, connect_mongo
from albertitos.types import Decision, RuleVerdict

# --------------------------------------------------------------- fakes mongo


class FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def create_index(self, *_a, **_k) -> None:
        return None

    def replace_one(self, q: dict, doc: dict, upsert: bool = False) -> None:
        for i, d in enumerate(self.docs):
            if d.get("file_id") == q.get("file_id") and "file_id" in q and "key" not in q:
                self.docs[i] = doc
                return
        self.docs.append(doc)

    def find_one(self, q: dict) -> dict | None:
        return next((d for d in self.docs if d.get("file_id") == q.get("file_id")), None)

    def find(self, q: dict, _p: dict | None = None) -> FakeCollection:
        out = self.docs
        if "file_id" in q and isinstance(q["file_id"], dict) and "$in" in q["file_id"]:
            out = [d for d in out if d.get("file_id") in q["file_id"]["$in"]]
        elif "file_id" in q:
            out = [d for d in out if d.get("file_id") == q["file_id"]]
        if "key" in q:
            out = [d for d in out if d.get("key") == q["key"]]
            if "value" in q:
                out = [d for d in out if d.get("value") == q["value"]]
        vista = FakeCollection()
        vista.docs = out
        return vista

    def distinct(self, campo: str) -> list:
        return sorted({d[campo] for d in self.docs if campo in d})

    def bulk_write(self, ops: list) -> None:
        for op in ops:
            doc = getattr(op, "doc", None) or op._doc
            for i, d in enumerate(self.docs):
                if d.get("file_id") == doc["file_id"] and d.get("key") == doc["key"]:
                    self.docs[i] = doc
                    break
            else:
                self.docs.append(doc)

    def sort(self, *_a, **_k) -> FakeCollection:
        self.docs.sort(key=lambda d: d.get("file_id", ""))
        return self

    def __iter__(self):
        return iter(self.docs)



class FakeReplaceOne:
    def __init__(self, q: dict, doc: dict, upsert: bool = False) -> None:
        self.q, self.doc = q, doc


class FakeDB:
    def __init__(self) -> None:
        self._cols: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self._cols.setdefault(name, FakeCollection())


class FakeAdmin:
    def command(self, _cmd: str) -> dict:
        return {"ok": 1}


class FakeClient:
    def __init__(self, *_a, **_k) -> None:
        self._db = FakeDB()
        self.admin = FakeAdmin()

    def __getitem__(self, _name: str) -> FakeDB:
        return self._db

    def close(self) -> None:
        pass


# --------------------------------------------------------------- decisiones


def _decision(file_id: str, result: str = "PAGAR") -> Decision:
    return Decision(
        invoice_id=f"inv-{file_id}",
        file_id=file_id,
        result=result,
        rule_verdicts=[RuleVerdict(code="TOTALS_MUST_MATCH", outcome="PASS",
                                   reason="ok", consumed={})],
        config_snapshot={"config_version": "v-test"},
    )


# ------------------------------------------------------------ connect_mongo


def test_sin_uri_es_sqlite():
    backend, estado = connect_mongo(uri="")
    assert backend is None and estado.state == "no-configurado"


def test_sin_pymongo_degrada(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://x")
    monkeypatch.setitem(sys.modules, "pymongo", None)  # ImportError garantizado
    backend, estado = connect_mongo(uri="mongodb://x")
    assert backend is None and estado.state == "sin-pymongo"


def test_backend_roundtrip_con_fakes():
    client = FakeClient()
    be = MongoInvoiceBackend(client, db_name="albertitos-test")
    be.put_factura({"file_id": "A.pdf", "result": "PAGAR", "extra": {"ruc": "1"}})
    be.put_factura({"file_id": "B.pdf", "result": "ESCALAR", "extra": {}})
    assert be.get_factura("A.pdf")["extra"] == {"ruc": "1"}
    assert [d["file_id"] for d in be.all_facturas()] == ["A.pdf", "B.pdf"]
    assert be.resultados_por_file(["A.pdf", "B.pdf", "C.pdf"]) == {
        "A.pdf": "PAGAR", "B.pdf": "ESCALAR"}


def test_register_attrs_nuevas_y_filtro(monkeypatch):
    fake_pymongo = types.ModuleType("pymongo")
    fake_pymongo.ReplaceOne = FakeReplaceOne
    monkeypatch.setitem(sys.modules, "pymongo", fake_pymongo)
    be = MongoInvoiceBackend(FakeClient(), db_name="albertitos-test")
    assert be.register_attrs("A.pdf", {"moneda": "PEN"}) == ["moneda"]
    assert be.register_attrs("A.pdf", {"moneda": "PEN"}) == []
    assert be.files_with_attr("moneda", "PEN") == ["A.pdf"]
    assert be.files_with_attr("moneda", "EUR") == []
    assert be.known_attr_keys() == ["moneda"]


# ------------------------------------------------------------- espejo Store


def test_store_sin_mongo_sigue_funcionando(tmp_path, monkeypatch):
    monkeypatch.delenv("MONGO_URI", raising=False)
    store = Store(tmp_path / "sdd")
    assert store.mongo_estado()["state"] == "no-configurado"
    marker = (tmp_path / "sdd" / "store-backend.json").read_text(encoding="utf-8")
    assert '"backend": "sqlite"' in marker
    store.record_decision(
        _decision("A.pdf"), "sha", numero_factura="F1", pedido="P1",
        engine_version="ev", extra={"ruc": "20123456789"},
    )
    assert store.decision_for("A.pdf").extra == {"ruc": "20123456789"}


def test_store_espeja_en_mongo(tmp_path, monkeypatch):
    import albertitos.store_mongo as sm

    be = MongoInvoiceBackend(FakeClient(), db_name="albertitos-test")
    monkeypatch.setattr(sm, "connect_mongo", lambda *a, **k: (be, sm.MongoStatus("activo", "ok")))
    fake_pymongo = types.ModuleType("pymongo")
    fake_pymongo.ReplaceOne = FakeReplaceOne
    monkeypatch.setitem(sys.modules, "pymongo", fake_pymongo)
    monkeypatch.setenv("MONGO_URI", "mongodb://fake")
    store = Store(tmp_path / "sdd")
    store.record_decision(
        _decision("A.pdf"), "sha", numero_factura="F1", pedido="P1",
        engine_version="ev", extra={"moneda": "PEN", "monto_soles": 1250.5},
    )
    doc = be.get_factura("A.pdf")
    assert doc["result"] == "PAGAR"
    assert doc["extra"]["moneda"] == "PEN"  # campo de otro país, sin migración
    assert be.files_with_attr("moneda", "PEN") == ["A.pdf"]
    marker = (tmp_path / "sdd" / "store-backend.json").read_text(encoding="utf-8")
    assert '"backend": "mongo"' in marker
    # SQLite sigue siendo la fuente de autoridad
    assert store.decision_for("A.pdf").extra["monto_soles"] == 1250.5


def test_mongo_caido_no_bloquea(tmp_path, monkeypatch):
    class Roto(MongoInvoiceBackend):
        def put_factura(self, doc):
            raise RuntimeError("conexion rota")

    import albertitos.store_mongo as sm

    be = Roto(FakeClient(), db_name="x")
    monkeypatch.setattr(sm, "connect_mongo", lambda *a, **k: (be, sm.MongoStatus("down", "x")))
    monkeypatch.setenv("MONGO_URI", "mongodb://fake")
    store = Store(tmp_path / "sdd")
    store.record_decision(
        _decision("A.pdf"), "sha", numero_factura="F1", pedido="P1",
        engine_version="ev", extra={"moneda": "PEN"},
    )
    # nada explotó y la decisión está en SQLite
    assert store.decision_for("A.pdf").result == "PAGAR"
    assert store.mongo_estado()["state"] == "down"


# ---------------------------------------------------------------- migración


def test_migrar_sqlite_a_mongo_idempotente(tmp_path, monkeypatch):
    fake_pymongo = types.ModuleType("pymongo")
    fake_pymongo.ReplaceOne = FakeReplaceOne
    monkeypatch.setitem(sys.modules, "pymongo", fake_pymongo)

    store = Store(tmp_path / "sdd")
    store.record_decision(
        _decision("A.pdf"), "sha-a", numero_factura="F1", pedido="P1",
        engine_version="ev", extra={"ruc": "20123456789"},
    )
    store.record_decision(
        _decision("B.pdf", result="NO_PAGAR"), "sha-b", numero_factura="F2",
        pedido="P2", engine_version="ev",
    )
    be = MongoInvoiceBackend(FakeClient(), db_name="albertitos-test")
    assert migrar_n(be, tmp_path / "sdd" / "store.db") == 2
    assert migrar_n(be, tmp_path / "sdd" / "store.db") == 2  # re-correr no duplica
    assert be.get_factura("A.pdf")["extra"]["ruc"] == "20123456789"
    assert be.get_factura("B.pdf")["result"] == "NO_PAGAR"


def migrar_n(be, path):
    from albertitos.store_mongo import migrar_sqlite_a_mongo

    return migrar_sqlite_a_mongo(be, path)
