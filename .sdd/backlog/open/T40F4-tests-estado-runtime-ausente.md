# T40F4 · Tests que dependen de estado runtime gitignored ⇒ rojos en worktree fresco
assignee: supervisor (decisión de provisionamiento; ficheros de W3/W4)
priority: p2
severidad: p2 (flaky de entorno, no de producto)

## Hallazgo (verificado hoy en worktree nuevo de W5)
Cinco tests dependen de estado runtime que NO está en git (`.sdd/lote1/`,
`.sdd/store.db`, cola de revisión) y por tanto van ROJOS en un worktree
recién clonado, aunque en la máquina donde se procesó el lote 1 pasan:
- `test_defensa.py::test_todos_los_ficheros_citados_existen`
  — cita `.sdd/lote1/ledger/ledger.jsonl` (gitignored).
- `test_ui_lote1.py::test_facturas_filtro_y_busqueda` y
  `test_reglas_umbrales_reales_y_sin_confianza` — store real vacío.
- `test_modo_alberto.py::test_confirmaciones_con_consecuencias`
  — la cola de revisión real está vacía ⇒ la página no trae `confirm(`.
- `test_presentacion_datos.py::test_determinismo_y_origen_medido`.

No son bugs del producto: los tests verifican contra el estado REAL del
lote 1 (correcto para la defensa). El problema es de PROVISIONING: el loop
tiene 3 workers y cualquier worktree nuevo hereda 5 falsos rojos.

## Opciones (decisión del supervisor)
a) **Semilla reproducible**: script que materialice el estado runtime en un
   worktree nuevo (reprocesar lote 1 en local o copiar el store validado).
   Recomendada: la defensa necesita el estado real de todos modos.
b) `skipif` con motivo honesto («estado del lote 1 ausente en este
   worktree») — conserva la verificación donde el estado existe, pero
   oculta los tests en worktrees nuevos.
Descartada: relajar los asserts (esconderría regresiones reales).

## Nota
NO implementado por W5: toca ficheros del dominio de W3/W4 (UI/defensa/
presentación) y la decisión es de provisioning, no de tests. Documentado
según T38 (hallazgo con repro, sin commit).