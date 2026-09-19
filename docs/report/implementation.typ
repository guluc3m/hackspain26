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
+ Store PouchDB JS local (LevelDB): única fuente de evidencia, caché,
    eventos y configuración. Documentos dinámicos, sin tablas ni segundo motor.
    - Decisiones inmutables por ejecución y candidatos sin colapsar.
    - Artefactos binarios fragmentados en adjuntos; originales recuperables sin
      depender de copias de trabajo. Estado en disco, nunca en `/tmp`.
    - Modo servidor: replicación bidireccional nativa PouchDB <-> CouchDB remoto,
      sin instalar CouchDB localmente. Configuración local no replicada.
+ Frontend (Vue + Vite, TypeScript, en español) + backend API (FastAPI,
    same Python repo as the pipeline).
    - The API shares the `types.py` contract, the store access layer and the
      deterministic rule engine with the pipeline: one toolchain, one engine.
    - The backend is *not* read-only: the review UI writes human overrides
      (with provenance) and triggers reprocessing; decisions are then
      recomputed deterministically by the same engine.
    - Los artefactos se recuperan desde PouchDB mediante la API.
    - Al arrancar la UI se elige standalone o servidor; Configuración permite
      editar las URLs de sincronización y VLM. El batch sigue no interactivo.

