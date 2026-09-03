@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PTT Assistant
rem ------------------------------------------------------------------
rem  KEEP THIS FILE PURE ASCII.
rem  cmd.exe parses .bat with the OEM code page (cp950 on this machine).
rem  UTF-8 CJK bytes get mis-paired as DBCS and swallow the line break,
rem  which eats the next command. The original Chinese menu lost 13+
rem  lines that way and made the launcher close instantly (2026-09-04).
rem  All Chinese UI now lives in scripts/launcher.py instead.
rem ------------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] PTT Assistant has not been installed yet.
    echo Please run the installer bat first.
    echo.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\launcher.py
set "ERR=%errorlevel%"
echo.
pause
exit /b %ERR%
