# T14 · Corrida real del lote 1 → outcomes.jsonl (los 500)
assignee: W1
priority: p0

## Objetivo
Ejecutar el pipeline COMPLETO (runner T8 + motor T3 + calibración T10) sobre los
500 PDFs reales y emitir `/home/deploy/hackspain26/outcomes.jsonl` con los
resultados reales. Esto es el entregable 1: exactitud > velocidad.

## Cómo
1. `python -m albertitos.run` con los umbrales calibrados (`.sdd/metrics/calibracion.md`),
   regla v3, rung 4 (llama-server ya corriendo en 127.0.0.1:8080, health-check)
   y rung 5 (deepseek-v4.1-flash — PROHIBIDO Qwen3.8, AGENTS.md §13).
   Credenciales cloud por variables de entorno: el supervisor las inyecta; NUNCA
   las escribas en el repo.
2. **Máquina en carga**: hay 2 workers más y el ERP compilando — rung 4 serializado
   (ya lo hace T8); no subas la concurrencia por encima de lo que T8 ya limita.
3. Al terminar: `python -m albertitos.validate outcomes.jsonl` en verde (500
   file_id exactos, resultados válidos) y `python -m albertitos.drills` si ya
   existe T12 integrado.
4. Revisa la cola de revisión generada (`.sdd/review-queue/`): cuenta y lista los
   ESCALAR con su motivo dominante — NO decidas tú sus resultados: el humano
   decide; tú documentas y encolas.
5. Números para el informe: files/s medidos del lote completo, latencia total,
   distribución de resultados, nº rung 4/5 invocados, coste estimado de llamadas
   cloud (T9 los recoge).

## Reglas duras
- outcomes.jsonl NO se commitea en la solución si contiene resultados finales del
  lote... SÍ se commitea (es parte de la solución como artefacto); el repo de
  ENTREGA lo prepara el supervisor con el script T12.
- Re-run idéntico: la corrida debe ser reproducible (cache + ledger); si no lo
  es, para y reporta por qué antes de emitir.

## Criterios de aceptación
- outcomes.jsonl: 500 líneas, validador en verde, sin duplicados, resultados ∈
  {PAGAR, NO_PAGAR, ESCALAR}.
- `.sdd/metrics/lote1.json` con las métricas del punto 5.
- Tests del runner siguen en verde; ticket a closed en el mismo commit.
