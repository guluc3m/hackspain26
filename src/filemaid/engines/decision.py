"""Motor de decisión (architecture.typ §Bloque de toma de decisiones).

Campos ExtractionField + maestro + config de reglas (rules/) -> Decision:
resultado y reglas que lo produjeron. Determinista y puro: mismos inputs +
misma config => misma salida, byte a byte.

La llamada desde la app aún no está definida: el método define el contrato y
lanza NotImplementedError. La UI usa la referencia sintética mientras tanto.
"""

from __future__ import annotations

from filemaid.types import Decision, ExtractionField


class DecisionEngine:
    """Bloque de decisión: campos -> resultado, puro y determinista."""

    def decidir(
        self,
        fields: list[ExtractionField],
        invoice_id: str,
        file_id: str,
    ) -> Decision:
        """Evalúa las reglas sobre los campos y emite la Decision."""
        raise NotImplementedError(
            "llamada al motor de decisión sin definir: los datos de la UI "
            "son sintéticos (frontend/src/mock/data.ts)"
        )
