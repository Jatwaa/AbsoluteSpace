@echo off
REM AbsoluteSpace one-click launcher (Windows). Double-click this file.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py start.py
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python start.py
    ) else (
        echo Python was not found. Install Python 3.11+ from https://python.org
        echo Make sure to tick "Add Python to PATH" during installation.
        pause
    )
)
