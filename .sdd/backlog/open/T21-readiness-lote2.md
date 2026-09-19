# T21 · Readiness del lote 2: simulación de extremo a extremo
assignee: W2
priority: p1

## Objetivo
Que el sábado a las 18:00 Madrid sea un cambio de DATOS, no de código. Simula
hoy el flujo completo del lote 2 con fixtures y deja el camino listo:

1. **Ingesta de un lote externo**: `python -m albertitos.run --only 'lote2/*'`
   (o un --facturas-dir alternativo) debe ingerir 40 PDFs de un directorio
   distinto con file_id = basename exacto, sin tocar el lote 1 (ledger/run
   separados).
2. **Regla v4 activada**: usa tu regla_v4.yaml paramétrica (T13); activa la
   regla nueva REGLA_V4 en un fixture de 10 facturas y verifica el diff de
   impacto (mecanismo T13): qué decisiones cambian y cuáles no.
3. **Cambio de dato del maestro**: aplica un parche (p.ej. cambia el NIF o el
   importe de un proveedor) y verifica el reprocesado dirigido: sólo los que
   cruzan con ese dato cambian de resultado; el histórico coexiste.
4. **Emisión**: el flujo debe poder emitir outcomes_lote2.jsonl (40 líneas,
   validador en verde) SIN tocar outcomes.jsonl del lote 1.

## Entregable
`python -m albertitos.lote2 --dry-run` (o el comando equivalente documentado en
scripts/) que ejecuta la simulación y deja en .sdd/metrics/lote2-sim.json el
resultado: nº ingeridos, qué cambiaría con v4, diff reprocesado, validador.

## Criterios de aceptación
- Test: la simulación completa corre sin red y es determinista.
- Test: outcomes.jsonl del lote 1 queda byte-idéntico tras la simulación.
- pytest+ruff verde; ticket a closed en el mismo commit.
