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

## Cerrado — decisiones tomadas (W3)

- **Métricas** (`src/albertitos/metrics.py`): lee el ledger en SOLO LECTURA
  (mismo formato JSONL kind=evidence/decision que W1/W2 ya escriben; reutiliza
  `ui.ledger.load_ledger`, tolerante a líneas corruptas). Rung derivado del
  stage (`extract:rungN_*` → `rungN`; si no, el extractor). Latencia media y
  p95 por rung solo sobre filas con éxito; los `skipped` cuentan como
  omitidos y no como llamadas; las llamadas cloud fallidas sí cuentan como
  llamadas emitidas (consumen cuota) pero no como latencia.
- **Throughput**: archivos/s medido = archivos con decisión ÷ suma de TODAS
  sus latencias (sin paralelismo, nota explícita); límite secuencial
  ESTIMADO = 1/latencia media del rung más lento. Hardware (núcleos, RAM de
  /proc/meminfo) medido.
- **Fórmula de coste explícita** con términos separados y etiquetados:
  extracción CPU (horas × €/h, precio ESTIMADO en config), llamadas cloud
  (nº × €/llamada, precio ESTIMADO en config), tokens de agentes (sin
  telemetría ⇒ «sin datos», jamás cifra inventada). Precios en `PRECIOS`
  (config, etiquetados), no en código de decisión.
- **Salida**: `.sdd/metrics/metrics.json` (estado regenerable, no se commita)
  + `docs/report/escalabilidad_datos.typ` (bindings #let, SÍ se commita) que
  `escalabilidad.typ` importa; secciones nuevas: fórmula de coste, coste por
  archivo/lote, rendimiento por rung, throughput/límite, hardware. El PDF
  compila (10 páginas) con las tablas nuevas renderizadas.
- **Validador** (`src/albertitos.validate`, `python -m albertitos.validate`):
  una línea por PDF exacto, basename exacto (detecta rutas Y variantes
  normalizadas NFKC/casefold/strip comparando formas normalizadas de ambos
  lados), sin duplicados, result ∈ contrato. Exit 0/1 + reporte de
  diferencias por línea. Probado con fixture de 500 nombres.
- **Test**: 9 tests nuevos (5 métricas con esperado calculado a mano +
  validador). `uv run pytest` (63) y ruff en verde; sin secretos.
