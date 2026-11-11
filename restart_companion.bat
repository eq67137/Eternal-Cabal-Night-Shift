@echo off
setlocal
title Eternal Cabal Night Shift - Restart

cd /d "%~dp0"

echo.
echo  Restarting the Night Shift companion...
echo.

call "%~dp0stop_companion.bat" <nul
timeout /t 3 /nobreak >nul

start "" "%~dp0start_companion.bat"

echo  [OK] Restart requested.
timeout /t 6 /nobreak >nul

"%~dp0scripts\check_health.py"

echo.
pause
