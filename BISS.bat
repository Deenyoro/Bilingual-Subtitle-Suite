@echo off
cd /d "%~dp0"

echo Starting BISS GUI...
echo Log file: %~dp0biss_gui.log
echo.

:: Set log level (DEBUG, INFO, WARNING, ERROR)
set BISS_LOG_LEVEL=INFO

python biss.py gui

if errorlevel 1 (
    echo.
    echo GUI exited with an error. Check biss_gui.log for details.
    pause
)
