# Setup llama.cpp + PaddleOCR-VL full-Q8 para Windows (PowerShell 5.1+).
# Equivalente a scripts/setup_llama.sh: binario + pesos en <repo>/models/llama.
# Sin admin, sin /tmp.
#
# Instalacion del binario, en orden de preferencia (todo user-space):
#   (a) llama/llama-server ya en PATH
#   (b) release portable oficial de ggml-org/llama.cpp -> %USERPROFILE%\.llama-app
#       (llama-server.exe + DLLs ggml-*, sin carpeta interna)
#   (c) winget --id ggml.llamacpp --scope user (instalador portable, sin admin)
# No se usa `install.sh | sh` en Windows: ese instalador es para Linux/macOS/FreeBSD.
#
# Modelo (docs/decisiones/DECISIONS.md D-002): Mungert full-Q8 (texto q8_0 +
# mmproj q8_0). El repo oficial PaddlePaddle publica bf16/f16, no Q8.
#
# Uso:  powershell -File scripts/setup_llama.ps1
# Env:  LLAMA_MODEL_REPO, FILEMAID_MODELS,
#       FILEMAID_LLAMA_WIN_VARIANT (cpu por defecto; cuda-12.4|cuda-13.3|vulkan|...)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ModelRepo = if ($env:LLAMA_MODEL_REPO) { $env:LLAMA_MODEL_REPO } else { "Mungert/PaddleOCR-VL-1.6-GGUF" }
$ModelsDir = if ($env:FILEMAID_MODELS) { $env:FILEMAID_MODELS } else { Join-Path $RepoRoot "models/llama" }
$Base = "https://huggingface.co/$ModelRepo/resolve/main"
$Variant = if ($env:FILEMAID_LLAMA_WIN_VARIANT) { $env:FILEMAID_LLAMA_WIN_VARIANT } else { "cpu" }
$LlamaHome = Join-Path $HOME ".llama-app"

function Log($msg) { Write-Host "[llama] $msg" }

function Find-Llama {
    foreach ($name in @("llama", "llama-server")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    foreach ($name in @("llama.exe", "llama-server.exe")) {
        $cand = Join-Path $LlamaHome $name
        if (Test-Path $cand) { return $cand }
    }
    return $null
}

# 1. Binario.
$bin = Find-Llama
if ($bin) {
    Log "ya instalado: $bin"
} else {
    # (b) release portable oficial: tag actual + zip win-<variant>-x64.
    $installed = $false
    try {
        $tag = (Invoke-WebRequest -UseBasicParsing "https://github.com/ggml-org/llama.cpp/releases/latest/download/nightly-tag.txt").Content.Trim()
        $zipName = "llama-$tag-bin-win-$Variant-x64.zip"
        $zipUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$tag/$zipName"
        New-Item -ItemType Directory -Force -Path $LlamaHome | Out-Null
        $zipPath = Join-Path $LlamaHome "llama-portable.zip"
        Log "descargando release portable $tag ($Variant) ..."
        Invoke-WebRequest -UseBasicParsing -Uri $zipUrl -OutFile $zipPath
        Expand-Archive -Path $zipPath -DestinationPath $LlamaHome -Force
        Remove-Item $zipPath -Force
        $installed = $true
    } catch {
        Log "release portable fallo: $($_.Exception.Message)"
    }
    # (c) winget portable, sin admin.
    if (-not $installed) {
        Log "instalando con winget (ggml.llamacpp, scope user)"
        winget install --id ggml.llamacpp -e --scope user --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { throw "winget fallo (exit $LASTEXITCODE)" }
    }
    $bin = Find-Llama
    if (-not $bin) { throw "no se encontro el binario llama/llama-server tras la instalacion" }
}

# 2. Pesos (D-002 full Q8, ~1.10 GB) con verificacion sha256.
New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
$files = @(
    @{ Name = "PaddleOCR-VL-1.6-q8_0.gguf";   Size = 498316064; Sha = "58ff75f8ca2ad8bc4308324d0df570ef77832479b2a80091134fc33e11955a3a" },
    @{ Name = "PaddleOCR-VL-1.6-q8_0.mmproj"; Size = 597566368; Sha = "036d06ea82e9133696c2f93bd9dd2e1e5009520811e5fb3092aab2d0e5696375" }
)
foreach ($f in $files) {
    $dest = Join-Path $ModelsDir $f.Name
    if ((Test-Path $dest) -and ((Get-Item $dest).Length -eq $f.Size)) {
        $sha = (Get-FileHash -Algorithm SHA256 -Path $dest).Hash.ToLower()
        if ($sha -eq $f.Sha) {
            Log "$($f.Name) presente y verificado, saltando"
            continue
        }
    }
    Log "descargando $($f.Name) ..."
    Invoke-WebRequest -UseBasicParsing -Uri "$Base/$($f.Name)" -OutFile "$dest.part"
    if ((Get-Item "$dest.part").Length -ne $f.Size) {
        Remove-Item "$dest.part"
        throw "tamano incorrecto para $($f.Name)"
    }
    $sha = (Get-FileHash -Algorithm SHA256 -Path "$dest.part").Hash.ToLower()
    if ($sha -ne $f.Sha) {
        Remove-Item "$dest.part"
        throw "sha256 incorrecto para $($f.Name)"
    }
    Move-Item -Force "$dest.part" $dest
}

Log "setup completo"
Log "binario : $(Find-Llama)"
Log "gguf    : $ModelsDir"
Log "arranque: uv run python -m filemaid.llama_manager start"
