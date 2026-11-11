@echo off
setlocal
title Eternal Cabal Night Shift - Uninstall

cd /d "%~dp0"

echo.
echo  ============================================
echo   ETERNAL CABAL NIGHT SHIFT - UNINSTALL
echo  ============================================
echo.
echo  This removes only this project's scheduled task and
echo  creates a final backup before deleting project data.
echo.
set /p CONFIRM="Type YES to continue: "
if /I not "%CONFIRM%"=="YES" (
  echo  Cancelled.
  exit /b 0
)

echo.
echo  [..] Stopping the service...
call "%~dp0stop_companion.bat" <nul

echo.
echo  [..] Creating final backup...
"%~dp0scripts\final_backup.py"

echo.
echo  [..] Removing scheduled task...
schtasks /Delete /TN "EternalCabalNightShift" /F >nul 2>&1
if errorlevel 1 (
  echo  [WARN] Could not remove the scheduled task.
  echo         Remove it manually from Task Scheduler.
) else (
  echo  [OK] Scheduled task removed.
)

echo.
echo  [..] Removing project files...
cd /d "%USERPROFILE%\Documents"
rmdir /S /Q "%~dp0" 2>nul

echo.
echo  [OK] Uninstall complete.
echo.
pause
