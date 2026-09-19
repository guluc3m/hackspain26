# Alberto: abre la app de facturas (Windows PowerShell).
Set-Location -Path $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "Falta uv — instala con: irm https://astral.sh/uv/install.ps1 | iex"
  exit 1
}
uv run python -m albertitos.desktop @args
