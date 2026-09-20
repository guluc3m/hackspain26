# NOTA de provenance — `data_outcomes_lote1.jsonl`

Fecha: 2026-09-20. Verificado contra `src/filemaid/rules/rules.py` y el histórico git
(completo, `git log --all`). Este fichero NO se regeneró: es la evidencia original de la
corrida del lote 1 y se mantiene como trazado histórico.

## Advertencia

**Esta evidencia fue producida por versiones del motor anteriores a la actual.** Mezcla:

- `engine_version`: 392 líneas `runner-1.0.0` + 108 líneas `runner-1.1.0` (500 total).
- `config_version`: uniforme `v3.0-2026-09-19`.
- `rule_ids`: **13 códigos** por línea, mientras que el motor actual (`RULE_CODES`,
  `src/filemaid/rules/rules.py:320`) declara **8**. La distribución de resultados
  (PAGAR 433 / NO_PAGAR 22 / ESCALAR 45) es la real de esa corrida y es la que narra el vídeo.

## Mapeo de los 13 códigos históricos → 8 reglas actuales

| Código histórico en el JSONL | Estado en el motor actual | Nota |
|---|---|---|
| `NIF_IN_MASTER` | Regla actual (8) | Idéntico. |
| `IBAN_MATCHES_MASTER` | Regla actual (8) | Idéntico. |
| `ORDER_BELONGS_TO_SUPPLIER` | Regla actual (8) | Idéntico. |
| `ORDER_AMOUNT_MATCHES` | **Alias interno de `ORDER_BELONGS_TO_SUPPLIER`** | El cruce de importe factura↔pedido vive dentro de `OrderBelongsToSupplier` (`rules.py:120-139`: `amounts_match(float(total.value), order.importe, TOLERANCE_EUR)` → FAIL propio de esa regla). No existe como regla separada. |
| `TOTALS_MUST_MATCH` | Regla actual (8) | Idéntico. |
| `IVA_CONSISTENT` | Regla actual (8) | Idéntico. |
| `DATE_VALID_NOT_FUTURE` | Regla actual (8) | Idéntico. |
| `ORDER_PENDING` | Regla actual (8) | Idéntico. |
| `NO_DOUBLE_PAYMENT` | Regla actual (8) | Idéntico. |
| `NO_EMBEDDED_INSTRUCTIONS` | **No implementado** (aspiracional) | Sin implementación ni alias en ninguna versión del motor (verificado en el histórico git completo). |
| `PROVEEDOR_FANTASMA` | **No implementado** (aspiracional) | Ídem. El caso que cubriría lo detecta hoy `NIF_IN_MASTER`/`IBAN_MATCHES_MASTER` (proveedor fuera del maestro → FAIL → ESCALAR). |
| `AMOUNT_OUTLIER` | **No implementado** (aspiracional) | Ídem. |
| `PEDIDO_EN_REVISION` | **No implementado** (aspiracional) | Ídem. El caso que cubriría lo detecta hoy `ORDER_PENDING` (pedido no confirmado → UNKNOWN → ESCALAR). |

En el set `rule_ids` de cada línea del JSONL: los 8 códigos de `RULE_CODES` son las reglas
reales evaluadas; `ORDER_AMOUNT_MATCHES` es el desglose histórico del cruce de importe hoy
incluido en `ORDER_BELONGS_TO_SUPPLIER`; los 4 restantes son comprobaciones de la normativa
que el motor actual no evalúa. Veredictos medidos de esos 4 en las 500 filas:
`NO_EMBEDDED_INSTRUCTIONS` 491 PASS / 9 UNKNOWN; `PROVEEDOR_FANTASMA` 497 PASS / 3 UNKNOWN;
`AMOUNT_OUTLIER` 470 PASS / 30 UNKNOWN; `PEDIDO_EN_REVISION` 498 PASS / 2 UNKNOWN.
Ninguno registra FAIL.

## Medido vs estimado

- **Medido** (parseo del JSONL y del árbol, reproducible): 500 filas; 392×`runner-1.0.0` +
  108×`runner-1.1.0`; `config_version` uniforme `v3.0-2026-09-19`; 13 códigos distintos
  con un único set de `rule_ids` en las 500 filas; distribución PAGAR 433 / NO_PAGAR 22 /
  ESCALAR 45; veredictos por código citados arriba; los 8 códigos vigentes en `RULE_CODES`
  (`rules.py:320`); el cruce de importe dentro de `OrderBelongsToSupplier`
  (`rules.py:120-139`); cobertura del store local (421 decisiones, 379/500 del lote 1);
  ausencia de los 4 códigos aspiracionales y de `ORDER_AMOUNT_MATCHES` como regla en todo
  el histórico git (`git log --all` sobre `*rules/rules.py` y `master/rules.yaml`).
- **Estimado** (razonamiento, no verificable con los artefactos actuales): por qué el JSONL
  lista 13 códigos que el motor nunca tuvo — la hipótesis más plausible es que el runner
  de la corrida original evaluaba una checklist normativa más amplia (borrador de reglas
  futuras) cuyos veredictos se registraron en la evidencia; ese runner no está en este
  repo, así que no puede confirmarse. También es estimado que los 4 códigos extra no
  condicionaron ningún resultado final: en la corrida solo el motor persistido decide, y
  no hay forma de reconstruir su influencia desde el JSONL (aunque ningún FAIL registrado
  y la coherencia con `RULE_CODES` lo hacen muy improbable).

## Por qué no se regeneró con el motor actual

Se evaluó la regeneración desde el store local (`data/`, PouchDB) y se descartó:

1. El store local tiene 421 documentos de decisión (419 `file_id` únicos) y cubre solo
   **379 de los 500** `file_id` del lote 1: faltarían 121 regeneraciones completas
   (extracción + parse + reglas), no un simple re-export.
2. El único lote completo en este store es el lote 2 (40 decisiones, `run_id`
   `533c485ca0d1`); el lote 1 se corrió en otra máquina y su `batch_result` no está aquí.
3. El motor evolucionó desde la corrida original (ADR-06: 86 falsos NO_PAGAR corregidos
   en el reproceso de 108): regenerar con el motor actual puede cambiar resultados y
   alterar la distribución 433/22/45 fijada en el vídeo ya renderizado.

La evidencia se mantiene, por tanto, como traza histórica etiquetada por esta nota.
Para la defensa: citar la corrida tal cual, apoyarse en esta nota si se pregunta por
los códigos extra, y señalar `RULE_CODES` como el conjunto vigente.
