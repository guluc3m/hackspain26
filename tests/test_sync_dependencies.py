import pytest

from filemaid.store.pouch import PouchStore


def test_invalid_dependencies_never_enter_replication_source(tmp_path):
    store = PouchStore(tmp_path)
    for doc in (
        {"_id": "artifact:bad", "kind": "artifact", "chunks": None},
        {"_id": "artifact:bad", "kind": "artifact", "chunks": ["blob:missing"]},
        {"_id": "doc:bad", "kind": "future", "payload_ref": "artifact:missing"},
        {
            "_id": "artifact:cycle",
            "kind": "artifact",
            "chunks": [],
            "payload_ref": "artifact:cycle",
        },
    ):
        with pytest.raises(RuntimeError):
            store.put(doc)
        assert store.get(doc["_id"]) is None
    store.put({"_id": "valid:new-kind", "new_field": {"arbitrary": True}})
    assert [d["_id"] for d in store.list("")] == ["valid:new-kind"]
