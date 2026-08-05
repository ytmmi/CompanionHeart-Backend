@echo off
REM CompanionHeart 设置服务启动脚本
REM 端口: 17999

cd /d "%~dp0.."
set PYTHONPATH=%~dp0..
.venv\python.exe www\settings_server.py
pause
