# T4 · Store, ledger e idempotencia + emitir outcomes.jsonl
assignee: W2
priority: p0

## Objetivo
Implementar `src/albertitos/store.py` y `src/albertitos/emit.py`.

## Requisitos (AGENTS.md §5 — 24/7)
- SQLite en `.sdd/store.db` + ledger JSONL append-only en `.sdd/ledger/`.
- Estado NUNCA en memoria; NUNCA en /tmp.
- Idempotencia: clave `(sha256, stage, engine_version, config_version)`. Re-
  procesar un ítem completado es no-op que reutiliza evidencia.
- Cada fase escribe fila de evidencia; el histórico y las resoluciones escaladas
  se conservan (corpus de retroalimentación, architecture.typ §Retroalimentación).
- Reprocesable desde cualquier punto; un crash pierde como mucho el ítem en
  vuelo.

## Emisión
`outcomes.jsonl`: una línea por factura —
`{"file_id": "<nombre EXACTO del PDF>", "result": "PAGAR"|"NO_PAGAR"|"ESCALAR"}`
+ campos de traza opcionales (rule_id, evidencia, latencia, engine).
`file_id` jamás normalizado ni con ruta. Un objeto por factura, ambos lotes.

## Criterios de aceptación
- Test: correr dos veces el mismo lote produce el mismo outcomes.jsonl byte a
  byte y cero re-procesos (contadores de evidencia no crecen).
- Test: crash simulado a mitad (matar el proceso en el ítem N) ⇒ reanudar
  completa el lote sin duplicados.
- Validador de contrato: 500 file_id únicos de `caja-de-alberto/facturas/`,
  result ∈ {PAGAR, NO_PAGAR, ESCALAR}.

---

## Resolución (W2 — 2026-09-19)

Implementado `src/albertitos/store.py`, `src/albertitos/emit.py` y
`src/albertitos/pipeline.py` (glue de integración) + `tests/test_store_emit.py`.

Decisiones documentadas:
- **Store**: SQLite WAL en `<root>/store.db` + ledger JSONL append-only con
  fsync en `<root>/ledger/ledger.jsonl`. Root configurable (por defecto
  `.sdd/`); jamás /tmp. Tablas: `invoices`, `evidence` (append-only),
  `stage_cache`, `resolutions` (corpus de retroalimentación, architecture.typ
  §Retroalimentación).
- **Idempotencia**: clave `(sha256, stage, engine_version, config_version)`.
  Matiz documentado: el cache-hit es válido SOLO si el `file_id` ya tiene su
  fila de decisión en el store (dos PDFs distintos pueden compartir sha256;
  la fila por file_id es la fuente de verdad). Re-lote completo = 0
  reprocesos, evidencia y ledger sin crecer, outcomes byte a byte idénticos.
- **Crash-resume**: transacción por factura + cache después del commit de la
  fila; inyector de fallos en tests simula muerte en el ítem N y la reanudación
  completa el lote sin duplicados. Un crash pierde como mucho el ítem en vuelo.
- **pipeline.py (glue justificado)**: los criterios de aceptación exigen
  ejecutar un lote dos veces y simular crash — hace falta orquestación
  features→parse→decide→store. El extractor de features (rung 1 pypdf) es
  inyectable: cuando W1 integre la escalera completa se sustituye
  `extract_features` sin tocar store/emit.
- **EvidenceRow.file_id**: campo añadido a types.py (superset compatible del
  contrato §5): la UI necesita el join file_id↔evidencia.
- **Emisión**: `emit_outcomes` ordena por file_id exacto, claves contrato
  primero y trazas después; `validate_outcomes` comprueba file_id únicos y
  exactos contra el directorio de PDFs y resultados válidos.
- **order determinista del lote** = file_id ascendente: base del
  NO_DOUBLE_PAYMENT y de la reproducibilidad byte a byte.
- Contrato 500 verificado contra `caja-de-alberto/facturas/` (submódulo
  inicializado en el pin 18d43b3, solo lectura): 500 file_id únicos,
  resultados ∈ {PAGAR, NO_PAGAR, ESCALAR}, validador sin errores, lote
  completo en ~1,3 s medidos.
