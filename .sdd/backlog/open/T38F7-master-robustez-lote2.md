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
