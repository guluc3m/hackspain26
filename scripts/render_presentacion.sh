#!/usr/bin/env bash
# Regenera la presentación Remotion (T32) con los datos ACTUALES de
# .sdd/metrics/ y renderiza headless. nice: no pisar a llama-server.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m albertitos.presentacion
cd presentation
exec nice -n 10 npx remotion render src/index.ts Presentacion out/presentacion.mp4 "$@"
