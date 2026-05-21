set TELEGRAM_TOKEN=8948698128:AAGg2agN-xGKh61NTn2dvDWuIGR3eSZztsk
set TELEGRAM_CHAT_ID=5439298818
@echo off
chcp 65001 > nul
title BTC/USDT Trading Bot - Live Dry-Run
color 0B
cls
echo =================================================================
echo   🚀 BTC/USDT TRADING BOT - MONITOR LIVE IN MODALITA' DRY-RUN
echo =================================================================
echo.
echo [INFO] Avvio del monitoraggio in tempo reale...
echo [INFO] Premi CTRL+C nel terminale per interrompere il bot.
echo -----------------------------------------------------------------
echo.
cd /d "%~dp0trading_bot"
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Si e' verificato un errore durante l'esecuzione del bot.
)
echo.
echo =================================================================
echo Il processo del Bot e' terminato.
pause
