@echo off
chcp 65001 > nul
title BTC/USDT Trading Bot - Simulatore di Backtest
color 0E
cls
echo =================================================================
echo   📊 SIMULATORE DI BACKTEST INTERATTIVO - BTC/USDT 5M
echo =================================================================
echo.

set /p CAPITAL="💰 Inserisci il capitale iniziale in euro [default: 100]: "
if "%CAPITAL%"=="" set CAPITAL=100

echo.
echo 🕒 Scegli la durata del test in candele (Timeframe 5m):
echo   - 1000  candele (circa 3.5 giorni)
echo   - 2000  candele (circa 7 giorni)
echo   - 5000  candele (circa 17 giorni)
echo   - 10000 candele (circa 35 giorni - massimo disponibile)
echo.
set /p CANDLES="📊 Inserisci il numero di candele da testare [default: 5000]: "
if "%CANDLES%"=="" set CANDLES=5000

echo.
echo -----------------------------------------------------------------
echo [INFO] Avvio simulazione con %CAPITAL% EUR su %CANDLES% candele...
echo -----------------------------------------------------------------
echo.
cd /d "%~dp0trading_bot"
python run_custom_backtest.py --balance %CAPITAL% --candles %CANDLES%
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Si e' verificato un errore durante la simulazione.
)
echo.
echo =================================================================
echo Simulazione completata. 
pause
