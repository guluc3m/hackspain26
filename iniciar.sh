#!/usr/bin/env bash
# Modo Alberto — arranque de UN paso (T34 + T35).
#
#   ./iniciar.sh
#
# Abre la app de facturas como VENTANA (modo escritorio) y, si tu sistema no
# puede, la abre en el navegador. Sin argumentos, sin terminal que aprender:
# al final verás "Listo". Idempotente: si ya está encendido, solo abre.
#
# Requisitos (se comprueban aquí mismo, con mensaje claro si falta algo):
#   - `uv` en el PATH  → https://docs.astral.sh/uv/
#   - nada más: el resto se descarga/crea solo (la .venv se crea con uv).

set -euo pipefail

PUERTO="${PUERTO:-8000}"
STORE="${STORE:-}"
cd "$(dirname "$0")"

aviso() { echo "ERROR: $*" >&2; exit 1; }

command -v uv >/dev/null 2>&1 || aviso "Falta uv — instálalo con:
  curl -LsSf https://astral.sh/uv/install.sh | sh"
[ -n "$STORE" ] && export ALBERTITOS_STORE="$STORE"
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
	if uv run python -c "import webview" >/dev/null 2>&1; then
		nohup uv run python -m albertitos.desktop --solo-ventana >/dev/null 2>&1 &
	else
		NAVEGADOR "http://localhost:$PUERTO"
	fi
	echo ""
	echo "Listo. Mira la ventana (o tu navegador): http://localhost:$PUERTO"
	exit 0
fi

# ------------------------------------------------ 3 · modo escritorio (ventana)
# pywebview abre la UI en una ventana nativa (WebKit/WebView2/GTK según OS).
# Si el webview del sistema no está disponible, cae al navegador sin drama.
MODO_ESCRITORIO=0
if uv run python -c "import webview" >/dev/null 2>&1; then
	MODO_ESCRITORIO=1
	echo "Arrancando la app… (se abre en una ventana)"
	nohup uv run python -m albertitos.desktop --puerto "$PUERTO" \
		> .sdd/telemetria/ui.log 2>&1 &
	for _ in $(seq 1 60); do
		if VIVA; then break; fi
		sleep 0.5
	done
	if VIVA; then
		echo ""
		echo "Listo. La app está en la ventana que se acaba de abrir."
		echo "(Sigue funcionando aunque cierres esta terminal. Para pararla:"
		echo " cierra la ventana, o usa: cerrar.sh)"
		exit 0
	fi
	echo "El modo ventana no arrancó — paso al navegador."
fi

# ------------------------------------------------ 4 · modo navegador (fallback)
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

NAVEGADOR "http://localhost:$PUERTO"
echo ""
echo "Listo. Mira tu navegador: http://localhost:$PUERTO"
echo "(El sistema sigue funcionando aunque cierres esta terminal."
