@echo off
rem Alberto: abre la app de facturas (Windows).
cd /d "%~dp0"
where uv >nul 2>nul || (echo Falta uv - instalando... & powershell -NoProfile -c "irm https://astral.sh/uv/install.ps1 | iex" & set "PATH=%USERPROFILE%\.local\bin;%PATH%")
where uv >nul 2>nul || (echo ERROR: uv no quedo en el PATH - abre otra terminal y reintenta & exit /b 1)
uv run python -m albertitos.desktop %*
