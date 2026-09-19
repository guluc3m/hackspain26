#!/usr/bin/env bash
# Readiness del lote 2 (T21): simulación de extremo a extremo, sin red.
#
# Ejercita HOY el flujo del sábado con fixtures:
#   1. ingesta de un lote externo (store sandbox + run_id separados),
#   2. regla v4 activada como DATOS (yaml, cero código) + diff de impacto,
#   3. cambio de dato del maestro (parche en memoria) + reprocesado dirigido,
#   4. emisión de outcomes_lote2.jsonl validada (lote 1 intacto).
#
# Resultado determinista en .sdd/metrics/lote2-sim.json.
#
# El sábado, con el lote 2 real (40 PDFs):
#   uv run python -m albertitos.run --facturas <dir-lote2> \
#       --outcomes outcomes_lote2.jsonl \
#       --rules src/albertitos/rules/regla_v4.yaml --run-id lote2 \
#       --emit-scope lote
#   bash scripts/stage_delivery.sh   # re-staging con lote2
set -euo pipefail
cd "$(dirname "$0")/.."
. "$(dirname "$0")/_ensure_uv.sh"
exec uv run python -m albertitos.lote2 --dry-run "$@"
