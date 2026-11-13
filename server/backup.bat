@echo off
cd /d "%~dp0"
if not exist backups mkdir backups
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set STAMP=%%i
if exist data\alkamel_admin.db copy /Y data\alkamel_admin.db backups\alkamel_admin-%STAMP%.db
echo Backup completed.
