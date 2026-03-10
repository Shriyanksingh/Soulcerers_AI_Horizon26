@echo off
setlocal
cd /d "%~dp0"

set "PY_EXE=C:\Users\LENOVO\AppData\Local\Programs\Python\Python311\python.exe"

if exist "%PY_EXE%" (
  echo Starting latest backend on http://127.0.0.1:8010 ...
  "%PY_EXE%" -m uvicorn backend.app:app --host 127.0.0.1 --port 8010
) else (
  echo Python at "%PY_EXE%" not found. Trying default python...
  python -m uvicorn backend.app:app --host 127.0.0.1 --port 8010
)

endlocal
