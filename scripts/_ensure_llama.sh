#!/usr/bin/env bash
# _ensure_llama.sh — source me: deja llama-server (rung 4) listo en 127.0.0.1:8080.
#
# Orden: 1) ya está UP → nada que hacer. 2) instalamos/actualizamos el binario
# y los GGUF de PaddleOCR-VL-1.6 q8_0 en .sdd/llama/ (fuera de git) y lo
# arrancamos. 3) si algo falla (sin red, sin curl) → aviso y seguimos: el
# sistema degrada a rung 3 (tesseract) y el lote NUNCA se detiene.
#
# NOTA: quien me sourcea (iniciar.sh) corre con `set -euo pipefail`. Todo fallo
# de descarga va dentro de `|| { aviso; }` — jamás aborta el arranque de la UI.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # scripts/ → raíz del repo

PUERTO_LLAMA="${PUERTO_LLAMA:-8080}"
LLAMA_DIR=".sdd/llama"
BASE_URL="http://127.0.0.1:$PUERTO_LLAMA"

VIVA_LLAMA() { curl -sf "$BASE_URL/health" -o /dev/null 2>&1; }

if VIVA_LLAMA; then
	return 0 2>/dev/null || true
fi

TAG_LLAMA="b11048"
OS_LLAMA="$(uname -s)-$(uname -m)"   # Linux-x86_64, Linux-aarch64, Darwin-arm64, Darwin-x86_64
case "$OS_LLAMA" in
	Linux-x86_64)  ASSET_LLAMA="llama-$TAG_LLAMA-bin-ubuntu-x64.tar.gz" ;;
	Linux-aarch64) ASSET_LLAMA="llama-$TAG_LLAMA-bin-ubuntu-arm64.tar.gz" ;;
	Darwin-arm64)  ASSET_LLAMA="llama-$TAG_LLAMA-bin-macos-arm64.tar.gz" ;;
	Darwin-x86_64) ASSET_LLAMA="llama-$TAG_LLAMA-bin-macos-x64.tar.gz" ;;
	*) echo "AVISO: plataforma $OS_LLAMA sin binario precompilado — sigo con tesseract (rung 3)." >&2; return 0 2>/dev/null || true ;;
esac
REPO_HF="https://huggingface.co/Mungert/PaddleOCR-VL-1.6-GGUF/resolve/main"
GGUF_MODELO="PaddleOCR-VL-1.6-q8_0.gguf"

GGUF_MMPROJ="PaddleOCR-VL-1.6-q8_0.mmproj"

mkdir -p "$LLAMA_DIR"   # curl escribe aquí: sin el directorio, error 23 (fue el fallo original)

# ---------- binario llama.cpp (CPU, precompilado por plataforma) ----------
if [ ! -x "$LLAMA_DIR/llama-server" ]; then
	echo "Rung 4: descargando llama.cpp ($TAG_LLAMA, CPU, ~16 MB)…"
	if curl -fL --retry 2 -sS -o "$LLAMA_DIR/llama.tar.gz" \
		"https://github.com/ggml-org/llama.cpp/releases/download/$TAG_LLAMA/$ASSET_LLAMA" \
		&& tar -xzf "$LLAMA_DIR/llama.tar.gz" -C "$LLAMA_DIR" \
		&& mv "$LLAMA_DIR"/llama-b*/* "$LLAMA_DIR/" \
		&& { rmdir "$LLAMA_DIR"/llama-b* 2>/dev/null || true; } \
		&& rm -f "$LLAMA_DIR/llama.tar.gz"
	then
		:
	else
		rm -f "$LLAMA_DIR/llama.tar.gz"
		echo "AVISO: no pude instalar el binario de llama.cpp — sigo con tesseract (rung 3)." >&2
	fi
fi

# ---------- modelo (0.5 + 0.6 GB, descarga única) ----------
# Descarga atómica (.tmp + mv): un GGUF truncado jamás pasará por modelo
# completo en un re-intento (la puerta de idempotencia es `[ -f ]`).
_descarga_gguf() {  # _descarga_gguf <url> <destino>
	local url="$1" destino="$2"
	curl -fL --retry 2 -sS -o "$destino.tmp" "$url" \
		&& mv "$destino.tmp" "$destino" \
		|| { rm -f "$destino.tmp"; echo "AVISO: falló la descarga de $(basename "$destino") — sigo con tesseract (rung 3)." >&2; return 1; }
}

if [ ! -f "$LLAMA_DIR/$GGUF_MODELO" ] || [ ! -f "$LLAMA_DIR/$GGUF_MMPROJ" ]; then
	echo "Rung 4: descargando modelo PaddleOCR-VL-1.6 q8_0 (~1.1 GB, solo la primera vez)…"
	# cada pieza solo si falta: un corte a mitad re-descarga lo pendiente
	[ -f "$LLAMA_DIR/$GGUF_MODELO" ] || _descarga_gguf "$REPO_HF/$GGUF_MODELO" "$LLAMA_DIR/$GGUF_MODELO" || true
	[ -f "$LLAMA_DIR/$GGUF_MMPROJ" ] || _descarga_gguf "$REPO_HF/$GGUF_MMPROJ" "$LLAMA_DIR/$GGUF_MMPROJ" || true
fi

if [ ! -x "$LLAMA_DIR/llama-server" ] || [ ! -f "$LLAMA_DIR/$GGUF_MODELO" ]; then
	echo "AVISO: rung 4 sin configurar (falta binario o modelo) — sigo con tesseract (rung 3)." >&2
	return 0 2>/dev/null || true
fi

# ---------- arranque ----------
echo "Rung 4: arrancando llama-server (CPU, ~30-60 s cargando el modelo)…"
nohup "$LLAMA_DIR/llama-server" \
	-m "$LLAMA_DIR/$GGUF_MODELO" \
	--mmproj "$LLAMA_DIR/$GGUF_MMPROJ" \
	--temp 0 --threads 6 --host 127.0.0.1 --port "$PUERTO_LLAMA" \
	> "$LLAMA_DIR/llama-server.log" 2>&1 &

for _ in $(seq 1 120); do
	VIVA_LLAMA && { echo "Rung 4: UP."; return 0 2>/dev/null || true; }
	sleep 1
done

echo "AVISO: llama-server no quedó listo en 120 s — sigo con tesseract (rung 3)." >&2
