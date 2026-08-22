@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title PTT Assistant - Diagnostics

echo ==================================================
echo PTT Assistant diagnostics
echo ==================================================
echo.
echo Folder:
echo %CD%
echo.

echo [py]
where py
py -3 --version
echo Return code: %errorlevel%
echo.

echo [python]
where python
python --version
echo Return code: %errorlevel%
echo.

echo [requirements.txt]
if exist requirements.txt (
    echo Found.
    type requirements.txt
) else (
    echo NOT FOUND.
)
echo.

echo [.venv]
if exist ".venv\Scripts\python.exe" (
    echo Found:
    ".venv\Scripts\python.exe" --version
    ".venv\Scripts\python.exe" -m pip --version
) else (
    echo Not created yet.
)
echo.

echo ==================================================
echo Copy or screenshot everything above if you need help.
echo ==================================================
pause
