# Alberto: abre la app de facturas (Windows PowerShell).
Set-Location -Path $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "Falta uv — instalándolo…"
  irm https://astral.sh/uv/install.ps1 | iex
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "ERROR: uv no quedó en el PATH — abre otra terminal y reintenta"
  exit 1
}
uv run python -m albertitos.desktop @args
