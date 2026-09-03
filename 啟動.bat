@echo off
chcp 65001 >nul
setlocal
rem Pure ASCII on purpose - see the tool bat header.
rem Resolves the PTT tool bat via a wildcard so no CJK filename appears in this file.
set "T="
for %%F in ("%~dp0PTT*.bat") do set "T=%%~fF"
if not defined T (
    echo [ERROR] Cannot find the PTT tool bat next to this file.
    echo   Looked in: %~dp0
    echo.
    pause
    exit /b 1
)
call "%T%"
set "ERR=%errorlevel%"
if not "%ERR%"=="0" (
    echo.
    echo [ERROR] exit code %ERR%
    pause
)
exit /b %ERR%
