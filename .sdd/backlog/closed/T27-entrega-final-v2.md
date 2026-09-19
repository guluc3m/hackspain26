# T27 · Entrega final v2: resumen de Alberto y contrato de la entrega
assignee: W1
priority: p0

## Contexto
W3 integró T26: `resumen_alberto.pdf` (resumen ejecutivo para Alberto). Este
ticket decide si entra en el repo de entrega y re-verifica la entrega final.

## Criterios (definidos por el supervisor)
- Analizar el contrato de la organización (AGENTS.md §1 / hackathon): la raíz
  del repo público lleva EXACTAMENTE los entregables del contrato
  (`outcomes.jsonl`, `outcomes_lote2.jsonl` cuando exista,
  `albertitos_plan.pdf`).
- Si el resumen rompe ese EXACTAMENTE ⇒ NO entra en el repo de entrega:
  queda como artefacto de la solución y punto de demo (con comando para
  regenerarlo).
- Re-verificar la entrega: exactamente los archivos permitidos en la raíz del
  delivery-repo, validador 500/500 verde, sin secretos.
- Anotar el comando de push para el usuario.
- pytest+ruff verde; ticket a closed en el mismo commit. Sin push.

## Decisión esperada (análisis, no gusto)
El contrato dice EXACTAMENTE los 3: añadir un 4º archivo (por bueno que sea)
es riesgo de invalidación binaria. El resumen NO entra al delivery-repo.

## CIERRE (W1, 2026-09-19) — decisión + verificación
**DECISIÓN: el resumen de Alberto NO entra en el repo de entrega.**
Análisis (contrato de la organización, AGENTS.md §1 + hackathon): la raíz del
repo público lleva EXACTAMENTE los entregables del contrato — `outcomes.jsonl`,
`outcomes_lote2.jsonl` (cuando exista) y `albertitos_plan.pdf`. Añadir
`resumen_alberto.pdf` rompe el EXACTAMENTE y es riesgo de invalidación
binaria. El resumen queda como ARTEFACTO DE LA SOLUCIÓN y punto de demo:
- `/home/deploy/fleet/w1/resumen_alberto.pdf` (+ .html/.typ), 2 páginas,
  generado con `uv run python -m albertitos.resumen --store-root .sdd`
  (idempotente; PDF vía typst).
- Demo: abrir el HTML/PDF — «¿qué pago hoy y por qué?» con los 433 PAGAR.

**Re-verificación de la entrega (todo en verde)**:
- re-staging ejecutado (idempotente): /home/deploy/delivery-repo raíz con
  EXACTAMENTE `outcomes.jsonl` + `albertitos_plan.pdf` (lote 2 pendiente);
  test nuevo comprueba que el staging IGNORA artefactos extra de la raíz.
- validador de contrato sobre el delivery-repo: 500/500 OK.
- grep de secretos (apiKey|sk-|FACTURAS2009) sobre lo copiado: vacío.
- pytest 230/230, ruff limpio.

**COMANDO EXACTO para el usuario (push + teamId)** — igual que T25:
1. (opcional) teamId: editar `docs/report/albertitos_plan.typ:13`
   `teamId: "TU_TEAM_ID",` y recompilar:
   `cd docs/report && ~/.local/bin/typst compile --font-path fonts albertitos_plan.typ && cp albertitos_plan.pdf ../../`
2. Re-staging: `cd /home/deploy/fleet/w1 && FACTURAS_LOTE1=/home/deploy/hackspain26/caja-de-alberto/facturas bash scripts/stage_delivery.sh`
3. Push del repo de entrega (crea el repo público antes):
   `git -C /home/deploy/delivery-repo remote add origin git@github.com:<usuario>/<repo-publico>.git`
   `git -C /home/deploy/delivery-repo push -u origin HEAD:main`
4. El resumen de Alberto para la demo está FUERA del repo de entrega (regenerable:
   `uv run python -m albertitos.resumen --store-root .sdd`).
