@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Create .venv with Python 3.12+ and install the project first. See README.md.
  exit /b 1
)
".venv\Scripts\python.exe" -m app.cli init-demo
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --timeout-keep-alive 30 --no-access-log
