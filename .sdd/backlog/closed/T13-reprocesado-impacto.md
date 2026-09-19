# T13 · Reprocesado e impacto (cambio de regla/dato → diff de decisiones)
assignee: W2
priority: p1

## Objetivo
`src/albertitos/reprocess.py` + `python -m albertitos.reprocess`: la pieza que
hace viable el lote 2 y el cambio de dato del maestro SIN rehacer todo.
(AGENTS.md §13: "el reprocesado y su diff deben funcionar desde el diseño".)

## Requisitos
1. **regla v4 como datos**: crea `src/albertitos/rules/regla_v4.yaml` partiendo
   de regla_v3.yaml con la estructura esperada del cambio (regla nueva
   `REGLA_V4` marcada PENDIENTE-ESPECIFICACIÓN y sus umbrales paramétricos).
   Cargar v3 o v4 es elegir un archivo — cero cambios de código en el motor.
2. **Cambio de dato del maestro**: dado un parche (p.ej. `--maestro-patch
   patch.yaml` que modifica una fila de Proveedores/Pedidos), determina los
   archivos afectados (los que cruzan con ese proveedor/pedido/NIF/IBAN).
3. **Reprocesado dirigido**: re-ejecuta SÓLO los afectados (y los marcados
   ESCALAR si `--all-scaled`), conservando el histórico: cada decisión nueva
   coexiste con la anterior en el store (run_id distinto), jamás se sobreescribe.
4. **Diff de impacto**: `--diff` compara dos runs y produce
   `.sdd/metrics/impacto.json` + reporte legible: file_id, resultado antes →
   después, código de regla responsable, nº afectados, nº escalados. La UI
   (Facturas/Reglas) debe poder leer ese diff (coincide con el formato que ya
   consume T5).
5. Determinista: mismo parche ⇒ mismo diff byte a byte.

## Criterios de aceptación
- Test: con fixture de 10 facturas, cambia un importe del maestro ⇒ diff muestra
  exactamente las facturas que cruzan con ese pedido y ninguna otra; re-run idéntico.
- Test: v4 con la regla PENDIENTE desactivada produce el MISMO resultado que v3
  (regresión de no-op); al activarla, cambia lo esperado.
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.

---

## Resolución (W2 — 2026-09-19)

Implementado `src/albertitos/reprocess.py` (`python -m albertitos.reprocess`),
`src/albertitos/rules/regla_v4.yaml`, soporte de reglas paramétricas en
`rules/config.py` + `rules/engine.py` (`REGLA_V4`), histórico de runs en
`store.py` (`decision_runs` + nif/iban en invoices, con migración idempotente
de esquema) y soporte en `run.py` (`only_list`, `force`, `run_id`,
`maestro_patch`) + `tests/test_reprocess.py` con fixtures `tests/fixtures/lote10/`
(10 facturas PAGAR reales con pedidos únicos), `maestro_lote10.xlsx` y
`patch_po.yaml`.

Decisiones documentadas:
- **v4 como datos**: `regla_v4.yaml` replica la v3 con la regla nueva
  `REGLA_V4` marcada PENDIENTE-ESPECIFICACIÓN y `activa: false`; sus umbrales
  viven en `rule_params` (yaml). Desactivada es un no-op exacto frente a la v3
  (test). Activarla = editar el yaml (`activa: true` + ajustar
  `importe_minimo`) — cero cambios de código en el motor. `load_config`
  acepta por regla `kind`/`activa`; las desactivadas quedan en el snapshot
  (`reglas_pendientes`) y el motor no las evalúa.
- **Parche de maestro EN MEMORIA** (`apply_master_patch`): valida campos
  conocidos (razon_social/nif/iban; importe/estado/nif/fecha), actualiza el
  índice por NIF si el NIF cambia, NO altera el sha256 ni el Excel del
  submódulo; el resumen antes/después queda registrado como provenance.
- **Afectados (criterio exacto)**: facturas cuyo `pedido` coincide con un
  pedido modificado, o cuyo NIF/IBAN almacenado coincide con el valor ANTES
  o DESPUÉS de un proveedor modificado. Todo sobre lo que el store guardó
  al decidir (por eso `invoices`/`decision_runs` ahora traen nif e iban).
- **Histórico, jamás sobreescrito**: `record_decision` escribe estado actual
  (tabla `invoices`) + fila de histórico `(file_id, run_id)` en
  `decision_runs`. El run base permanece byte a byte tras un reprocesado (test).
- **Bug de diseño destapado por los tests y corregido**: al re-decidir un
  subset, sus decisiones antiguas NO cuentan como "ya vistas" en el contexto
  del lote (un reprocesado no debe convertirse en falso NO_DOUBLE_PAYMENT
  contra sí mismo). `Runner.run()` excluye el subset (force/only_list) del
  contexto prev.
- **Diff de impacto determinista** (`diff_runs` + `write_impact`): compara la
  INTERSECCIÓN de file_id entre los dos runs; lo que solo está en uno se
  informa aparte (`solo_en_run_base/solo_en_run_nuevo`), nunca como "cambio".
  Salida: `.sdd/metrics/impacto.json` (la UI lee esta estructura) +
  `.sdd/metrics/impacto.txt` legible en español llano. Sin timestamps: mismo
  parche ⇒ mismo diff byte a byte (test).
- **Regla responsable** en el diff: primera `anomaly:UNKNOWN`, si no
  `gate:FAIL` del run nuevo.
- Aceptación verificada: con el lote10, cambiar el importe de UN pedido ⇒
  objetivo = exactamente la factura que cruza con ese pedido y ninguna otra;
  re-run idéntico; `--all-scaled` reproduce solo los ESCALAR actuales
  (seedeados con un scan real); v4 desactivada ≡ v3 y v4 activada produce el
  efecto paramétrico esperado (total < importe_minimo ⇒ ESCALAR).
- Suite completa: 143 passed; `uv run ruff check .` limpio.
