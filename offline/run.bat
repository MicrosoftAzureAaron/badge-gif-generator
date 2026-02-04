@echo off
REM Badge GIF Generator - Run Script (Windows Batch)
REM Starts the local web server and opens the browser

echo ===============================================
echo Badge GIF Generator - Offline Mode
echo ===============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found! Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

REM Get script directory
set SCRIPT_DIR=%~dp0

REM Create virtual environment if it doesn't exist
if not exist "%SCRIPT_DIR%.venv" (
    echo Creating virtual environment...
    python -m venv "%SCRIPT_DIR%.venv"
    call "%SCRIPT_DIR%.venv\Scripts\activate.bat"
    echo Installing dependencies...
    pip install -r "%SCRIPT_DIR%requirements.txt"
) else (
    call "%SCRIPT_DIR%.venv\Scripts\activate.bat"
)

echo.
echo Starting server on http://localhost:5000
echo Press Ctrl+C to stop the server.
echo.

cd /d "%SCRIPT_DIR%"
python -m src.server

pause
