@echo off
cd /d "%~dp0.."
set RISE_DATABASE_URL=sqlite:///./artifacts/review/rise.db
set RISE_ESCROW_JOURNAL_PATH=artifacts/review/escrow.db
set RISE_ALLOWED_ORIGINS=["http://127.0.0.1:3020"]
set RISE_RUN_WORKER=true
set RISE_MODEL_ARTIFACT_PATH=artifacts/models/main_v1
if not exist artifacts\review mkdir artifacts\review
".venv\Scripts\python.exe" -m app.cli init-demo
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8020 --timeout-keep-alive 30 --no-access-log
