# Setup llama.cpp + PaddleOCR-VL para Windows (PowerShell).
# Equivalente a scripts/setup_llama.sh: binario via instalador oficial de
# llama.app (o winget), pesos en <repo>/models/llama. Sin admin, sin /tmp.
#
# Uso:  powershell -File scripts/setup_llama.ps1
# Env:  LLAMA_MODEL_REPO, ALBERTITOS_MODELS

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ModelRepo = if ($env:LLAMA_MODEL_REPO) { $env:LLAMA_MODEL_REPO } else { "PaddlePaddle/PaddleOCR-VL-1.6-GGUF" }
$ModelsDir = if ($env:ALBERTITOS_MODELS) { $env:ALBERTITOS_MODELS } else { Join-Path $RepoRoot "models/llama" }
$Base = "https://huggingface.co/$ModelRepo/resolve/main"

function Log($msg) { Write-Host "[llama] $msg" }

# 1. Binario. El instalador de llama.app publica para Windows (x86_64);
#    winget instala el paquete clasico llama-server — ambos valen, el
#    manager detecta `serve` y hace fallback.
$llama = Get-Command llama -ErrorAction SilentlyContinue
if ($llama) {
    Log "ya instalado: $($llama.Source)"
} else {
    Log "instalando via https://llama.app/install.sh ..."
    try {
        $sh = Get-Command sh -ErrorAction SilentlyContinue
        if ($sh) {
            (Invoke-WebRequest -UseBasicParsing "https://llama.app/install.sh").Content | sh
        } else {
            Log "no hay sh en PATH; instalando con winget (llama.cpp)"
            winget install --id GGGML.llama.cpp -e --accept-source-agreements --accept-package-agreements
        }
    } catch {
        Log "instalador fallo ($($_.Exception.Message)); probando winget"
        winget install --id GGGML.llama.cpp -e --accept-source-agreements --accept-package-agreements
    }
}

# 2. Pesos (~1 GB total) con resume y verificacion de tamano.
New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
foreach ($name in @("PaddleOCR-VL-1.6-GGUF.gguf", "PaddleOCR-VL-1.6-GGUF-mmproj.gguf")) {
    $dest = Join-Path $ModelsDir $name
    if ((Test-Path $dest) -and ((Get-Item $dest).Length -gt 0)) {
        $mb = [math]::Round((Get-Item $dest).Length / 1MB)
        Log "$name presente (${mb} MB), saltando"
        continue
    }
    Log "descargando $name ..."
    $head = Invoke-WebRequest -UseBasicParsing -Method Head -Uri "$Base/$name"
    $expected = [long]$head.Headers["Content-Length"][0]
    Invoke-WebRequest -UseBasicParsing -Uri "$Base/$name" -OutFile "$dest.part"
    if ((Get-Item "$dest.part").Length -ne $expected) {
        Remove-Item "$dest.part"
        throw "tamano incorrecto para $name"
    }
    Move-Item "$dest.part" $dest
}

Log "setup completo"
Log "binario : $((Get-Command llama -ErrorAction SilentlyContinue).Source ?? '~/.llama-app o winget')"
Log "gguf    : $ModelsDir"
Log "arranque: uv run python -m albertitos.llama_manager start"
