@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
where docker >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Docker Desktop is required for one-command full-stack startup.
  exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Start Docker Desktop, then retry scripts\up.cmd.
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-local.ps1"
if errorlevel 1 exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0validate-local.ps1"
if errorlevel 1 exit /b 1
set "LESSONGEN_BUILD_COMMIT=unknown"
set "LESSONGEN_BUILD_DIRTY=unknown"
for /f "tokens=1,2 delims=|" %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-metadata.ps1"') do (
  set "LESSONGEN_BUILD_COMMIT=%%I"
  set "LESSONGEN_BUILD_DIRTY=%%J"
)
if "%LESSONGEN_BUILD_COMMIT%"=="unknown" echo [WARN] Git build provenance is unavailable; source health will report unknown.
docker compose --env-file .env config --quiet
if errorlevel 1 exit /b 1
set "RUNNING_CONTAINER="
for /f "delims=" %%I in ('docker compose --env-file .env ps -q') do set "RUNNING_CONTAINER=%%I"
if not defined RUNNING_CONTAINER (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check-ports.ps1"
  if errorlevel 1 exit /b 1
)
docker compose --env-file .env up --build -d --wait --wait-timeout 180
if errorlevel 1 (
  echo [ERROR] Stack did not start. Check whether an old C-drive Java service owns port 8080.
  exit /b 1
)
docker compose --env-file .env ps
echo Open http://127.0.0.1:5173 after all services are healthy.
