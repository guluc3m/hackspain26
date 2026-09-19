#!/usr/bin/env bash
# Instala todas las dependencias de filemaid: Python (uv), PouchDB (npm) y la UI (pnpm).
set -euo pipefail
cd "$(dirname "$0")"

DESKTOP=0
for arg in "$@"; do
  case "$arg" in
    --desktop) DESKTOP=1 ;;
    *) printf 'uso: %s [--desktop]\n' "$0" >&2; exit 2 ;;
  esac
done

need() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'error: falta %s en PATH\n' "$1" >&2
    exit 1
  }
}

need uv
need node
need npm

node_major="$(node --version | sed 's/^v//' | cut -d. -f1)"
if [ "$node_major" -lt 20 ]; then
  printf 'error: Node >= 20 requerido, encontrado %s (instálalo en espacio de usuario, p. ej. con nvm)\n' "$(node --version)" >&2
  exit 1
fi
printf 'ok: node %s, npm %s, uv %s\n' "$(node --version)" "$(npm --version)" "$(uv --version)"

printf '\n==> Python (uv sync)\n'
if [ "$DESKTOP" -eq 1 ]; then
  uv sync --extra desktop
else
  uv sync
fi

printf '\n==> Motor PouchDB (npm ci)\n'
uv run -- npm ci --prefix src/filemaid/store/pouchdb

printf '\n==> UI (pnpm install + build)\n'
uv run -- npx --yes pnpm --dir frontend install
uv run -- npx --yes pnpm --dir frontend build

printf '\n==> Verificación del puente PouchDB\n'
SMOKE="$HOME/.cache/filemaid-bootstrap-check"
rm -rf "$SMOKE"
uv run python - "$SMOKE" <<'PY'
import sys
from pathlib import Path

from filemaid.store.pouch import PouchStore

store = PouchStore(Path(sys.argv[1]))
store.local_put("bootstrap", {"ok": True})
assert store.local_get("bootstrap") == {"ok": True}
print("puente PouchDB OK")
PY
rm -rf "$SMOKE"

printf '\nInstalación completa. Arranca con: ./run.sh\n'
