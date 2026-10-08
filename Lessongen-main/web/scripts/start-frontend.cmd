@echo off
setlocal
cd /d "%~dp0..\frontend"
if not exist node_modules\ npm install
call npm run dev
