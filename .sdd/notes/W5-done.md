
## Sesión 14 — T40 · 3º EVALUADOR-IMPLEMENTADOR (W5), dominio tests/robustez

### Evaluación de la cola abierta
- T38F1 (NIF_IN_MANAGER colapsa 1er candidato): supervisor/ADR, cambia
  resultados — NO tocado (regla dura T38.2). W1 ya dejó xfail en worker/w3.
- T38F2 (labels de total): parser, cambia resultados — dominio W2/W1, NO tocado.
- T38F3/F4/F5: ya implementados por W1 en worker/w3 (commits f69231c, 29df989).
- T38F6 (overrides huérfanos), T38F7 (master lote2), T38-ID1 (script lote2):
  asignados W2, pipeline (~60 líneas c/u) — fuera de mi dominio, NO tocados.
- T40F4 (nuevo, ABIERTO): 5 tests dependen de estado runtime gitignored
  (.sdd/lote1) ⇒ rojos en worktree fresco; repro documentado, decisión de
  provisioning al supervisor (ficheros de W3/W4).

### Implementado (3 commits, 1 ticket por commit, ticket a closed)
1. **T40F1** (b008f2f): higiene de secretos como test PERMANENTE
   (tests/test_higiene_secretos.py) — escanea lo que viaja en un commit,
   patrones de señal alta (sk- larga, apiKey con valor, AKIA/ghp_/github_pat_/
   xox*, clave privada), self-test con payload simulado en runtime.
   AGENTS.md §13 deja de ser ritual manual.
2. **T40F2**: 14 puertos FIJOS eliminados (8231-8237 drill-live, 8241-8247
   hardening) — stubs con bind :0 y puerto real leído tras el bind
   (restart revincula al mismo puerto, requisito del drill); tmp_path por
   test en vez de .sdd/pytest-tmp compartido. El drill ya no es sensible a
   procesos vecinos ni a corridas paralelas de otros workers.
3. **T40F3 (p0)**: pypdfium2 NO es thread-safe — run.py extrae con 2 workers
   cuando el rung 4 cae (la degradación del drill) y dos hilos entraban a la
   vez al C de pdfium ⇒ SIGSEGV del proceso entero (repro con stack; el drill
   fallaba unas corridas sí y otras no). Fix: _PDFIUM_LOCK alrededor de toda
   entrada a pdfium en ladder.py (raster serializado; rungs 3-5 en paralelo).
   Regresión: test_concurrencia_extract.py (4 hilos × 3 rondas == serial).
   Validador 500/500 OK tras el cambio en src/.
- Submódulo caja-de-alberto inicializado (pin 18d43b3, solo lectura) — el
  drill lee el maestro del corpus y en este worktree no estaba.
- Al cierre: validador 500/500, pytest 285 passed (5 rojos = T40F4,
  preexistentes de entorno), ruff limpio, sin secretos.
