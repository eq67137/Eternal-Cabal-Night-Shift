@echo off
setlocal
title Eternal Cabal Night Shift - Dashboard

cd /d "%~dp0"

set "PY="
for %%P in (python py) do (
  if not defined PY (
    %%P -c "import fastapi, uvicorn" 2>nul && set "PY=%%P"
  )
)
if not defined PY (
  for %%P in (python py) do (
    if not defined PY (
      %%P --version >nul 2>&1 && set "PY=%%P"
    )
  )
)
if not defined PY (
  echo [dashboard] Python not found. Run install.bat first.
  exit /b 1
)

start "" http://127.0.0.1:8770
echo  [dashboard] Starting on http://127.0.0.1:8770
echo.

"%PY%" "%~dp0backend\dashboard.py"
