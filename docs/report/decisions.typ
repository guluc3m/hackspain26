== Implementation
- *Dos motores de persistencia*: descartados. PouchDB JS local conserva
  evidencia, candidatos, snapshots, caché y eventos como documentos dinámicos.
  El modo servidor replica con una base remota CouchDB sin requerir CouchDB local.
- *Backend in Go*: the UI must write overrides and re-trigger the
  deterministic engine (Python); duplicating the engine breaks the
  byte-for-byte determinism guarantee and drifts the type contract.
- *Astro*: aimed at content sites; this panel is a live ops dashboard
  (batch status, review queue, threshold diffs), so a reactive framework fits
  better.
- *Ledger externo*: descartado; los eventos append-only viven en PouchDB.
- *Modelo VLM en cada cliente*: opcional en standalone; en modo servidor el
  escalador centraliza el endpoint configurado, sin cambiar reglas de decisión.