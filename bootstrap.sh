#!/usr/bin/env bash
# Instala todas las dependencias de filemaid: Python (uv), PouchDB (npm) y la UI (pnpm).
#
# Delega en el lanzador (`python start.py install`), que es la única fuente de
# verdad del entorno: sincroniza uv sin borrar extras ajenos (`--inexact`),
# instala las deps Node de PouchDB y construye la UI solo si falta o está
# desactualizada.
set -euo pipefail
cd "$(dirname "$0")"

DESKTOP=0
for arg in "$@"; do
  case "$arg" in
    --desktop) DESKTOP=1 ;;
    *) printf 'uso: %s [--desktop]\n' "$0" >&2; exit 2 ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  printf 'error: falta python3 en PATH (start.py solo usa la stdlib)\n' >&2
  exit 1
fi

if [ "$DESKTOP" -eq 1 ]; then
  exec python3 start.py install --desktop
fi
exec python3 start.py install
