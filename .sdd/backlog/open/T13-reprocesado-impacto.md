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
