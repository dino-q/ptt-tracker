@echo off
chcp 65001 >nul
setlocal
rem Pure ASCII on purpose - CJK in a .bat gets mangled under cp950.
rem The installer file name is 4 CJK chars, so ????.bat matches it and
rem nothing else here (the other bats are 2, 2 and 5 chars long).
set "T="
for %%F in ("%~dp0????.bat") do if /i not "%%~nxF"=="%~nx0" set "T=%%~fF"
if not defined T (
    echo [ERROR] Cannot find the installer bat next to this file.
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
