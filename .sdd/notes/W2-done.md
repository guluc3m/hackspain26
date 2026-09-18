# W2 — resumen de cola cerrada (2026-09-19)

Tickets implementados por W2 (todos p0, uno a uno, cada uno con commit propio
y ticket movido a `.sdd/backlog/closed/`):

## T2 · Parser: features → campos con candidatos  (commit d550783)
- `src/albertitos/parse/`: `normalizers.py`, `extractors.py`, `parser.py`.
- Registro extensible de extractores por campo; TODOS los candidatos se
  conservan (extractor, value, confidence, feature_ref).
- Normalización ES: importes `1.234,56` → Decimal, fechas DD/MM/AAAA y
  "25 de enero de 2026" → ISO; validadores NIF (letra de control) e IBAN
  (mod-97) como señal de confianza, nunca veto (el corpus usa IBANs
  sintéticos: decisión documentada en el ticket cerrado).
- Campo extra `numero_factura` (necesario para el trap del duplicado FA-8801).
- Cobertura medida: 471/500 facturas del corpus extraen todos los campos; los
  29 restantes son scans sin capa de texto (26) + ilegibles (3).

## T3 · Motor de reglas v3 + decisión  (commit 2b9015c)
- `src/albertitos/rules/`: `regla_v3.yaml` (reglas COMO DATOS — la v4 del
  sábado será cambiar ese yaml), `config.py`, `master.py`, `engine.py`.
- Política §6 vinculante e implementada: anomaly-UNKNOWN ⇒ ESCALAR >
  gate-FAIL ⇒ NO_PAGAR > UNKNOWN ⇒ ESCALAR > PAGAR. Ante duda, ESCALAR.
- Maestro: solo `Proveedores`+`Pedidos_2026`+`pendiente_revisar`; hojas trampa
  ignoradas y registradas en el snapshot; P007 duplicado deduplicado y
  registrado; submódulo `caja-de-alberto/` intacto (test de solo lectura).
- Traps verificados sobre el corpus real: FA-8801 duplicado ⇒ NO_PAGAR;
  fantasmas (IBAN ES66…8877 + "dar de alta") ⇒ ESCALAR; outlier 84700 ⇒
  ESCALAR; PO-2026-0007/0141 (pendiente_revisar) ⇒ ESCALAR.
- Corpus real: PAGAR 347 / NO_PAGAR 108 / ESCALAR 45.
- Motor puro y determinista: `fecha_referencia` inyectada, misma entrada ⇒
  output idéntico (test de bytes).

## T4 · Store, ledger, idempotencia + outcomes.jsonl  (commit 569972a)
- `store.py` (SQLite WAL + ledger JSONL append-only con fsync, nunca /tmp),
  `emit.py` (emisión determinista + validador de contrato), `pipeline.py`
  (glue justificado: la prueba de idempotencia/crash exige orquestación; el
  extractor de features es inyectable para que W1 enchufe la escalera sin
  tocar store/emit).
- Idempotencia `(sha256, stage, engine_version, config_version)`; matiz
  documentado: cache-hit válido solo con fila de decisión del file_id en el
  store (dos PDFs distintos pueden compartir sha256).
- Crash simulado en el ítem N ⇒ reanudación completa el lote sin duplicados.
- Contrato 500 verificado contra `caja-de-alberto/facturas/` (submódulo
  inicializado en el pin 18d43b3, solo lectura, sin tocarlo).

## Estado final del worktree
- `uv run pytest -q`: 53 passed. `uv run ruff check .`: limpio.
- Fixtures committeadas: `tests/fixtures/facturas/` (3 PDFs reales),
  `tests/fixtures/scans/` (2 scans sin texto), `tests/fixtures/maestro_fixture.xlsx`
  (maestro con trampas: P007 duplicado, hojas trampa, pendiente_revisar).
- Dependencia nueva: `pyyaml` (justificada por el propio ticket T3:
  reglas-como-datos en YAML).
- Submódulo `caja-de-alberto/` inicializado en el pin indicado y sin ninguna
  modificación.
- Pendientes para otros workers: T1 (W1, escalera completa — el pipeline ya
  tiene el punto de sustitución), T5/T6 (W3, UI e informe).