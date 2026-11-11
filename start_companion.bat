@echo off
setlocal
title Eternal Cabal Night Shift - Companion

cd /d "%~dp0"

REM Resolve a Python interpreter: prefer the one that has our deps.
set "PY="
for %%P in (python py) do (
  if not defined PY (
    %%P -c "import fastapi, uvicorn, requests, psutil, yaml" 2>nul && set "PY=%%P"
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
  echo [nightshift] Python not found. Install Python 3.10+ and re-run install.bat
  exit /b 1
)

if not exist "logs" mkdir "logs"

REM Append to a rolling log so the task scheduler never blocks on a handle.
"%PY%" "%~dp0backend\service.py" >> "%~dp0logs\service.log" 2>&1
