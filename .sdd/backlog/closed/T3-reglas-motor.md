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

---

## Resolución (W2 — 2026-09-19)

Implementado `src/albertitos/rules/` (`regla_v3.yaml`, `config.py`, `master.py`,
`engine.py`) + `tests/test_rules.py` y fixture `tests/fixtures/maestro_fixture.xlsx`.

Decisiones documentadas:
- **Reglas como datos**: códigos, clase (gate/anomaly), umbrales, marcadores de
  anomalías, estados pagables y hojas ignoradas viven en `regla_v3.yaml`; la v4
  del sábado será cambiar ese yaml. Códigos sin implementación rechazan la carga.
- **Política de resultado (AGENTS.md §6, orden vinculante)**: (1) UNKNOWN de
  clase `anomaly` ⇒ ESCALAR; (2) FAIL de clase `gate` ⇒ NO_PAGAR; (3) cualquier
  otro UNKNOWN ⇒ ESCALAR; (4) si no, PAGAR. Anomalía + violación definitiva ⇒
  ESCALAR (ante duda razonable, escalar antes de NO_PAGAR).
- **Reglas anomaly nuevas (datos, no código)**: `NO_EMBEDDED_INSTRUCTIONS`
  (marcadores imperativos sobre el texto crudo — son datos, nunca comandos),
  `PROVEEDOR_FANTASMA` (IBAN ES66…8877), `AMOUNT_OUTLIER` (>50000 EUR),
  `PEDIDO_EN_REVISION` (pedidos de la hoja `pendiente_revisar` del maestro).
- **Maestro**: SOLO `Proveedores` + `Pedidos_2026` + `pendiente_revisar`;
  trampas ignoradas y registradas en snapshot; P007 duplicado deduplicado
  (primera ocurrencia gana) y registrado en `duplicados_deducidos`. El
  submódulo `caja-de-alberto/` permanece byte a byte intacto (test de solo
  lectura incluido).
- **NIF vacío en Pedidos**: se cruza por `ProveedorID → NIF del maestro`;
  el NIF vacío del pedido no castiga si el proveedor cruza bien.
- **Estados pagables**: la norma pide PENDIENTE; el maestro marca ABIERTO
  (=pendiente de pago). Config `estados_pagables: [ABIERTO, PENDIENTE]`;
  PAGADO nunca es pagable.
- **Colapso de candidatos**: solo cuando una regla necesita un escalar; se
  elige el de mayor confianza y se registra (elegido, por qué) en `consumed`.
- **Pureza**: `fecha_referencia` se inyecta (el motor no lee el reloj);
  misma entrada + misma config ⇒ output idéntico (test de bytes).
- Verificación sobre el corpus real: PAGAR 347 / NO_PAGAR 108 / ESCALAR 45;
  traps FA-8801 (duplicado), fantasmas, outlier 84700 y pendiente_revisar
  (PO-2026-0007/0141) en el resultado esperado.
