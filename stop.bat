@echo off
rem Stops the private PostgreSQL instance that start.bat started.
cd /d "%~dp0"
"C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" -D .pgdata -m fast -w stop
pause
