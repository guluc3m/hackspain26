# T19 · Preparación de la entrega: staging del repo público + PDF final
assignee: W2
priority: p1

## Objetivo
Dejar la entrega a un comando: `bash scripts/stage_delivery.sh` produce en
`/home/deploy/delivery-repo` un repo git limpio con EXACTAMENTE
`outcomes.jsonl`, `outcomes_lote2.jsonl` (si existe), `albertitos_plan.pdf`.

## Requisitos
- Usa tu propio script T12; actívalo con los datos reales: outcomes.jsonl del
  lote 1 está en la raíz de la solución (500/500 validado). lote2 aún no existe:
  el script debe tolerar su ausencia (stage solo con los que existan, avisando).
- Compila el PDF final con el binario typst ya instalado en ~/.local/bin:
  `cd docs/report && typst compile --font-path fonts albertitos_plan.typ` — con
  los bindings de T15/T18 (auditoría T17, impacto del fix T18 si ya existe).
- Higiene: grep de secretos sobre lo que va al repo de entrega; EXACTAMENTE los
  archivos permitidos (ni .gitattributes, ni README, ni nada).
- El repo de entrega es git init local (no remote): que solo falte
  `git remote add` + push — eso lo hace el usuario.

## Criterios de aceptación
- `stage_delivery.sh` idempotente: dos ejecuciones seguidas = mismo estado.
- Test: con fixtures del lote, el script produce el repo con exactamente N
  archivos y falla limpio ante JSONL inválido.
- PDF compilado presente en /home/deploy/delivery-repo (NO commiteado en la solución).
- pytest+ruff verde; ticket a closed en el mismo commit.

---

## Resolución (W2 — 2026-09-19)

Entrega a un comando, verificada con los datos reales.

- **Script T12 activado con datos reales** (`scripts/stage_delivery.sh`):
  `outcomes.jsonl` real del lote 1 (500/500 validado contra
  `caja-de-alberto/facturas/` con `python -m albertitos.validate`) +
  `albertitos_plan.pdf` compilado. T19 añade la tolerancia pedida:
  `outcomes_lote2.jsonl` es OPCIONAL — si falta, se AVISA y se hace staging
  con los que existan; lote 1 y PDF siguen siendo obligatorios (fallo limpio
  sin copiar nada). La comprobación final es dinámica (2 o 3 entregables).
- **PDF final compilado con typst** (`~/.local/bin/typst compile --font-path
  fonts albertitos_plan.typ`): 13 páginas. Antes se regeneró el binding
  `datos.typ` con `albertitos.report_data` — corrección real: leía un
  formato de ledger que ya no existe (zeros). Ahora `_datos_desde_store`
  lee el store SQLite real (invoices + evidence): 500 facturas, 347/108/45,
  config v3.0-2026-09-19, 498 páginas de extracción, 4,16 archivos/s (del
  estado medido del runner). `escalabilidad_datos.typ` NO se regeneró: el
  committed de T15 ya lleva la evidencia T10/T12 real y regenerarlo hoy
  perdería drills/calibración cuyo .json ya no está en disco (decisión
  documentada). PDF compilado en `/home/deploy/delivery-repo` y NO commiteado
  en la solución (`.gitignore` nuevo para PDFs compilados y outcomes.jsonl).
- **Staging real ejecutado**: `/home/deploy/delivery-repo` = repo git local
  SIN remote (solo falta `git remote add` + push, lo hace el usuario) con
  exactamente 2 entregables ahora; al llegar el lote 2, re-ejecutar el
  script lo eleva a 3. Idempotente medido: segunda ejecución ⇒ mismo estado,
  sigue 1 commit.
- **Higiene**: grep de secretos (apiKey|sk-|FACTURAS2009) sobre lo que se
  copia, validador de contrato sobre cada JSONL, y nada más que los
  entregables en la raíz (ni README ni .gitattributes).
- **Tests** (`tests/test_staging_entrega.py`): el script se ejecuta de
  verdad (bash subprocess contra fixtures) — happy path sin lote2 (2
  entregables + 1 commit + sin remote), con lote2 (3 entregables),
  idempotencia (2 corridas ⇒ 1 commit), JSONL inválido (fallo limpio, nada
  copiado), falta de lote1 (fallo limpio), secreto (fallo limpio) y
  presencia del PDF real compilado en el repo de entrega. Fixtures bajo
  `.sdd/pytest-tmp/` (estado jamás en /tmp).
- Suite completa: 177 passed; `uv run ruff check .` limpio.
