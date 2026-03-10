@echo off
setlocal
cd /d "%~dp0\\frontend"
echo Starting frontend on http://127.0.0.1:5173 ...
node server.js
endlocal
