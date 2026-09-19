== Implementation
- *MongoDB (+ separate SQL)*: at this scale (hundreds of files) two engines
  are two operational surfaces with no benefit; traceability (evidence,
  candidates, snapshots) is relational, and SQLite + ledger covers the
  history with trivial recovery. Dynamic fields fit JSON columns.
- *Backend in Go*: the UI must write overrides and re-trigger the
  deterministic engine (Python); duplicating the engine breaks the
  byte-for-byte determinism guarantee and drifts the type contract.
- *Astro*: aimed at content sites; this panel is a live ops dashboard
  (batch status, review queue, threshold diffs), so a reactive framework fits
  better.
- Ledger con JSONL para estar por casa, ya cuando escale usar algo como MongoDB
- SQLite ya escalará cuando toque escalar (PosgreSQL)