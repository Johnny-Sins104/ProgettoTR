@echo off
setlocal EnableExtensions

REM ProgettoTR - Backtest launcher for Windows CMD
REM ASCII-only file to avoid encoding problems in .bat execution.

cd /d "%~dp0"

echo ================================================================
echo   ProgettoTR - Backtest Runner
echo ================================================================
echo.

if not exist "trading_bot\run_custom_backtest.py" (
    echo [ERROR] File not found: trading_bot\run_custom_backtest.py
    echo [ERROR] Run this .bat from the project root folder.
    pause
    exit /b 1
)

set "CAPITAL="
set "CANDLES="

set /p CAPITAL=Initial capital in EUR [default: 100]: 
if "%CAPITAL%"=="" set "CAPITAL=100"

echo.
echo Choose number of candles to test:
echo   1000   approx 3.5 days on 5m timeframe
echo   2000   approx 7 days on 5m timeframe
echo   5000   approx 17 days on 5m timeframe
echo   10000  approx 35 days on 5m timeframe
echo.
set /p CANDLES=Number of candles [default: 5000]: 
if "%CANDLES%"=="" set "CANDLES=5000"

echo.
echo [INFO] Starting backtest with %CAPITAL% EUR on %CANDLES% candles...
echo.

cd /d "%~dp0trading_bot"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 run_custom_backtest.py --balance %CAPITAL% --candles %CANDLES%
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        python run_custom_backtest.py --balance %CAPITAL% --candles %CANDLES%
    ) else (
        echo [ERROR] Python not found. Install Python 3 and add it to PATH.
        pause
        exit /b 1
    )
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Backtest failed. See the error above.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ================================================================
echo Backtest completed.
echo ================================================================
pause
exit /b 0
