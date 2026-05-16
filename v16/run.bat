@echo off
REM Start HYDRA Bot v16.0 on Windows
chcp 65001 > nul

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%\shared;%ROOT%\v16"

echo.
echo ================================
echo HYDRA Trading Bot v16.0
echo ================================
echo.

if not exist venv (
    echo ERROR: Virtual environment not found
    echo Please run setup_windows.bat first
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
cls
echo Activating virtual environment...
echo.
python v16\bot.py

pause
