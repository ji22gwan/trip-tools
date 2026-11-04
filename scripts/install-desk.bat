@echo off
chcp 65001 >nul
rem 크롬 대신 전용 창으로 쓰려면:  install-desk.bat qt   (whisper 와 함께: install-desk.bat whisper qt)
if /i "%~1"=="qt" set QT=1
if /i "%~2"=="qt" set QT=1
rem 음성 인식(전사)까지 설치하려면:  install-desk.bat whisper
if /i "%~1"=="whisper" set WHISPER=1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-desk.ps1"
pause
