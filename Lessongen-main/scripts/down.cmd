@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
if not exist ".env" (
  echo [ERROR] No repository .env was found. Nothing to stop.
  exit /b 1
)
docker compose --env-file .env down
echo Containers stopped. The MySQL volume and runtime files were preserved.
