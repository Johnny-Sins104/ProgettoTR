@echo off
setlocal EnableExtensions

REM ProgettoTR - Live/Dry-run launcher for Windows CMD
REM Do NOT hardcode API keys or Telegram tokens in this file.
REM Set secrets as Windows environment variables instead.

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

if "%API_KEY%"=="" echo [WARN] API_KEY is not set. Exchange private actions may be disabled.
if "%API_SECRET%"=="" echo [WARN] API_SECRET is not set. Exchange private actions may be disabled.
if "%TELEGRAM_TOKEN%"=="" echo [WARN] TELEGRAM_TOKEN is not set. Telegram alerts disabled.
if "%TELEGRAM_CHAT_ID%"=="" echo [WARN] TELEGRAM_CHAT_ID is not set. Telegram alerts disabled.

echo.
echo [INFO] Starting bot. Press CTRL+C to stop.
echo.

cd /d "%~dp0trading_bot"

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

%PYTHON_CMD% main.py

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
pause
exit /b 0
