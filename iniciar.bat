@echo off
rem Alberto: abre la app de facturas (Windows).
cd /d "%~dp0"
where uv >nul 2>nul || (echo Falta uv - instala con: powershell -c "irm https://astral.sh/uv/install.ps1 | iex" & exit /b 1)
uv run python -m albertitos.desktop %*
