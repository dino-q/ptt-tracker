@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title PTT Assistant - Weekend Deals

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] PTT Assistant has not been installed yet.
    echo Please run 安裝套件.bat first.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" ptt_tool.py --weekend-deals
set "ERR=%errorlevel%"

echo.
if not "%ERR%"=="0" (
    echo [ERROR] 執行失敗，錯誤代碼：%ERR%
)
pause
exit /b %ERR%
