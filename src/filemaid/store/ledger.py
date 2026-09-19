"""Ledger JSONL append-only: cada transición de estado, en orden.

Sobrevive a un fichero DB corrupto; la recuperación es "copiar un fichero".
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class Ledger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"type": event_type, **payload}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
