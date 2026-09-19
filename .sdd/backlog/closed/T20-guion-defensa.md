# T20 · Guion de defensa + checklist de demo
assignee: W3
priority: p2

## Objetivo
`docs/report/DEFENSA.md` — el guion de los 10 minutos (hackathon.maisa.ai):
1. Demo y contexto (2 min): qué le ahorra a Alberto; UI en vivo con el lote
   real (Operaciones → Facturas → una factura PAGAR con su traza → Revisión
   con un escalado real → Reglas con el what-if).
2. Arquitectura y ADRs (2 min): la escalera por página con los números medidos
   (471/500 texto usable, 29 raster, rung 4 serializado 31 s/página), 5 ADRs
   (leer del PDF, no recitar).
3. Trazabilidad, escala y coste (4 min): seguir UNA decisión real end-to-end
   (file_id → ledger → evidencia por rung → reglas con provenance → resultado);
   files/s medido, fórmula de coste explícita (medido vs estimado), límites y
   cómo se añaden emails/imágenes/Excel (T18/T13: reglas y datos, sin motor).
4. Resiliencia (2 min): drills T12 (4/4 PASS: proveedor caído→ESCALAR, 429→
   backoff, crash→reanudación sin duplicados, ledger corrupto→tolerado);
   mostrado en la pantalla Salud.

## Reglas
- Cada número citado en el guion debe existir en .sdd/metrics/ con fuente.
- El guion NO inventa: si un dato falta, marca PENDIENTE.
- Incluye checklist operativo: comandos para levantar la demo (uvicorn, el
  store real, llama-server si aplica) y qué mostrar si algo falla en vivo
  (plan B: capturas del store real).

## Criterios de aceptación
- DEFENSA.md en docs/report/ con las 4 secciones y el checklist.
- Cada cifra citada tiene su fuente en un comentario al pie.
- pytest+ruff verde; ticket a closed en el mismo commit.

## Cerrado — decisiones tomadas (W3)

- **`docs/report/DEFENSA.md`** con las 4 secciones del guion (demo 2' ·
  arquitectura/ADRs 2' · trazabilidad/escala/coste 4' · resiliencia 2') +
  checklist operativo + plan B.
- **Cero cifras de memoria**: cada número viene de `.sdd/metrics/` con nota
  al pie por fuente — corpus-dryrun.json (T10: 471/29/0, latencias),
  lote1.json (T14: 500/0 fallos, 347/108/45, 4,162 files/s, rung 4 media
  15,8 s / máx 33,7 s medido — la cifra «31 s/página» del ticket se sustituye
  por la medición real del store), calibracion-rung3.json (extract-v2),
  drills.json (4/4 PASS), outcomes-lote1.jsonl, auditoria-trampas.md (T17),
  triage-revision.md (desglose de los 45 escalados). Pendientes declarados
  explícitamente (exactitud vs referencia, reprocesado post-fix).
- **Checklist operativo**: comandos exactos (symlink lote1, uvicorn con
  ALBERTITOS_STORE, typst compile, drills, validador del entregable),
  factura marcada para la traza end-to-end antes de la demo.
- **Plan B**: capturas del store real, UI sin store externo → datos de
  prueba MARCADOS como tales (nunca camuflados), PROHIBIDO improvisar cifras.
- **Test** (`tests/test_defensa.py`): 4 secciones + checklist + Plan B,
  TODAS las rutas `.sdd/...` citadas existen en disco, y los números
  estrella se verifican contra los JSON medidos (471/29/0, 500/0 fallos,
  347/108/45, 4.162, 33 725 ms, drills 4/4, 500 outcomes).
- Suite: 187 passed, ruff limpio, sin secretos.
