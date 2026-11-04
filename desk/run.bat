@echo off
cd /d "%~dp0"
py -3 -m tripdesk %*
if errorlevel 1 python -m tripdesk %*
pause
