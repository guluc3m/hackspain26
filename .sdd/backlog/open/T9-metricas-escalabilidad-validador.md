# T9 · Métricas del store + datos de escalabilidad + validador de contrato
assignee: W3
priority: p1

## Objetivo
Tres piezas (continúan tu T6, `src/albertitos/report.py` + `src/albertitos/ui/ledger.py`):

1. **Extractor de métricas** desde las filas de evidencia del store/ledger
   (read-only): archivos/s medidos, latencia media y p95 por rung, coste por
   archivo y por lote (coste = nº llamadas × precio unitario en config, cada
   precio etiquetado medido/estimado), hardware (núcleos, RAM) y límites
   (throughput máximo estimado a partir de latencias medias del rung más lento).
   Salida: JSON en `.sdd/metrics/` + un `escalabilidad_datos.typ` incluíble por
   la plantilla del informe (`docs/report/escalabilidad.typ` — los números del
   informe salen de aquí, jamás hardcodeados).
2. **Fórmula de coste explícita** en la salida: coste_lote = extracción (CPU,
   horas×€/h estimado) + llamadas cloud (nº × €/llamada) + tokens de agentes,
   con cada término separado medido vs estimado.
3. **Validador de contrato** (`python -m albertitos.validate`): dado un
   outcomes.jsonl + el dir de facturas, comprueba: una línea por PDF exacto,
   `file_id` = basename exacto (sin ruta, sin normalizar), sin duplicados,
   `result` ∈ {PAGAR, NO_PAGAR, ESCALAR}. Exit 0/1 + reporte de diferencias.
   Es la MISMA validación que la organización hará con su referencia privada —
   que no se pase ni una.

## Criterios de aceptación
- Test con store sembrado: métricas correctas (calcula a mano el esperado) y
  `escalabilidad_datos.typ` generado.
- Test del validador: lote con duplicado falla; file_id normalizado falla;
  result inválido falla; lote correcto pasa (500 fixture nombres).
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.
