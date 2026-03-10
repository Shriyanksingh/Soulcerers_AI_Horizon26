@echo off
setlocal
cd /d "%~dp0"

echo Launching latest backend (8010) in new window...
start "SmartNav Backend 8010" cmd /k run_latest_backend_8010.bat

ping 127.0.0.1 -n 3 >nul

echo Launching frontend (5173) in new window...
start "SmartNav Frontend 5173" cmd /k run_frontend_5173.bat

echo.
echo Open: http://127.0.0.1:5173
echo Backend: http://127.0.0.1:8010/health
endlocal
