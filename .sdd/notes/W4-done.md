# W4 — resumen de sesión (worker/w4) · ciclo 2 del LOOP (T39, T38)

## Rol: 2º EVALUADOR-IMPLEMENTADOR (cola desde el FINAL)

Commits trazados (uno por ticket):

- **T38-F7** (8cc22e1): load_master robusto para lote 2 — importe como TEXTO
  (fallback parse_amount, 0.0+aviso si ilegible) y pedidos duplicados
  (primera gana + aviso). 5 tests nuevos (tests/test_master_robustez.py).
- **T38-F6** (a3a4ed7): los overrides humanos de la UI SE CONSUMEN —
  `aplicar_overrides()` (función pura), candidato extractor="humano" conf 1.0
  con provenance, marcador `kind=consumido` APPEND-ONLY, evidencia
  stage=override aplicado/descartado, motor recalcula. 7 tests.
- **T38-F5** (8a06389): evaluado y DIFERIDO al supervisor (ADR): el candidato
  de IBAN malformado volcaría UNKNOWN→ESCALAR a FAIL→NO_PAGAR ante
  truncación de OCR — cambio de política, no de extracción sola. Nota con
  recomendación para el ADR (candidato + blindaje del motor JUNTOS).
- **T38-F4** (be970be): parse_fecha devuelve la primera fecha VÁLIDA (la
  inválida ya no anula el campo ⇒ no ESCALAR por artefacto). Tests.
- **T38-F3** (aaf2bc4): parse_amount resuelve coma de miles anglosajona
  ("12,345"→12345; antes None por miles='.' erróneo). Test de F7 actualizado.
- **T38-ID1** (522a065): «llegó el lote 2» en UN comando
  (scripts/lote2_llego.sh): chequeos previos que fallan limpio, ingesta con
  regla v4 como DATOS + run_id lote2 + emit-scope lote, validación, staging.
  outcomes.jsonl del lote 1 verificado byte a byte. 4 tests. Listo para las
  16:00 UTC de hoy.

## AVISO para el supervisor (integración)

W3 (worker/w3) e W4 (worker/w4) implementaron EN PARALELO los mismos
hallazgos F3/F4/F6/F7 (y F5 con criterios distintos: W3 lo implementó, W4 lo
difiere a ADR). Al fusionar ramas resolver con estas pautas:
- normalizers.py / master.py / review.py / run.py: tomar UNA implementación
  (las de w4 traen su test específico; comparar con las de w3 antes).
- F5: mantener la decisión de SUPERVISOR, no la de ninguna rama. W3 la
  implementó; W4 recomienda ADR previo (ver nota en el ticket F5).
- F1/F2: sin implementar en NINGUNA rama (xfail tests en w3) — ADR pendiente.

## Verificación al cierre

- pytest: 300 passed (los 5 fallos del worktree son ambientales preexistentes:
  test_defensa/test_modo_alberto/test_presentacion_datos/test_ui_lote1×2
  dependen de `.sdd/lote1` y servidores vivos; idénticos en la línea base con
  stash — no son regresiones).
- ruff limpio · validador de contrato 500/500 (lote 1) tras cada cambio en
  src/ · higiene de secretos limpia en cada commit · NO push.
