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

## Cerrado — decisiones tomadas (W3)

- **Drills contra las costuras REALES** (no stubs innecesarios):
  - rung5-provider-caido: usa la escalera real (`ExtractionLadder` + fixture
    `scan_001.pdf`) con `httpx.MockTransport` que cae ⇒ 3 intentos medidos,
    evidencia con `provider-failed:…`, página en cola de revisión
    (escalated=True), lote continúa. Degradación, no aborte.
  - backoff-429: `read_page` con transport que devuelve 429+Retry-After, 429
    sin Retry-After y luego 200; `time` del módulo cloud sustituido solo en
    el drill ⇒ delays medidos: Retry-After respetado (con cap) + exponencial;
    3 llamadas exactas (cero extra).
  - crash-reanudacion: contra el runner REAL `pipeline.run_batch` + `Store`
    (T4) con `fail_injector` en el ítem 2 ⇒ crash, reanudación completa,
    0 duplicados en store, reutilizados por caché = decididos pre-crash.
  - ledger-corrupto: 3 líneas corruptas ignoradas, solo 2 registros válidos
    cargados, nada inventado (lector de UI/métricas).
- **Salida**: `.sdd/metrics/drills.json` con pass/fail + mediciones por drill
  (intentos, delays, decididos pre/post crash, líneas ignoradas). CLI
  `python -m albertitos.drills` con exit 0/1. Verificado end-to-end: 4/4 PASS.
- **scripts/stage_delivery.sh** (bash estricto, `set -euo pipefail`): valida
  ambos JSONL con `python -m albertitos.validate` ANTES de tocar nada (dirs
  de facturas por lote vía env), escaneo de secretos
  (apiKey|sk-|FACTURAS2009), repo git en DESTINO (default ~/delivery-repo)
  con EXACTAMENTE los 3 entregables en raíz, idempotente (commit solo si
  cambió algo; verificado: 2ª ejecución = 1 solo commit, cambio real = 2º
  commit). Falla limpio (exit 1 + mensaje) si falta un artefacto, hay
  duplicado, result inválido, file_id de otro lote o secreto; nada se copia
  antes de validar.
- **Tests**: 6 de drills + 6 del script (happy path, idempotencia, fallo
  limpio). Suite completa 132 passed, ruff limpio, sin secretos reales.
