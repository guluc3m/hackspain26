# _ensure_uv.sh — source me: instala uv si falta (usuario, sin root).
# Uso:  . "$(dirname "${BASH_SOURCE[0]}")/_ensure_uv.sh"
if ! command -v uv >/dev/null 2>&1; then
	echo "Falta uv — instalándolo (usuario, sin root; solo hace falta curl)…"
	curl -LsSf https://astral.sh/uv/install.sh | sh
	export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || {
	echo "ERROR: uv no quedó en el PATH — abre otra terminal y reintenta" >&2
	exit 1
}
