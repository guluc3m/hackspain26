#!/usr/bin/env bash
# Drill EN VIVO (T24): matar llama-server a mitad de una corrida real.
# Store TEMPORAL en .sdd/drill-live/ (el store real nunca se toca).
# nice: el drill no puede degradar a la flota (llama-server ya corre nice 5).
# Al terminar, el servidor queda UP (el drill lo relanza con su cmdline).
set -euo pipefail
cd "$(dirname "$0")/.."
exec nice -n 10 uv run python -m albertitos.drill_rung4_live "$@"
