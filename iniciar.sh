#!/usr/bin/env bash
# Modo Alberto — arranque de UN paso (T34).
#
#   ./iniciar.sh
#
# Levanta tu sistema de facturas y abre el navegador. Sin argumentos, sin
# terminal que aprender: al final verás "Listo. Mira tu navegador: …".
# Idempotente: si ya está encendido, solo abre el navegador (nunca rompe).
#
# Requisitos (se comprueban aquí mismo, con mensaje claro si falta algo):
#   - `uv` en el PATH  → https://docs.astral.sh/uv/
#   - nada más: el resto se descarga/crea solo (la .venv se crea con uv).

set -euo pipefail

PUERTO="${PUERTO:-8000}"
STORE="${STORE:-}"
cd "$(dirname "$0")"

aviso() { echo "ERROR: $*" >&2; exit 1; }

# ------------------------------------------------------------ 0 · requisitos
if ! command -v uv >/dev/null 2>&1; then
	aviso "Falta 'uv' (el instalador de Python que usa este proyecto).
Instálalo con:  curl -LsSf https://astral.sh/uv/install.sh | sh
y vuelve a ejecutar ./iniciar.sh"
fi
if [ ! -f .venv/bin/python ]; then
	echo "Preparando el sistema por primera vez (solo la primera vez)…"
	uv sync --quiet
fi

# ------------------------------------------------- 1 · qué datos usar
if [ -z "$STORE" ]; then
	if [ -e .sdd/lote1/ledger ] || [ -L .sdd/lote1/ledger ]; then
		STORE=".sdd/lote1/ledger"       # tus facturas reales (solo lectura)
	else
		STORE=".sdd/ledger"             # sin datos todavía: verás datos de prueba
	fi
fi
export ALBERTITOS_STORE="$STORE"
mkdir -p .sdd/telemetria

NAVEGADOR() {
	if command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 &
	elif command -v open >/dev/null 2>&1; then open "$1" >/dev/null 2>&1 &
	else echo "Abre este enlace en tu navegador: $1"; fi
}

VIVA() { curl -sf "http://127.0.0.1:$PUERTO/" >/dev/null 2>&1; }

# ------------------------------------------------ 2 · ¿ya está funcionando?
if VIVA; then
	echo "El sistema ya está encendido (no lo vuelvo a arrancar)."
	NAVEGADOR "http://localhost:$PUERTO"
	echo ""
	echo "Listo. Mira tu navegador: http://localhost:$PUERTO"
	exit 0
fi

# ------------------------------------------------ 3 · arrancar en segundo plano
mkdir -p .sdd/telemetria
nohup uv run uvicorn albertitos.ui.app:app --host 127.0.0.1 --port "$PUERTO" \
	> .sdd/telemetria/ui.log 2>&1 &

echo "Arrancando el sistema… (esto tarda unos segundos la primera vez)"
ARRANCADA=0
for _ in $(seq 1 60); do
	if VIVA; then ARRANCADA=1; break; fi
	sleep 0.5
done
if [ "$ARRANCADA" != "1" ]; then
	aviso "No arrancó en 30 s. Mira el log: .sdd/telemetria/ui.log
Y prueba: uv run python -m albertitos.simulacro"
fi

# ------------------------------------------------ 4 · abrir navegador
NAVEGADOR "http://localhost:$PUERTO"
echo ""
echo "Listo. Mira tu navegador: http://localhost:$PUERTO"
echo "(El sistema sigue funcionando aunque cierres esta terminal."
echo " Para pararlo:  pkill -f 'uvicorn albertitos.ui.app')"