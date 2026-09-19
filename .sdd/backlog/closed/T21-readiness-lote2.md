# T21 · Readiness del lote 2: simulación de extremo a extremo
assignee: W2
priority: p1

## Objetivo
Que el sábado a las 18:00 Madrid sea un cambio de DATOS, no de código. Simula
hoy el flujo completo del lote 2 con fixtures y deja el camino listo:

1. **Ingesta de un lote externo**: `python -m albertitos.run --only 'lote2/*'`
   (o un --facturas-dir alternativo) debe ingerir 40 PDFs de un directorio
   distinto con file_id = basename exacto, sin tocar el lote 1 (ledger/run
   separados).
2. **Regla v4 activada**: usa tu regla_v4.yaml paramétrica (T13); activa la
   regla nueva REGLA_V4 en un fixture de 10 facturas y verifica el diff de
   impacto (mecanismo T13): qué decisiones cambian y cuáles no.
3. **Cambio de dato del maestro**: aplica un parche (p.ej. cambia el NIF o el
   importe de un proveedor) y verifica el reprocesado dirigido: sólo los que
   cruzan con ese dato cambian de resultado; el histórico coexiste.
4. **Emisión**: el flujo debe poder emitir outcomes_lote2.jsonl (40 líneas,
   validador en verde) SIN tocar outcomes.jsonl del lote 1.

## Entregable
`python -m albertitos.lote2 --dry-run` (o el comando equivalente documentado en
scripts/) que ejecuta la simulación y deja en .sdd/metrics/lote2-sim.json el
resultado: nº ingeridos, qué cambiaría con v4, diff reprocesado, validador.

## Criterios de aceptación
- Test: la simulación completa corre sin red y es determinista.
- Test: outcomes.jsonl del lote 1 queda byte-idéntico tras la simulación.
- pytest+ruff verde; ticket a closed en el mismo commit.

---

## Resolución (W2 — 2026-09-19)

Implementado `src/albertitos/lote2.py` (`python -m albertitos.lote2 --dry-run`,
documentado también en `scripts/lote2_readiness.sh`) + `tests/test_lote2_sim.py`.
Resultado medido commiteado en `.sdd/metrics/lote2-sim.json`.

Decisiones documentadas:
- **Sandbox, no producción**: la simulación corre TODO el flujo en
  `<store_root>/lote2-sim/` (store + ledger propios); el store real
  (`.sdd/store.db`) y `outcomes.jsonl` del lote 1 no se abren jamás —
  test byte a byte. Es determinista: dos corridas ⇒ mismo JSON byte a byte
  (sin timestamps, sin timings).
- **Ingesta de lote externo (1)**: `Runner` contra directorio distinto con
  file_id = basename exacto, store sandbox y `run_id='lote2-base'` (ledger y
  run separados del lote 1). Sábado (flujo real documentado en el módulo y
  en el script): `--facturas <dir-lote2> --outcomes outcomes_lote2.jsonl
  --run-id lote2 --emit-scope lote`.
- **Emisión con scope (nuevo en emit.py)**: `emit_outcomes(only_files=...)`
  y `RunnerConfig.emit_scope='lote'` (`--emit-scope lote`) — el lote 2 puede
  convivir con el lote 1 en el MISMO store y emitir SOLO sus 40 líneas
  (test: store mixto ⇒ 10 líneas del lote 2 / 13 sin scope), sin mezclar ni
  tocar outcomes.jsonl.
- **v4 como datos (2)**: primera corrida con `regla_v4.yaml` desactivada
  (no-op exacto, 10 PAGAR) y segunda con copia ACTIVADA en el sandbox
  (`importe_minimo=3000`): el diff T13 muestra 5 decisiones cambian / 5 se
  mantienen — medido en el JSON.
- **Cambio de dato (3)**: parche en memoria que cambia el NIF del proveedor
  P001 (`tests/fixtures/patch_nif.yaml`, el ejemplo del ticket) +
  `reprocesar()`: EXACTAMENTE 1 factura cambia (la que cruza con B46102331),
  0 las demás; los tres runs (`lote2-base/v4/dato`) coexisten en
  `decision_runs`, jamás sobreescritos.
- **Bug latente corregido (hallado por esta simulación)**:
  `Store.all_decisions()/run_decisions()` no mapeaban las columnas nif/iban
  añadidas en T13 (el parche de T13 era por pedido, así que no se detectó);
  los afectados por NIF/IBAN salían vacíos. Corregido + tests.
  También: exclusión de contexto del lote por `force` generalizada (un
  re-run completo no se convierte en falso doble pago contra sí mismo).
- Suite: 193 passed + ruff limpio. Los 3 fallos de `test_defensa.py` /
  `test_ui_lote1.py` (W3) son PREEXISTENTES en HEAD limpio y ajenos a T21:
  dependen de `.sdd/lote1/ledger/`, que no existe en disco en este worktree.
