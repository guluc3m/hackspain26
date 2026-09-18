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
