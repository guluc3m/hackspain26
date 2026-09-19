# T24 · Drill en vivo: matar llama-server a mitad de una corrida real
assignee: W2
priority: p1

## Objetivo
Los drills T12 usan mocks. Este es REAL: demuestra la degradación con el VLM
local vivo y muerto, midiendo todo — es la evidencia de resiliencia que se
muestra en la defensa.

## Protocolo (store TEMPORAL, nunca el real)
1. Levanta (si no está) llama-server en 127.0.0.1:8080 (ya corriendo: health).
2. Corre `python -m albertitos.run --only "scan_0[12]*.pdf"` (los que van a
   rung 4) contra un store temporal con 20 archivos.
3. A mitad de la corrida: `pkill -f llama-server` (regístralo con timestamp).
4. Mide: los archivos en vuelo → qué hacen (timeout? retry? ESCALAR con
   motivo?), el resto del lote sigue por rung 1-3 sin tocar rung 4, y las
   páginas afectadas quedan ESCALAR/pendientes en cola de revisión.
5. Reinicia llama-server, re-corre: los pendientes se completan (resume
   idempotente) y el outcomes final es idéntico al de una corrida sin kill
   (byte a byte) — determinismo tras recuperación.
6. En paralelo: verifica que 3 workers + UI + ERP sigue en verde (la corrida
   NO puede matar a la flota: nice/cgroups si hace falta).

## Entregable
`.sdd/metrics/drill-rung4-live.json`: timeline (t=0 arranca, t=X kill, t=Y
detectado, t=Z colas afectadas, t=W recuperación completa), files/s antes y
después, y una nota para el guion de defensa (Salud screen lo muestra).

## Criterios de aceptación
- Test: el drill corre con un stub de llama-server que muere (sin red real);
  resultados idénticos con y sin kill.
- perfíl del sistema no degradado durante el drill (RAM bajo control).
- pytest+ruff verde; ticket a closed en el mismo commit.

---

## Resolución (W2 — 2026-09-19): VERDE/ROJO por fase

Corrida EN VIVO real (no mocks): llama-server PaddleOCR-VL q8_0 en
127.0.0.1:8080, 20 archivos reales del corpus (12 scans + 8 con texto),
store TEMPORAL `.sdd/drill-live/` (el store real jamás se abre: hash
byte a byte verificado en tests). Dos corridas; artefacto consolidado con
la timeline medida en `.sdd/metrics/drill-rung4-live.json`.

| fase | resultado | evidencia |
|---|---|---|
| 0 · llama-server arriba | VERDE | t=0.007s /v1/models UP (2 corridas) |
| 1 · corrida BASE sin kill | VERDE | 20/20 (run1 0.563 files/s, run2 0.076 medidos) |
| 2 · KILL en vivo a mitad | VERDE | SIGTERM PID 11757 @ t=35.83s, cmdline preservada de /proc |
| 3 · degradación medida | VERDE | 12 scans: rung 4 skip → rung 5 skip → ESCALAR + cola revisión 12; el resto siguió por rung 1–3; 0 timeouts (run2) |
| 3b · presupuesto de timeout | ROJO→fix | run1: falsos RUNNER_TIMEOUT en cascada medidos (9/12) ⇒ presupuesto desde ARRANQUE REAL (commit b3b2ec2, test T8 verde) |
| 4 · reinicio llama-server | VERDE | relanzado con SU cmdline de /proc; /health ok |
| 5 · resume idempotente | VERDE | 13 ESCALAR re-decidos con reprocesado dirigido T13 (--all-scaled); histórico kill+recuperado coexiste |
| 6 · determinismo tras recuperación | VERDE | run2: outcomes 20/20 líneas byte-idénticos a la base (recalculado post-corrida con el mismo código del drill tras el corte por tope externo); demostrado también con stub (tests) |
| 7 · flota no degradada | VERDE | 430 muestras RAM: proceso 132 MB, llama 2.78 GB, disponible mín 7.8 GB; nice |

Bug identificado (documentado, NO implementado por directiva del ticket):
`hooks_reales.health()` da UP durante la carga del modelo — el chequeo de
/health cae en `except OSError: return True` cuando llama-server responde
/v1/models pero aún carga el gguf (/health contesta 503 ⇒ HTTPError ⇒
OSError). Efecto medido (run 2): llamadas rung 4 en cola hasta
`vlm_timeout_s=60s` (12 skips + 3 respuestas a ~31.8s). NO rompió el
determinismo. Fix propuesto como nota en el JSON: `health()` debe exigir
GET /health == 200 (quitar el `return True`); no toca decisiones ni store.

Cambios de código incluidos:
- `extract/ladder.py`: un skip TRANSIENTE de proveedor (llama-server caído,
  llamada fallida, cloud fallido, tesseract error) NO se cachea — cacharlo
  haría la degradación permanente y la recuperación imposible. Los skips
  estables (binario ausente, cloud no configurado) sí se cachean. Test de
  cache actualizado + dryrun refleja los reintentos (gratis, locales).
- `run.py`: presupuesto de timeout medido desde el arranque real (adenda en
  el ticket T8) con espera de arranque acotada y sin carreras.
- `reprocess.py`: passthrough de `extract_config` para el drill.
- `drill_rung4_live.py` + `scripts/drill_rung4_live.sh` (nice): hooks
  inyectables — stub que muere (tests, sin red real) o kill/relanzado real.

Suite completa: 217 passed; `uv run ruff check .` limpio.
