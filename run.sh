#!/usr/bin/env bash
# Arranca la aplicación: ./run.sh [app|vlm|desktop]
set -euo pipefail
cd "$(dirname "$0")"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'error: falta %s en PATH\n' "$1" >&2
    exit 1
  }
}

need uv
need node

if [ ! -d src/filemaid/store/pouchdb/node_modules ]; then
  printf 'error: PouchDB no está instalado; ejecuta ./bootstrap.sh primero\n' >&2
  exit 1
fi

command="${1:-app}"
case "$command" in
  app)
    if [ ! -f frontend/dist/index.html ]; then
      printf 'aviso: frontend/dist no existe; solo se servirá la API (ejecuta ./bootstrap.sh para construir la UI)\n' >&2
    fi
    port="${FILEMAID_PORT:-8000}"
    printf 'filemaid en http://127.0.0.1:%s\n' "$port"
    exec uv run filemaid serve
    ;;
  vlm)
    host="${FILEMAID_VLM_HOST:-127.0.0.1}"
    port="${FILEMAID_VLM_PORT:-8001}"
    printf 'servidor VLM en http://%s:%s\n' "$host" "$port"
    exec uv run filemaid server --host "$host" --port "$port"
    ;;
  desktop)
    exec uv run filemaid-desktop
    ;;
  *)
    printf 'uso: %s [app|vlm|desktop]\n' "$0" >&2
    exit 2
    ;;
esac
