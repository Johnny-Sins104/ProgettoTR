@echo off
setlocal EnableExtensions

REM ProgettoTR - Dashboard launcher
REM Starts the local web dashboard at http://127.0.0.1:8050/
REM The browser opens automatically. CTRL+C in this window to stop.

cd /d "%~dp0"

echo ================================================================
echo   ProgettoTR - Web Dashboard
echo   http://127.0.0.1:8050/
echo ================================================================
echo.

if not exist "web\server.py" (
    echo [ERROR] File not found: web\server.py
    echo [ERROR] Run this .bat from the project root folder.
    pause
    exit /b 1
)

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

echo [INFO] Dashboard server starting...
echo [INFO] Il browser si apre automaticamente.
echo [INFO] Premi CTRL+C per fermare il server.
echo.

%PYTHON_CMD% web\server.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Dashboard terminated with an error. See above.
    pause
    exit /b %ERRORLEVEL%
)

pause
exit /b 0
