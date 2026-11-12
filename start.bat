@echo off
rem One-click start for local runs on Windows: double-click this file.
rem   1. starts the private PostgreSQL instance (port 5434) if it is not running
rem   2. applies any new migrations
rem   3. asks whether to reset the demo data (answers No after 5 seconds)
rem   4. opens the customer page and the staff page (two browser tabs) and
rem      starts the service on http://127.0.0.1:8000
rem Close this window or press Ctrl+C to stop the service.
rem The database keeps running; stop.bat stops it.
setlocal
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
set PGBIN=C:\Program Files\PostgreSQL\18\bin

echo [1/4] Database
"%PGBIN%\pg_ctl.exe" -D .pgdata status >nul 2>&1
if errorlevel 1 (
    "%PGBIN%\pg_ctl.exe" -D .pgdata -l .pgdata.log -o "-p 5434" -w start
) else (
    echo   already running
)

echo [2/4] Migrations
%PY% migrate.py || goto :failed

echo [3/4] Demo data
choice /C YN /T 5 /D N /M "  Reset the demo data (all orders are deleted)"
if errorlevel 2 (
    echo   kept as it is
) else (
    %PY% seed.py || goto :failed
)

echo [4/4] Service
echo   Customer page: http://127.0.0.1:8000/customer  (log in as alice or register)
echo   Staff page:    http://127.0.0.1:8000/staff     (log in as staff)
echo   Contract:      http://127.0.0.1:8000/docs
echo   Press Ctrl+C to stop.
rem Open both pages a few seconds later, once the service is listening.
rem Each tab keeps its own login, so one can be a customer and the other staff.
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000/customer & start http://127.0.0.1:8000/staff"
%PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof

:failed
echo.
echo Something went wrong (see the message above).
pause
