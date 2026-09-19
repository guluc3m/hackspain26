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
