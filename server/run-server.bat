@echo off
cd /d "%~dp0"
set ALKAMEL_HOST=0.0.0.0
if "%ALKAMEL_ADMIN_PASSWORD%"=="" set ALKAMEL_ADMIN_PASSWORD=ChangeThis-Admin-2026
py -3 server.py
pause
