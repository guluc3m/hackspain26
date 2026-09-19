"""Los dos motores de la arquitectura (docs/report/architecture.typ).

Dos bloques estrictamente separados:

- ExtractionEngine: bloque de extracción — PDF -> features (extract/) ->
  campos con todos los candidatos (parse/).
- DecisionEngine: bloque de decisión — campos + maestro + config ->
  resultado con las reglas que lo produjeron (rules/).

La superficie de llamada de ambos está definida; las llamadas desde la app
aún NO están definidas (los métodos lanzan NotImplementedError) y la UI
consume la referencia sintética (frontend/src/mock/data.ts).
"""

from .decision import DecisionEngine
from .extraction import ExtractionEngine

__all__ = ["DecisionEngine", "ExtractionEngine"]
