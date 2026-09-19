= Implementación

The architecture is implemented in three main parts:
+ Pipeline (Python 3.13 + uv), a long-running worker loop that does the work
    (extraction ladder, parsing, rule evaluation) and writes to the store.
    - Every stage caches on that same key; processing is idempotent and
      resumable. A missing dependency degrades quality (`skipped:<reason>`)
      but never halts the batch.
    - Master data (providers, NIFs, IBANs, rule thresholds, rule list) is
      loaded from YAML/CSV files at startup and snapshotted per run, so a
      reload keeps a record of what was active at decision time.
    - Emits `outcomes.jsonl` / `outcomes_lote2.jsonl` (one result per file,
      `file_id` = exact PDF filename).
+ Store (SQLite + append-only JSONL ledger), our source of truth and historic
    records. One DB file (WAL mode), zero extra services, state on disk and
    never in `/tmp` (tmpfs).
    - Normalized tables for the relational core: invoices, evidence rows,
      fields + candidates (values are never collapsed), rule evaluations,
      config snapshots, human overrides with provenance.
    - Dynamic per-country fields live in JSON columns, so a new
      administration needs no schema migration.
    - The ledger records every state transition append-only, so the history
      survives even a corrupted DB file; recovery is "copy one file".
+ Frontend (Svelte + Vite, TypeScript, in Spanish) + backend API (FastAPI,
    same Python repo as the pipeline).
    - The API shares the `types.py` contract, the store access layer and the
      deterministic rule engine with the pipeline: one toolchain, one engine.
    - The backend is *not* read-only: the review UI writes human overrides
      (with provenance) and triggers reprocessing; decisions are then
      recomputed deterministically by the same engine.
    - Page images rendered by pypdfium2 are served as static files for the
      review queue (candidates side by side).
    - Views: Operaciones, Facturas, Revisión, Reglas, Impacto, Salud.

