#!/usr/bin/env sh
# Setup llama-server for albertitos (extraction rung 4).
#
# Installs llama.cpp via the official installer (https://llama.app) and
# downloads the PaddleOCR-VL 1.6 Q8 model + mmproj into a project-local dir.
# Everything lives under $HOME, no root, never in /tmp.
#
# Platforms: Linux (x86_64/aarch64), macOS (Apple Silicon), FreeBSD — via
# llama.app's installer, which auto-picks CUDA/ROCm/Vulkan/Metal/CPU.
# Windows: run the installer manually (see below), then re-run this script —
# it will skip the binary step and only fetch the weights:
#   curl.exe -LsSf https://llama.app/install.sh | sh   # needs zstd in PATH
#   (or: winget install llama.cpp)
#
# Usage: uv run scripts/setup_llama.sh
# Env overrides:
#   LLAMA_MODEL_REPO   HF repo (default PaddlePaddle/PaddleOCR-VL-1.6-GGUF)
#   ALBERTITOS_MODELS  target dir (default <repo>/models/llama, git-ignored)

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_REPO="${LLAMA_MODEL_REPO:-PaddlePaddle/PaddleOCR-VL-1.6-GGUF}"
MODELS_DIR="${ALBERTITOS_MODELS:-$REPO_ROOT/models/llama}"
GGUF="$MODELS_DIR/PaddleOCR-VL-1.6-GGUF.gguf"
MMPROJ="$MODELS_DIR/PaddleOCR-VL-1.6-GGUF-mmproj.gguf"
BASE_URL="https://huggingface.co/$MODEL_REPO/resolve/main"

log() { printf '%s\n' "$*" >&2; }

# 1. llama.cpp binary (installs to ~/.local/bin/llama, ~560 MB, CUDA when present)
if command -v llama >/dev/null 2>&1 && llama version >/dev/null 2>&1; then
    log "[llama] already installed: $(llama version 2>&1 | head -1)"
else
    log "[llama] installing via https://llama.app/install.sh ..."
    curl -LsSf https://llama.app/install.sh | sh
fi

# 2. Model weights (~1 GB total) with resume; sha256 via HF's .no_exist-less
#    checksum headers is not exposed, so size-check instead of blind re-download.
mkdir -p "$MODELS_DIR"
for f in "$GGUF" "$MMPROJ"; do
    name="$(basename "$f")"
    if [ -s "$f" ]; then
        log "[model] $name present ($(du -h "$f" | cut -f1)), skipping"
        continue
    fi
    expected="$(curl -sSI -L "$BASE_URL/$name" | tr -d '\r' | awk 'tolower($1)=="content-length:" {print $2}' | tail -1)"
    log "[model] downloading $name ..."
    curl -fL --retry 3 -C - -o "$f.part" "$BASE_URL/$name"
    if [ -n "$expected" ] && [ "$(wc -c < "$f.part")" != "$expected" ]; then
        rm -f "$f.part"
        log "[model] size mismatch for $name; aborting"
        exit 1
    fi
    mv "$f.part" "$f"
done

# 3. Ensure the app config points at the default port
log "[llama] setup complete"
log "[llama] binary : $(command -v llama)"
log "[llama] gguf   : $GGUF"
log "[llama] mmproj : $MMPROJ"
log "[llama] start  : uv run python -m albertitos.llama_manager start   (or via API /health)"
