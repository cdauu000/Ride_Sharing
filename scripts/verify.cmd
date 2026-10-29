@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m ruff check app research tests scripts migrations
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pytest
if errorlevel 1 exit /b 1
cd web
call npm.cmd run typecheck
if errorlevel 1 exit /b 1
call npm.cmd test
if errorlevel 1 exit /b 1
call npm.cmd run format:check
if errorlevel 1 exit /b 1
call npm.cmd run test:e2e
if errorlevel 1 exit /b 1
call npm.cmd run build
if errorlevel 1 exit /b 1
cd ..\contracts
call npm.cmd test
if errorlevel 1 exit /b 1
cd ..
".venv\Scripts\python.exe" contracts/scripts/verify_adapter.py
