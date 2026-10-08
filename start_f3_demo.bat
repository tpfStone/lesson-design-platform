@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%~dp0SimClass-main\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo [ERROR] Project Python virtual environment was not found.
  echo Expected one of:
  echo   %~dp0SimClass-main\.venv\Scripts\python.exe
  echo   %~dp0.venv\Scripts\python.exe
  exit /b 2
)

if not exist "%~dp0f3_demo_config.json" (
  echo [ERROR] f3_demo_config.json was not found.
  echo Copy f3_demo_config.example.json to f3_demo_config.json and fill f4SessionId.
  exit /b 2
)

"%PYTHON%" "%~dp0run_f3_demo.py" --config "%~dp0f3_demo_config.json"
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo [ERROR] F3 demo failed. Exit code: %RC%
  exit /b %RC%
)

echo [OK] F3 demo completed. The two output paths are printed above.
exit /b 0
