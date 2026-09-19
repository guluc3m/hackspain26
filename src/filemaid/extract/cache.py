"""Cache de escalones sobre (page_sha256, extractor_version, config_version).

extractor_version incluye la identidad del motor y su versión (p. ej.,
"cloud_vlm-1"): una versión numérica sola colisiona entre proveedores.
Los escalones no consultan las claves numéricas antiguas ni las migran;
son ambiguas y deben producir un fallo de caché con las nuevas identidades.

Un re-run 24/7 nunca re-factura una llamada cloud. Estado en PouchDB.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from filemaid.store.pouch import INLINE_LIMIT, PouchStore
from filemaid.types import ExtractionFeature


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def encode(obj: Any) -> str:
    if is_dataclass(obj):
        obj = asdict(obj)
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=repr)


class FeatureCache:
    def __init__(self, root: Path | PouchStore) -> None:
        if isinstance(root, PouchStore):
            self.store = root
        else:
            self.store = PouchStore(root)

    @property
    def root(self) -> Path:
        return self.store.root

    def key(self, page_sha256: str, extractor_version: str, config_version: str) -> str:
        raw = f"{page_sha256}|{extractor_version}|{config_version}"
        return sha256_bytes(raw.encode())

    def get(self, page_sha256: str, extractor_version: str, config_version: str) -> ExtractionFeature | None:
        doc_id = f"cache:{self.key(page_sha256, extractor_version, config_version)}"
        doc = self.store.get(doc_id)
        if doc is None:
            return None
        doc = self.store.hydrate(doc)
        feature_data = dict(doc.get("feature", {}))
        if feature_data.get("_bytes_encoded"):
            raw_b64 = feature_data.get("data", "")
            feature_data["data"] = base64.b64decode(raw_b64)
            feature_data.pop("_bytes_encoded", None)
        return ExtractionFeature(**feature_data)

    def put(self, page_sha256: str, feature: ExtractionFeature, config_version: str) -> None:
        k = self.key(page_sha256, feature.extractor_version, config_version)
        doc_id = f"cache:{k}"
        existing = self.store.get(doc_id)
        if existing is not None:
            return

        feat_dict = asdict(feature)
        if isinstance(feat_dict.get("data"), bytes):
            feat_dict["data"] = base64.b64encode(feat_dict["data"]).decode("ascii")
            feat_dict["_bytes_encoded"] = True

        payload = {"feature": feat_dict}
        raw_json = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)

        if len(raw_json.encode("utf-8")) > INLINE_LIMIT:
            identity = {"scan_id": f"cache-{k}"}
            ref = self.store.artifact(identity, "cache", f"cache_{k}.json", raw_json.encode("utf-8"), "application/json")
            payload = {"payload_ref": ref, "encoding": "json"}

        doc = {
            "_id": doc_id,
            "kind": "cache",
            "key": k,
            "page_sha256": page_sha256,
            "extractor_version": feature.extractor_version,
            "config_version": config_version,
            **payload,
        }
        try:
            self.store.put(doc)
        except RuntimeError:
            # A concurrent writer may win the immutable cache slot; disk errors
            # and other failures still propagate unless a usable value exists.
            if self.store.get(doc_id) is None:
                raise
