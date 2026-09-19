# T17 · Auditoría de trampas contra el lote 1 real
assignee: W1
priority: p0

## Objetivo
Las trampas conocidas (AGENTS.md §11) deben estar CORRECTAS en el outcomes.jsonl
real (347 PAGAR / 108 NO_PAGAR / 45 ESCALAR). Es la única oportunidad de
corregir la política antes de la validación binaria de la organización.

## Qué auditar (con el store real de .sdd/lote1 y outcomes.jsonl integrado)
1. **3 proveedores fantasma** (IBAN compartido ES6614910001213000098877 + notas
   "dar de alta y pagar"): esperado ESCALAR con motivo que cite la regla.
2. **Duplicado FA-8801** (`2026-05-28_P005.pdf` y `factura_8801.pdf`): el segundo
   NO_PAGAR (NO_DOUBLE_PAYMENT) o ESCALAR — verifica qué produjo y si es
   coherente con la doctrina §6.
3. **7 archivos con instrucciones embebidas**: ninguna puede haber cambiado el
   resultado (los datos nunca son comandos).
4. **Pedidos con NIF vacío** (PO-2026-0538…0557): resultado y motivo.
5. **Outlier 84700** y **pendiente_revisar** (PO-2026-0007, PO-2026-0141):
   ESCALAR esperado.
6. **26 scan_*.pdf**: revisa la distribución de resultados de las páginas que
   pasaron por rung 4 — ¿alguna confianzas sospechosamente altas con lectura
   dudosa? Lista las 5 peores por confianza para revisión.
7. **Los 108 NO_PAGAR**: muestra la distribución por código de regla que los
   decidió; si un solo código genera >60, detalla ejemplos y verifica que la
   regla se está aplicando con los datos correctos (no un bug de matching).

## Entregable
`.sdd/metrics/auditoria-trampas.md` con: tabla trampa → resultado obtenido →
esperado → VERDE/ROJO. Cualquier ROJO con análisis de causa (¿bug de extracción,
de matching, o política?). NO cambies resultados a mano: si algo está mal,
identifícalo y déjalo documentado — el supervisor decide si reprocesar.

## Criterios de aceptación
- Test: las trampas como fixtures leen outcomes.jsonl real y cada una assertion
  el resultado esperado (VERDE/ROJO explícito, no skip).
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.
