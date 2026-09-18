"""Page-level cache for rungs 2–5.

Key: (page_sha256, engine, engine_version, config_version). A cache hit makes
the rung a no-op — a 24/7 re-run never re-bills a cloud call (AGENTS.md §3).
"""

from __future__ import annotations

import json
from pathlib import Path


class PageCache:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, page_sha256: str, engine: str, engine_version: str, config_version: str) -> Path:
        name = f"{page_sha256}-{engine}-{engine_version}-{config_version}.json"
        return self.root / page_sha256[:2] / name

    def get(
        self, page_sha256: str, engine: str, engine_version: str, config_version: str
    ) -> dict | None:
        p = self._path(page_sha256, engine, engine_version, config_version)
        if not p.is_file():
            return None
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # corrupt entry = miss; recompute
        if not isinstance(payload, dict):
            return None
        return payload

    def put(
        self,
        page_sha256: str,
        engine: str,
        engine_version: str,
        config_version: str,
        payload: dict,
    ) -> None:
        p = self._path(page_sha256, engine, engine_version, config_version)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        tmp.replace(p)  # atomic: a crash never leaves a half-written entry
