"""Cache de escalones sobre (page_sha256, extractor_version, config_version).

Un re-run 24/7 nunca re-factura una llamada cloud. Estado en disco (data/cache),
nunca en /tmp (tmpfs).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

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
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def key(self, page_sha256: str, extractor_version: str, config_version: str) -> str:
        raw = f"{page_sha256}|{extractor_version}|{config_version}"
        return sha256_bytes(raw.encode())

    def get(self, page_sha256: str, extractor_version: str, config_version: str) -> ExtractionFeature | None:
        path = self.root / f"{self.key(page_sha256, extractor_version, config_version)}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ExtractionFeature(**data)

    def put(self, page_sha256: str, feature: ExtractionFeature, config_version: str) -> None:
        path = self.root / f"{self.key(page_sha256, feature.extractor_version, config_version)}.json"
        path.write_text(encode(feature), encoding="utf-8")
