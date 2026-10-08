@echo off
chcp 936 >nul
cd /d %~dp0
title 教案智能批注系统

echo ============================================
echo   教案智能批注系统 - 本地 Web 界面
echo ============================================
echo.

REM ===== 探测 Python（依次尝试：本机常用路径 -^> py -^> python -^> python3）=====
set PY=
if exist "D:\python\python.exe" set PY=D:\python\python.exe
if not defined PY (
  py -3 --version >nul 2>nul
  if not errorlevel 1 set PY=py -3
)
if not defined PY (
  python --version >nul 2>nul
  if not errorlevel 1 set PY=python
)
if not defined PY (
  python3 --version >nul 2>nul
  if not errorlevel 1 set PY=python3
)
if not defined PY goto nopython

for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo   Python 版本：%%v
echo   项目目录：%~dp0
echo.

REM ===== 端口占用检查 =====
netstat -ano | findstr ":8501" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo [提示] 服务已经在运行，正在打开浏览器...
  start "" http://localhost:8501
  ping -n 3 127.0.0.1 >nul
  goto end
)

REM ===== 跳过 Streamlit 首次运行的邮箱引导 =====
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  echo [general]> "%USERPROFILE%\.streamlit\credentials.toml"
  echo email = "">> "%USERPROFILE%\.streamlit\credentials.toml"
)

REM ===== 依赖检查（缺失时自动安装）=====
"%PY%" -c "import streamlit, docx, fitz, yaml, openpyxl" >nul 2>nul
if errorlevel 1 (
  echo [1/2] 首次运行，正在安装依赖，约 2-5 分钟，请耐心等待...
  echo       如果很慢，可先按 Ctrl+C 终止，然后手动执行下面的命令换国内源安装：
  echo       %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  echo.
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 goto pipfail
) else (
  echo [1/2] 依赖检查通过
)

echo.
echo [2/2] 正在启动服务，约 10 秒后自动打开浏览器...
echo.
echo   地址：http://localhost:8501
echo   首次使用请在网页左侧「设置」页填写 API Key 并保存
echo   如果没有自动打开，请手动在浏览器输入上面的地址
echo   使用完毕后，关闭本窗口即可停止服务
echo.

start "" cmd /c "ping -n 10 127.0.0.1 >nul & start http://localhost:8501"

"%PY%" -m streamlit run web/app.py --server.port 8501 --server.headless true
goto end

:nopython
echo [错误] 未检测到 Python。
echo.
echo   请先安装 Python 3.10 或更高版本：
echo     1. 打开 https://www.python.org/downloads/
echo     2. 下载 Windows 安装包并运行
echo     3. 安装时务必勾选  "Add Python to PATH"
echo     4. 安装完成后重新双击本文件
echo.
pause
goto end

:pipfail
echo.
echo [错误] 依赖安装失败。
echo   常见原因：网络问题。
echo   请尝试手动执行下面命令（使用清华镜像源）：
echo     %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.
pause
goto end

:end
pause
