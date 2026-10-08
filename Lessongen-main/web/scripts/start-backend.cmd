@echo off
setlocal
cd /d "%~dp0.."
if "%DB_PASSWORD%"=="" (
  echo [ERROR] 请先设置 DB_PASSWORD
  exit /b 1
)
if "%ENGINE_INTERNAL_TOKEN%"=="" (
  echo [ERROR] 请先设置与 Python 相同的 ENGINE_INTERNAL_TOKEN
  exit /b 1
)
call mvnw.cmd spring-boot:run
