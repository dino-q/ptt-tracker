@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

title PTT Assistant - Installer
echo ==================================================
echo PTT Assistant installer
echo ==================================================
echo.
echo Current folder:
echo %CD%
echo.

if not exist "requirements.txt" (
    echo [ERROR] requirements.txt was not found.
    echo.
    echo Please extract the whole ZIP file first,
    echo then run this installer from the extracted folder.
    echo.
    pause
    exit /b 1
)

set "PYTHON_CMD="

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 --version >nul 2>&1
    if %errorlevel%==0 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if %errorlevel%==0 (
        python --version >nul 2>&1
        if %errorlevel%==0 set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] Python was not found.
    echo.
    echo Please install Python 3.11 or newer first.
    echo During installation, enable:
    echo     Add python.exe to PATH
    echo.
    echo Then run this installer again.
    echo.
    pause
    exit /b 1
)

echo Python found:
%PYTHON_CMD% --version
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating local virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :venv_error
) else (
    echo [1/3] Existing virtual environment found.
)

echo.
echo [2/3] Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :pip_error

echo.
echo [3/3] Installing required packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :package_error

echo.
echo ==================================================
echo Installation completed successfully.
echo ==================================================
echo.
echo You can now run:
echo     PTT工具.bat
echo or:
echo     週末咖啡飲料優惠.bat
echo.
pause
exit /b 0

:venv_error
echo.
echo [ERROR] Could not create the virtual environment.
echo Error code: %errorlevel%
echo.
pause
exit /b 1

:pip_error
echo.
echo [ERROR] pip could not be updated.
echo Check your network connection and try again.
echo Error code: %errorlevel%
echo.
pause
exit /b 1

:package_error
echo.
echo [ERROR] Package installation failed.
echo The error message is shown above.
echo Error code: %errorlevel%
echo.
pause
exit /b 1
