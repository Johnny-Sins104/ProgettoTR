@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0orchestrator.ps1" %*
exit /b %ERRORLEVEL%
