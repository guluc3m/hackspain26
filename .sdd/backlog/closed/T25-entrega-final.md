# T25 · Entrega final: PDF definitivo + repo de entrega verificado
assignee: W1
priority: p0

## Objetivo
Cerrar la entrega: PDF con los números post-fix (T22) + staging final del repo
público + verificación completa. Idempotente: re-ejecutable cuando lote 2 aterrice.

## Pasos
1. Regenera `escalabilidad_datos.typ` con las métricas post-fix (tu T22
   follow-up ya lo dejó listo — verifica que el binding resultadosLote1 usa
   433/22/45 y exactitudLote1 medido).
2. Compila `docs/report` con typst: `typst compile --font-path fonts
   albertitos_plan.typ` (binario en ~/.local/bin). Verifica que el PDF tiene
   arquitectura + ADR-06 + todos los números citados.
3. Ejecuta `scripts/stage_delivery.sh` (T12/T19) con el outcomes.jsonl POST-fix
   (raíz de la solución): produce /home/deploy/delivery-repo con EXACTAMENTE
   outcomes.jsonl + albertitos_plan.pdf (outcomes_lote2.jsonl aún no existe —
   el script debe tolerarlo y avisar).
4. Verificación final (todo en verde, listado en el ticket):
   - `python -m albertitos.validate` sobre el JSONL del repo de entrega.
   - EXACTAMENTE los archivos permitidos en la raíz (ni README ni .gitignore).
   - grep de secretos sobre lo copiado: vacío.
   - pytest+ruff de la solución en verde.
5. NO hagas push del repo de entrega (lo hace el usuario). Deja escrito en el
   ticket el comando exacto que el usuario debe correr para push + teamId.

## Criterios de aceptación
- /home/deploy/delivery-repo: git repo limpio, raíz con los archivos de
  entrega, validator en verde, sin secretos.
- PDF final compilado con los números post-fix.
- pytest+ruff verde; ticket a closed en el mismo commit.

## CIERRE (W1, 2026-09-19) — todo ejecutado y verificado
1. escalabilidad_datos.typ: verificado — resultadosLote1 = "433 PAGAR / 22
   NO_PAGAR / 45 ESCALAR (500 archivos)" y exactitudLote1 = "86.6 % PAGAR
   automático", ambos etiqueta "medido" (cableado a lote1.json en T22).
2. PDF compilado con ~/.local/bin/typst (typst compile --font-path fonts
   albertitos_plan.typ; solo warnings de deprecación de la plantilla, sin
   errores): 13 páginas, verificado por extracción de texto — contiene
   arquitectura + ADR-06 + 433/22/45 + 86.6 % + 471/500 + provenance.
   Copiado a la raíz de la solución (albertitos_plan.pdf, 121 KB).
3. scripts/stage_delivery.sh ejecutado con el outcomes POST-fix: AVISO
   esperado de outcomes_lote2.jsonl pendiente, validador 500/500 OK,
   staging → /home/deploy/delivery-repo.
4. Verificación final:
   - validate sobre /home/deploy/delivery-repo/outcomes.jsonl: 500/500 OK
   - raíz EXACTAMENTE con outcomes.jsonl + albertitos_plan.pdf (+ .git)
   - grep de secretos (apiKey|sk-|FACTURAS2009) sobre lo copiado: vacío
   - outcomes byte-idéntico al POST-fix; PDF byte-idéntico al de la solución
   - pytest 220/220, ruff limpio.
5. COMANDO EXACTO para el usuario (push + teamId):
   a) Editar `docs/report/albertitos_plan.typ` línea 13: `teamId: "TU_TEAM_ID",`
      (HackSpain; si se prefiere sin chip, dejar `none`).
      Recompilar: `cd docs/report && ~/.local/bin/typst compile --font-path fonts albertitos_plan.typ && cp albertitos_plan.pdf ../../`
   - Re-staging: `cd /home/deploy/fleet/w1 && FACTURAS_LOTE1=/home/deploy/hackspain26/caja-de-alberto/facturas bash scripts/stage_delivery.sh`
   - Push (crea el repo público en GitHub primero):
       git -C /home/deploy/delivery-repo remote add origin git@github.com:<usuario>/<repo-publico>.git
       git -C /home/deploy/delivery-repo push -u origin HEAD:main
   - Idempotente: cuando llegue el lote 2, generar outcomes_lote2.jsonl y
     re-ejecutar el staging (el script lo tolera y deja la raíz exacta).
