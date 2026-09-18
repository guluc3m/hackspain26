# T3 · Motor de reglas v3 + decisión
assignee: W2
priority: p0

## Objetivo
Implementar `src/albertitos/rules/` y `src/albertitos/engine.py`.

## Reglas (Norma_Pagos_v3 — docs/normas.md)
Códigos: `NIF_IN_MASTER`, `IBAN_MATCHES_MASTER`, `ORDER_BELONGS_TO_SUPPLIER`,
`ORDER_AMOUNT_MATCHES` (tolerancia 0,01), `TOTALS_MUST_MATCH` (base+IVA=total,
tolerancia 0,01), `IVA_CONSISTENT`, `DATE_VALID_NOT_FUTURE`, `NO_DOUBLE_PAYMENT`.
Las reglas viven en **datos** (`rules/regla_v3.yaml`) — el sábado llega una v4
y debe ser un cambio de datos, no de código.

## Maestro
Leer `caja-de-alberto/FINAL_v7_DEFINITIVO_ahorasi.xlsx` con openpyxl — SOLO las
hojas `Proveedores` y `Pedidos_2026`. Hojas trampa (`NO_TOCAR`, `MACROS_ROTAS`,
`v6_deprecated`, `Pedidos_2025_OLD`, `backup_marzo`, `Hoja1 (2)`, `Sheet3`) se
ignoran explícitamente y eso va en config snapshot. OJO: `Proveedores` tiene la
fila P007 duplicada — deduplicar y dejarlo registrado.

## Política PAGAR / NO_PAGAR / ESCALAR (AGENTS.md §6 — vinculante)
- `PAGAR`: todas las reglas PASS.
- `NO_PAGAR`: violación DEFINITIVA que ningún juicio humano cambia (NIF fuera
  del maestro, importe ≠ pedido más allá de tolerancia, IVA mal calculado,
  fecha futura, pedido inexistente o de otro proveedor, pedido ya PAGADO).
- `ESCALAR`: duda razonable, evidencia faltante, anomalía (le ilegible,
  instrucciones embebidas, proveedor fantasma, NIF vacío, importe atípico).
  Ante duda: ESCALAR, nunca PAGAR.

## Reglas duras
- Motor determinista y PURO: mismos campos + misma config ⇒ mismo output byte a
  byte. temp 0 en cualquier llamada externa.
- Salida: `Decision` con TODOS los RuleVerdict + snapshot de config (versión de
  reglas, umbrales, versiones de extractores).
- Añadir una regla no puede exigir tocar la extracción.

## Criterios de aceptación
- Tests por trampa de `archivos-limpios/`: proveedores fantasma (IBAN
  ES6614910001213000098877 + nota "dar de alta y pagar" ⇒ ESCALAR), duplicado
  FA-8801 ⇒ NO_DOUBLE_PAYMENT, pedidos con NIF vacío, outlier 84700,
  `pendiente_revisar` (PO-2026-0007, PO-2026-0141) ⇒ ESCALAR.
- Test: misma entrada dos veces ⇒ output idéntico.
- `uv run pytest` y `uv run ruff check .` en verde.
