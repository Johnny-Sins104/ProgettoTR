@echo off
setlocal EnableExtensions

REM ProgettoTR - Paper-live launcher for Windows CMD
REM Do NOT hardcode API keys or Telegram tokens in this file.
REM Secrets may be loaded by the Python app from .env or environment variables.

cd /d "%~dp0"

echo ================================================================
echo   ProgettoTR - Live/Dry-Run Bot
echo ================================================================
echo.

if not exist "trading_bot\main.py" (
    echo [ERROR] File not found: trading_bot\main.py
    echo [ERROR] Run this .bat from the project root folder.
    pause
    exit /b 1
)

echo.
echo [INFO] Paper-live mode: no live/testnet/exchange broker is enabled.
echo [INFO] Telegram credentials, if configured, are loaded by the Python app.
echo [INFO] LSR-v2 read-only dashboard banner will be printed by avvia_bot_live.py when artifacts are ready.
echo [INFO] Launcher visibility is read-only: no Telegram send, no scheduler, no submit/close.
echo.
echo [INFO] Starting bot from project root. Press CTRL+C to stop.
echo.

set "PYTHON_CMD="

python --version >nul 2>nul
if %ERRORLEVEL%==0 set "PYTHON_CMD=python"

if "%PYTHON_CMD%"=="" (
    py --version >nul 2>nul
    if %ERRORLEVEL%==0 set "PYTHON_CMD=py"
)

if "%PYTHON_CMD%"=="" (
    set "PYTHON_CMD=C:\Users\Davide\AppData\Local\Microsoft\WindowsApps\python.exe"
)

%PYTHON_CMD% trading_bot\avvia_bot_live.py --mode paper-live --symbols BTC/USDT --timeframe 5m --cost-model conservative --max-cycles 0 --poll-seconds 20 --no-cycle-artifacts

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Bot terminated with an error. See the error above.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ================================================================
echo Bot process ended.
echo ================================================================
echo.
echo [INFO] Final read-only paper diagnosis:
%PYTHON_CMD% trading_bot\avvia_bot_live.py --paper-blockers --tail 500
echo.
pause
exit /b 0
