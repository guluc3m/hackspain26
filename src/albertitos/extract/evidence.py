"""Evidence sink for extraction stages — append-only JSONL (AGENTS.md §5)."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path

from albertitos.types import EvidenceRow


class EvidenceLedger:
    """Collects EvidenceRow objects in memory and optionally appends to disk.

    Thread-safe: the dry-run runs up to 2 files in flight (ticket T10).
    """

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.rows: list[EvidenceRow] = []
        self._lock = threading.Lock()

    def append(self, row: EvidenceRow) -> None:
        with self._lock:
            self.rows.append(row)
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(asdict(row), ensure_ascii=False, sort_keys=True) + "\n")
