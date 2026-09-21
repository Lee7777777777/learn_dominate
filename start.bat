@echo off
cd /d "%~dp0"
python app.py
if errorlevel 1 (
    echo.
    echo Failed to start. Please install Python 3.10+ with Tcl/Tk and add Python to PATH.
    pause
)
