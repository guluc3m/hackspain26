
---

## Resolución (W2 — 2026-09-19)

Implementado `src/albertitos/lote2.py` (`python -m albertitos.lote2 --dry-run`,
envuelto por `scripts/lote2_readiness.sh`) + soporte de ingesta separada en
`run.py` (`--run-id`, `--emit-scope todo|lote`) y `emit.py` (`only_files`) +
`tests/test_lote2_sim.py` (8 tests). Simulación real ejecutada: resultado en
`.sdd/metrics/lote2-sim.json` (determinista, sin timestamps).

Decisiones documentadas:
- **Ingesta separada**: el lote 2 se ingiere con `--facturas <dir>` a un store
  SANDBOX (`<store-root>/lote2-sim/store`) con `run_id='lote2-base'`; file_id =
  basename exacto; el store y outcomes.jsonl del lote 1 no se abren siquiera
  (test del hash byte a byte de `.sdd/store.db` y `outcomes.jsonl`).
- **Producción del sábado documentada en el script**: lote 1 y lote 2 conviven
  en el MISMO store (`--run-id lote2` + `--emit-scope lote`); la emisión del
  lote 2 con `only_files` produce SOLO sus líneas sin mezclar el lote 1
  (test con store mixto: 10 + 3 file_ids ⇒ outcomes_lote2 = 10 líneas).
- **v4 como datos**: corre con `regla_v4.yaml` (no-op) y luego con una COPIA
  del yaml con `activa: true` y `importe_minimo: 3000` — cambio de yaml, cero
  código. Diff de impacto (T13) medido: 5 decisiones cambian, 5 se mantienen.
- **Cambio de dato del maestro**: parche `tests/fixtures/patch_nif.yaml`
  (NIF de P001 ⇒ B99999999) en memoria + reprocesado dirigido: SOLO la
  factura que cruza con ese NIF cambia (PAGAR → NO_PAGAR); los 3 runs
  (`lote2-base`, `lote2-v4`, `lote2-dato`) coexisten en `decision_runs`.
- **Emisión validada**: `outcomes_lote2.jsonl` (10 líneas, file_id exactos)
  pasa el validador de contrato; el flujo del sábado con 40 PDFs es el mismo
  comando.
- **Determinismo**: mismo fixture ⇒ mismo JSON byte a byte (dos corridas
  idénticas; el JSON no lleva timestamps ni latencias).
- Arreglo de contexto del lote (run.py): el exclusión de re-decididos ahora
  usa el conjunto REAL de archivos en vuelo cuando `force=True` (no solo
  `only_list`), coherente para reprocesado y para re-corridas v4.
- De paso: `.sdd/lote1` es el symlink documentado → `/home/deploy/fleet/w1/.sdd`
  (SOLO LECTURA); estaba ausente en este worktree y hacía fallar los tests de
  T20/defensa y T16/ui-lote1 — creado (estado runtime, gitignored, no commit).
- Suite completa: 197 passed; `uv run ruff check .` limpio.
