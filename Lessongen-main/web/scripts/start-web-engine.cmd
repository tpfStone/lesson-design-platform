@echo off
setlocal

for %%I in ("%~dp0..\..\paper4_pipeline") do set "PIPELINE_ROOT=%%~fI"
if not exist "%PIPELINE_ROOT%\src\paper4_pipeline\providers\openai_compatible.py" (
  echo [ERROR] Lessongen Python source was not found at "%PIPELINE_ROOT%".
  exit /b 1
)

cd /d "%PIPELINE_ROOT%" || exit /b 1
set "PYTHON_EXE=%PIPELINE_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo [ERROR] Lessongen .venv is missing. Install uv and run:
  echo         cd /d "%PIPELINE_ROOT%"
  echo         uv sync --locked --extra web --extra dev
  exit /b 1
)
set "PYTHONPATH=%PIPELINE_ROOT%\src;%PYTHONPATH%"

"%PYTHON_EXE%" -c "import pathlib,sys,paper4_pipeline.providers.openai_compatible as p; expected=(pathlib.Path.cwd()/'src'/'paper4_pipeline'/'providers'/'openai_compatible.py').resolve(); actual=pathlib.Path(p.__file__).resolve(); print('Using Python provider:',actual); sys.exit(0 if actual==expected else 1)"
if errorlevel 1 (
  echo [ERROR] Python imported a different paper4_pipeline installation. Recreate the local .venv and retry.
  exit /b 1
)

"%PYTHON_EXE%" -c "import hashlib,json,os,sys; from paper4_pipeline.web_api.app import _build_fingerprint; from paper4_pipeline.web_api.settings import EngineSettings; s=EngineSettings.from_environment(); commit,dirty=_build_fingerprint(); key=bool(os.getenv('DEEPSEEK_API_KEY','').strip()); token=bool(s.internal_token); config=s.config_path.is_file(); limits=json.loads(s.config_path.read_text(encoding='utf-8'))['role_model_configs'] if config else {}; digest=hashlib.sha256(s.config_path.read_bytes()).hexdigest() if config else 'missing'; print('Build commit:',commit); print('Build dirty:',dirty); print('Python executable:',sys.executable); print('DeepSeek key configured:',key); print('Engine token configured:',token); print('Config file:',s.config_path,'exists:',config); print('Config SHA256:',digest); print('Writer max_tokens:',limits.get('writer_v0_1',{}).get('max_tokens')); print('Rewriter max_tokens:',limits.get('rewriter_v0_1',{}).get('max_tokens')); print('State root:',s.state_root); print('Artifacts root:',s.artifacts_root); sys.exit(0 if key and token and config else 1)"
if errorlevel 1 (
  echo [ERROR] Configure DEEPSEEK_API_KEY and ENGINE_INTERNAL_TOKEN in the repository .env or your current process.
  exit /b 1
)

if /I "%~1"=="--check" exit /b 0
"%PYTHON_EXE%" -c "import socket,sys; conn=socket.socket(); busy=conn.connect_ex(('127.0.0.1',8001))==0; conn.close(); sys.exit(1 if busy else 0)"
if errorlevel 1 (
  echo [ERROR] Port 8001 is already in use. Stop the old service and check its PID with Get-NetTCPConnection before starting this F-drive engine.
  exit /b 1
)
"%PYTHON_EXE%" -m paper4_pipeline.web_api
