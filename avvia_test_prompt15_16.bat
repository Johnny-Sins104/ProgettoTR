@echo off
setlocal EnableExtensions

REM ProgettoTR - Prompt 15/16 integration tests

cd /d "%~dp0trading_bot"

echo ================================================================
echo   ProgettoTR - Prompt 15/16 Test Suite
echo ================================================================
echo.

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PYTHON_CMD=python"
    ) else (
        echo [ERROR] Python not found. Install Python 3 and add it to PATH.
        pause
        exit /b 1
    )
)

%PYTHON_CMD% test_prompt15_16_integration.py || goto fail
%PYTHON_CMD% test_execution_model.py || goto fail
%PYTHON_CMD% test_risk_engine.py || goto fail
%PYTHON_CMD% run_execution_analysis.py || goto fail
%PYTHON_CMD% run_portfolio_backtest.py || goto fail

echo.
echo [OK] Prompt 15/16 tests and diagnostics completed.
pause
exit /b 0

:fail
echo.
echo [ERROR] Test suite failed. See the error above.
pause
exit /b 1
