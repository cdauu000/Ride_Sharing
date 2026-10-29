@echo off
cd /d "%~dp0.."
if not exist web\node_modules (
  call npm.cmd --prefix web ci
  if errorlevel 1 exit /b 1
)
if not exist artifacts\review\web-v2\.next\BUILD_ID (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\prepare-review.ps1
  if errorlevel 1 exit /b 1
)
set RISE_LOCAL_REVIEW=true
cd /d "%~dp0..\artifacts\review\web-v2"
node ../../../web/node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3020
