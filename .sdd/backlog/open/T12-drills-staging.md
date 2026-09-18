# T12 · Ensayos de fallo + script de staging del repo de entrega
assignee: W3
priority: p1

## Objetivo
Dos piezas para los criterios de resiliencia (10 pts) y entrega:

1. **Drills automatizados** (`src/albertitos/drills.py` + `python -m albertitos.drills`):
   ensaya y MIDE, con mocks/adapters (sin depender de red real):
   - proveedor de rung 5 caído / timeout ⇒ la página queda ESCALAR con motivo
     en evidencia y el lote sigue (degradación, no aborte);
   - 429 con Retry-After ⇒ backoff respetado, ninguna llamada extra;
   - crash del runner a mitad del lote ⇒ reanudación completa sin duplicados
     (usa el ledger T4; si T8 aún no está integrado, ejércelo contra un runner
     stub tras la misma interfaz);
   - evidencia corrupta en el ledger ⇒ la UI/lector la tolera (ya lo hace,
     testéalo formalmente).
   Salida: `.sdd/metrics/drills.json` con resultado POR drill (pass/fail,
   comportamiento medido) — el informe y la defensa se alimentan de aquí.
2. **`scripts/stage_delivery.sh`** (bash estricto): crea `~/delivery-repo` como
   repo git limpio con EXACTAMENTE `outcomes.jsonl`, `outcomes_lote2.jsonl`,
   `albertitos_plan.pdf` en la raíz; ANTES valida con `python -m
   albertitos.validate` ambos JSONL contra `caja-de-alberto/facturas/`; rechaza
   (exit 1) si falta cualquier archivo de los 500+40, si hay duplicados, result
   inválido, o si encuentra `apiKey|sk-|FACTURAS2009` en lo que va a copiar.
   Idempotente: re-ejecutar es seguro. NO lo ejecutes contra datos reales si
   outcomes.jsonl aún no existe — que falle limpio con mensaje claro.

## Criterios de aceptación
- Cada drill corre en tests (con mocks, sin red) y `drills.json` refleja resultados.
- El script de staging, probado con fixtures, produce un repo con EXACTAMENTE
  3 archivos y falla limpio ante JSONL inválido.
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.
