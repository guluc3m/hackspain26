#!/usr/bin/env bash
# Alberto: abre la app de facturas en una ventana (o navegador si falta).
# Idempotente y sin root: todo va en el .venv local.
set -euo pipefail
cd "$(dirname "$0")"
. "$(dirname "$0")/scripts/_ensure_uv.sh"
exec uv run python -m albertitos.desktop "$@"
