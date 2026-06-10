@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0monitor_live.ps1" %*
exit /b %ERRORLEVEL%
