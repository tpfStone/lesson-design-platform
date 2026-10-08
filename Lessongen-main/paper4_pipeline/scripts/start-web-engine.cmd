@echo off
setlocal
call "%~dp0..\..\web\scripts\start-web-engine.cmd" %*
exit /b %errorlevel%
