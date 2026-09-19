# T38-F7 · load_master: dos riesgos para el lote 2 (importe texto, pedido duplicado)
assignee: W2
priority: p2
severidad: p2

## Hallazgo (src/albertitos/rules/master.py)
1. `importe=float(row[3])` — si el ERP actualizado (lote 2, "podría cambiar un
   dato del maestro") trae el importe como TEXTO ("1.234,56"), `float()` lanza
   ValueError ⇒ load_master crashea ⇒ el runner completo cae. Repro: un xlsx
   con importe "1705,37" como texto.
2. `pedidos[pid] = Pedido(...)` — un pedido duplicado se SOBREESCRIBE (última
   gana) sin aviso, a diferencia de Proveedores (dedup + aviso registrado).
   El lote 2 ya avisaron de datos nuevos: si trae pedidos duplicados, el
   último manda silenciosamente.

## Propuesta
1. Fallback `parse_amount` (ya existe en normalizers) con aviso si falla.
2. Duplicados de pedido: primera gana + `avisos` como Proveedores (§11 ya lo
   hace con P007).
~15 líneas + tests. Solo lectura del maestro, sin tocar la decisión.

## Resolución (W4, T39 — ciclo evaluador-implementador)
APROBADO e implementado (commit `T38-F7`). Coste/beneficio: p2, ~20 líneas,
solo lectura del maestro, robustez exigida por la llegada del lote 2 (datos
nuevos, importe posiblemente como TEXTO); no toca el motor ni la política.

- `src/albertitos/rules/master.py`: `_parse_importe` — float directo si es
  numérico; si es texto, fallback `parse_amount`; si ni así, 0.0 + aviso
  `pedido_importe_ilegible:<pid>` (o `pedido_importe_vacio:<pid>`). Un
  maestro con importes de texto ya NO derriba el runner.
- Pedidos duplicados: primera ocurrencia gana + aviso
  `pedidos_deduplicados:<ids>` (mismo patrón que Proveedores).
- Tests: `tests/test_master_robustez.py` (5 casos, incl. no-crash con
  importe ilegible). Nota: el caso anglosajón "1,234" hoy devuelve 0.0+aviso
  porque `parse_amount` tiene el bug T38-F3 (fix pendiente, principio de la
  cola); el test lo documenta y deberá subir a 1234.0 cuando F3 aterrice.
- Verificado: pytest verde en lo tocante, ruff limpio, validador de contrato
  500/500 sobre el lote 1 tras el cambio en src/.
