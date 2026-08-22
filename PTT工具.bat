@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title PTT Assistant

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] PTT Assistant has not been installed yet.
    echo Please run 安裝套件.bat first.
    echo.
    pause
    exit /b 1
)

echo.
echo ================================
echo        PTT Assistant
echo ================================
echo.
echo   [1] 網頁介面（會自動開瀏覽器，建議）
echo   [2] 一句話 CLI（輸出 TXT）
echo.
set "mode=1"
set /p "mode=選擇模式後按 Enter（預設 1）："

if "%mode%"=="2" goto cli

echo.
echo 啟動網頁介面中...（關閉此視窗即結束服務）
".venv\Scripts\python.exe" server.py
set "ERR=%errorlevel%"
echo.
if not "%ERR%"=="0" (
    echo [ERROR] 伺服器已結束，錯誤代碼：%ERR%
)
pause
exit /b %ERR%

:cli
echo.
set /p "request=請輸入要求："
echo.

if not defined request (
    echo 沒有輸入內容。
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" ptt_tool.py "%request%"
set "ERR=%errorlevel%"

echo.
if not "%ERR%"=="0" (
    echo [ERROR] 執行失敗，錯誤代碼：%ERR%
)
pause
exit /b %ERR%
