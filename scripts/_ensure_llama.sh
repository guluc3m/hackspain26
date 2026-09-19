#!/usr/bin/env bash
# _ensure_llama.sh — source me: deja llama-server (rung 4) listo en 127.0.0.1:8080.
#
# Orden: 1) ya está UP → nada que hacer. 2) instalamos/actualizamos el binario
# y los GGUF de PaddleOCR-VL-1.6 q8_0 en .sdd/llama/ (fuera de git) y lo
# arrancamos. 3) si algo falla (sin red, sin curl) → aviso y seguimos: el
# sistema degrada a rung 3 (tesseract) y el lote NUNCA se detiene.
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

# ---------- binario llama.cpp (CPU, precompilado por plataforma) ----------
if [ ! -x "$LLAMA_DIR/llama-server" ]; then
	echo "Rung 4: descargando llama.cpp ($TAG_LLAMA, CPU, ~16 MB)…"
	curl -fL --retry 2 -# -o "$LLAMA_DIR/llama.tar.gz" \
		"https://github.com/ggml-org/llama.cpp/releases/download/$TAG_LLAMA/$ASSET_LLAMA" \
	&& tar -xzf "$LLAMA_DIR/llama.tar.gz" -C "$LLAMA_DIR" \
	&& mv "$LLAMA_DIR"/llama-b*/* "$LLAMA_DIR/" \
	&& { rmdir "$LLAMA_DIR"/llama-b* 2>/dev/null || true; } \
	&& rm -f "$LLAMA_DIR/llama.tar.gz"
fi

# ---------- modelo (0.5 + 0.6 GB, descarga única) ----------
if [ ! -f "$LLAMA_DIR/$GGUF_MODELO" ]; then
	echo "Rung 4: descargando modelo PaddleOCR-VL-1.6 q8_0 (~1.1 GB, solo la primera vez)…"
	curl -fL -o "$LLAMA_DIR/$GGUF_MODELO" "$REPO_HF/$GGUF_MODELO"
	curl -fL -o "$LLAMA_DIR/$GGUF_MMPROJ" "$REPO_HF/$GGUF_MMPROJ"
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
