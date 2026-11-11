@echo off
setlocal EnableDelayedExpansion
title Eternal Cabal Night Shift - Installer

REM ============================================================
REM  Eternal Cabal Night Shift - Windows installer
REM  Creates the scheduled task, initialises the database and
REM  verifies the background service. Touches nothing else.
REM ============================================================

cd /d "%~dp0"

echo.
echo  ============================================
echo   ETERNAL CABAL - NIGHT SHIFT COMPANION
echo   Windows Installer
echo  ============================================
echo.

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

REM --- 1. Locate a Python interpreter -------------------------------
set "PY="
for %%P in (python py) do (
  if not defined PY (
    %%P --version >nul 2>&1 && set "PY=%%P"
  )
)
if not defined PY (
  echo  [FAIL] Python was not found on PATH.
  echo         Install Python 3.10+ from https://python.org and re-run.
  exit /b 1
)
for /f "delims=" %%V in ('%PY% --version 2^>^&1') do echo  [OK] Python found: %%V

REM --- 2. Check required packages -----------------------------------
echo.
echo  [..] Checking dependencies...
set "MISSING="
%PY% -c "import fastapi" 2>nul || set "MISSING=!MISSING! fastapi"
%PY% -c "import uvicorn" 2>nul || set "MISSING=!MISSING! uvicorn"
%PY% -c "import requests" 2>nul || set "MISSING=!MISSING! requests"
%PY% -c "import psutil" 2>nul || set "MISSING=!MISSING! psutil"
%PY% -c "import yaml" 2>nul || set "MISSING=!MISSING! pyyaml"

if defined MISSING (
  echo  [..] Installing missing packages:!MISSING!
  %PY% -m pip install!MISSING! --quiet
  if errorlevel 1 (
    echo  [FAIL] Dependency installation failed.
    exit /b 1
  )
)
echo  [OK] Dependencies satisfied.

REM --- 3. Initialise the database -----------------------------------
echo.
echo  [..] Initialising database...
%PY% -c "import sys; sys.path.insert(0,'.'); from backend.db import init_db; init_db(); print('  database ready')"
if errorlevel 1 (
  echo  [FAIL] Database initialisation failed.
  exit /b 1
)

REM --- 4. Write default config --------------------------------------
if not exist "config.yaml" (
  echo  [..] Writing default config...
  %PY% -c "import sys; sys.path.insert(0,'.'); from backend.config import save_config, get_config; c=get_config(); save_config(c)"
)

REM --- 5. Create the scheduled task ---------------------------------
echo.
echo  [..] Configuring Windows scheduled task...

schtasks /Query /TN "EternalCabalNightShift" >nul 2>&1
if not errorlevel 1 (
  echo  [..] Existing task found. Recreating...
  schtasks /Delete /TN "EternalCabalNightShift" /F >nul 2>&1
)

REM Run at startup, 30s delay, restart on failure (3 attempts, 1 min apart).
schtasks /Create /TN "EternalCabalNightShift" ^
  /TR "\"%ROOT%\start_companion.bat\"" ^
  /SC ONSTART ^
  /DELAY 0000:30 ^
  /RU "%USERNAME%" ^
  /RL LIMITED ^
  /F >nul 2>&1

if errorlevel 1 (
  echo  [WARN] Could not create the scheduled task without elevation.
  echo         Re-run this installer as Administrator, or start the
  echo         companion manually with start_companion.bat
) else (
  echo  [OK] Scheduled task created: EternalCabalNightShift
)

REM Restart settings via schtasks is limited; apply with a follow-up command.
schtasks /Change /TN "EternalCabalNightShift" /RI 60 /DU 0001:00 /K >nul 2>&1
schtasks /Change /TN "EternalCabalNightShift" /ENABLE >nul 2>&1

REM --- 6. Test the background service --------------------------------
echo.
echo  [..] Testing the background service...
start "" /B "%ROOT%\start_companion.bat"
timeout /t 8 /nobreak >nul

%PY% -c "import sys,time; sys.path.insert(0,'.'); from backend.instance import read_heartbeat; time.sleep(1); hb=read_heartbeat(); print('  heartbeat pid:', hb.get('pid') if hb else 'NONE'); sys.exit(0 if hb else 1)"
if errorlevel 1 (
  echo  [WARN] Service did not report a heartbeat yet. Check logs\service.log
) else (
  echo  [OK] Background service is running.
)

REM --- 7. Verify Telegram connectivity ------------------------------
echo.
echo  [..] Checking Telegram connectivity...
%PY% -c "import sys; sys.path.insert(0,'.'); from backend.notify import connection_status; s=connection_status(); print('  telegram:', 'reachable' if s['reachable'] else 'unreachable'); print(' ', s.get('detail','')[:80])"

REM --- 8. Installation report ---------------------------------------
echo.
echo  ============================================
echo   INSTALLATION REPORT
echo  ============================================
echo   Project directory : %ROOT%
echo   Database          : %ROOT%\database\nightshift.db
echo   Config            : %ROOT%\config.yaml
echo   Scheduled task    : EternalCabalNightShift
echo   Dashboard         : http://127.0.0.1:8770
echo.
echo   Logs              : %ROOT%\logs
echo   Backups           : %ROOT%\backups
echo  ============================================
echo.

REM --- 9. Launch the dashboard --------------------------------------
echo  [..] Starting dashboard...
start "" "%ROOT%\open_dashboard.bat"

echo  Done. The companion runs at every Windows startup.
echo.
pause
