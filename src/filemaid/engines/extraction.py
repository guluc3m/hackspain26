"""Motor de extracción (architecture.typ §Bloque de extracción).

PDF -> features en crudo (extract/, escalera por página) -> parser -> campos
ExtractionField con TODOS los candidatos (parse/). Sin interpretación.

La llamada desde la app aún no está definida: el método define el contrato y
lanza NotImplementedError. La UI usa la referencia sintética mientras tanto.
"""

from __future__ import annotations

from pathlib import Path

from filemaid.types import ExtractionField


class ExtractionEngine:
    """Bloque de extracción: features -> campos, todos los candidatos."""

    def extraer(self, pdf_path: str | Path) -> list[ExtractionField]:
        """Extrae los campos de un PDF (features + parser, sin colapsar)."""
        raise NotImplementedError(
            "llamada al motor de extracción sin definir: los datos de la UI "
            "son sintéticos (frontend/src/mock/data.ts)"
        )
