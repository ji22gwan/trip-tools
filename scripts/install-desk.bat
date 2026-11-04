@echo off
chcp 65001 >nul
rem 음성 인식(전사)까지 설치하려면:  install-desk.bat whisper
if /i "%~1"=="whisper" set WHISPER=1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-desk.ps1"
pause
