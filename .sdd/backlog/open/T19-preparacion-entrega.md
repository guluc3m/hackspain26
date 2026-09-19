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
