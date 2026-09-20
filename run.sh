#!/usr/bin/env bash
# Arranca la aplicación: ./run.sh [app|vlm|desktop]
#
# Delega en el lanzador (`python start.py`), que es la única fuente de verdad
# del entorno: sincroniza uv sin borrar extras ajenos, instala las deps Node de
# PouchDB y construye la UI solo si falta o está desactualizada.
#
# Cerrar la app termina el proceso: no se relanza nada.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'error: falta python3 en PATH (start.py solo usa la stdlib)\n' >&2
  exit 1
fi

command="${1:-app}"
case "$command" in
  app)
    port="${FILEMAID_PORT:-8000}"
    printf 'filemaid en http://127.0.0.1:%s\n' "$port"
    exec python3 start.py client --headless --port "$port"
    ;;
  vlm)
    host="${FILEMAID_VLM_HOST:-127.0.0.1}"
    port="${FILEMAID_VLM_PORT:-8001}"
    printf 'servidor VLM en http://%s:%s\n' "$host" "$port"
    exec python3 start.py server --host "$host" --port "$port"
    ;;
  desktop)
    exec python3 start.py client
    ;;
  *)
    printf 'uso: %s [app|vlm|desktop]\n' "$0" >&2
    exit 2
    ;;
esac
