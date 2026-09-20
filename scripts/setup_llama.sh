#!/usr/bin/env sh
# Setup llama-server for filemaid (extraction rung 4).
#
# Installs llama.cpp via the official installer (https://llama.app) and
# downloads the PaddleOCR-VL 1.6 full-Q8 model + mmproj (D-002) into a
# project-local dir. Everything lives under $HOME, no root, never in /tmp.
#
# Model choice (docs/decisiones/DECISIONS.md D-002): Mungert full-Q8 files
# (text q8_0 + vision mmproj q8_0). The official PaddlePaddle repo ships
# bf16/f16, not Q8; Q8 is the safe quality floor for this 0.9B OCR model.
#
# Platforms: Linux (x86_64/aarch64), macOS (Apple Silicon), FreeBSD — via
# llama.app's installer, which auto-picks CUDA/ROCm/Vulkan/Metal/CPU.
# Windows: use scripts/setup_llama.ps1 instead (official portable release or
# winget ggml.llamacpp, both user-space, no admin). This script does not
# handle Windows.
#
# Usage: uv run scripts/setup_llama.sh
# Env overrides:
#   LLAMA_MODEL_REPO   HF repo (default Mungert/PaddleOCR-VL-1.6-GGUF)
#   FILEMAID_MODELS    target dir (default <repo>/models/llama, git-ignored)

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_REPO="${LLAMA_MODEL_REPO:-Mungert/PaddleOCR-VL-1.6-GGUF}"
MODELS_DIR="${FILEMAID_MODELS:-$REPO_ROOT/models/llama}"
BASE_URL="https://huggingface.co/$MODEL_REPO/resolve/main"

log() { printf '%s\n' "$*" >&2; }

# sha256 helper: GNU coreutils, then BSD/macOS shasum.
sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

# 1. llama.cpp binary (installs to ~/.local/bin/llama, ~560 MB, CUDA when present)
if command -v llama >/dev/null 2>&1 && llama version >/dev/null 2>&1; then
    log "[llama] already installed: $(llama version 2>&1 | head -1)"
else
    log "[llama] installing via https://llama.app/install.sh ..."
    curl -LsSf https://llama.app/install.sh | sh
fi

# 2. Model weights (D-002 full Q8, ~1.10 GB total) with resume + sha256 verify.
mkdir -p "$MODELS_DIR"
download() {
    name="$1"; expected_size="$2"; expected_sha="$3"
    dest="$MODELS_DIR/$name"
    if [ -s "$dest" ] && [ "$(wc -c < "$dest")" = "$expected_size" ] \
        && [ "$(sha256_of "$dest")" = "$expected_sha" ]; then
        log "[model] $name present and verified, skipping"
        return 0
    fi
    log "[model] downloading $name ..."
    curl -fL --retry 3 -C - -o "$dest.part" "$BASE_URL/$name"
    actual_size="$(wc -c < "$dest.part")"
    if [ "$actual_size" != "$expected_size" ]; then
        rm -f "$dest.part"
        log "[model] size mismatch for $name ($actual_size != $expected_size); aborting"
        exit 1
    fi
    actual_sha="$(sha256_of "$dest.part")"
    if [ "$actual_sha" != "$expected_sha" ]; then
        rm -f "$dest.part"
        log "[model] sha256 mismatch for $name; aborting"
        exit 1
    fi
    mv "$dest.part" "$dest"
}

download "PaddleOCR-VL-1.6-q8_0.gguf" 498316064 \
    "58ff75f8ca2ad8bc4308324d0df570ef77832479b2a80091134fc33e11955a3a"
download "PaddleOCR-VL-1.6-q8_0.mmproj" 597566368 \
    "036d06ea82e9133696c2f93bd9dd2e1e5009520811e5fb3092aab2d0e5696375"

log "[llama] setup complete"
log "[llama] binary : $(command -v llama)"
log "[llama] gguf   : $MODELS_DIR/PaddleOCR-VL-1.6-q8_0.gguf"
log "[llama] mmproj : $MODELS_DIR/PaddleOCR-VL-1.6-q8_0.mmproj"
log "[llama] start  : uv run python -m filemaid.llama_manager start   (or via API /health)"
