"""Evidence sink for extraction stages — append-only JSONL (AGENTS.md §5)."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from albertitos.types import EvidenceRow


class EvidenceLedger:
    """Collects EvidenceRow objects in memory and optionally appends to disk."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.rows: list[EvidenceRow] = []

    def append(self, row: EvidenceRow) -> None:
        self.rows.append(row)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(row), ensure_ascii=False, sort_keys=True) + "\n")
