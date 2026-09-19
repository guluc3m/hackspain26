"""Ledger JSONL append-only: cada transición de estado, en orden.

Sobrevive a un fichero DB corrupto; la recuperación es "copiar un fichero".
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class Ledger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        # ts: hora de recepción (el store también sella; el ledger es el log
        # crudo y ordenado). Eventos antiguos sin ts se leen como None.
        event = {"type": event_type, **payload, "ts": time.time()}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def read(self) -> list[dict[str, Any]]:
        """Lee el ledger en orden de escritura. Tolerante a una última línea
        truncada por una caída: se salta y el resto sigue legible."""
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # línea corrupta/truncada: no tumba la lectura
        return events
