@echo off
chcp 936 >nul
cd /d %~dp0
title OCR 组件安装（easyocr）

echo ============================================
echo   教案智能批注系统 - OCR 组件安装
echo ============================================
echo.
echo  说明：本组件仅用于评阅「扫描版 PDF」（整页图片、无法选中文字）。
echo        Word 教案与文字版 PDF 不需要安装本组件。
echo.
echo  体积：约 2 GB     耗时：视网速 5-20 分钟
echo.
set /p CONFIRM=确认开始安装？(Y 继续 / 其它键取消): 
if /i not "%CONFIRM%"=="Y" goto cancel
echo.

REM ===== 探测 Python =====
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
if not defined PY goto nopython

echo  使用的 Python：
%PY% -c "import sys; print('    路径:', sys.executable); print('    版本:', sys.version.split()[0])"
echo.
echo  [1/2] 正在下载安装（约 2GB，请耐心等待，不要关闭窗口）...
echo.
%PY% -m pip install easyocr -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto fail

echo.
echo  [2/2] 安装自检...
%PY% -c "import easyocr; print('    OK - easyocr 安装成功')"
if errorlevel 1 goto fail

echo.
echo ============================================
echo   安装完成！
echo.
echo   下一步：直接上传扫描版 PDF 评分即可，
echo          系统会自动使用 OCR（首次运行会自动下载识别模型）。
echo          注意：扫描版单份耗时约 5-10 分钟。
echo ============================================
echo.
pause
exit /b 0

:nopython
echo.
echo [错误] 未检测到 Python。
echo        请先安装 Python 3.10 或更高版本（安装时勾选 Add Python to PATH）。
pause
exit /b 1

:fail
echo.
echo [错误] 安装失败。常见原因与解决办法：
echo   1) 网络问题：重试本脚本，或手动执行下面命令（使用清华镜像）：
echo        %PY% -m pip install easyocr -i https://pypi.tuna.tsinghua.edu.cn/simple
echo   2) 磁盘空间不足：easyocr 含 PyTorch，需约 2-3GB 空闲空间
echo   3) 装到了别的 Python：请用  python -m pip install ...  形式安装
echo.
echo   详细说明见：docs\OCR安装与使用说明.md
pause
exit /b 1

:cancel
echo.
echo 已取消安装。
pause
exit /b 0
