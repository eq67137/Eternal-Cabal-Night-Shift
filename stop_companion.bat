@echo off
setlocal
title Eternal Cabal Night Shift - Stop

cd /d "%~dp0"

echo.
echo  Stopping the Night Shift companion...
echo.

REM Ask the running service to stop gracefully via its state file.
"%~dp0scripts\stop_service.py"

if errorlevel 1 (
  echo  [WARN] Graceful stop was not confirmed.
  echo         The service will also exit when its scheduled task is ended.
) else (
  echo  [OK] Stop request sent.
)

REM End the scheduled task if it is currently running.
schtasks /End /TN "EternalCabalNightShift" >nul 2>&1

echo.
pause
