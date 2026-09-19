#!/usr/bin/env bash
# Alberto: abre la app de facturas en una ventana (o navegador si falta).
# Idempotente y sin root: todo va en el .venv local.
set -euo pipefail
cd "$(dirname "$0")"
command -v uv >/dev/null || { echo "Falta uv — instálalo con: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
exec uv run python -m albertitos.desktop "$@"
