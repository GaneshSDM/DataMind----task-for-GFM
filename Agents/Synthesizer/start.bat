@echo off
setlocal EnableDelayedExpansion
title Universal Synthesizer Agent App

echo.
echo  ============================================================
echo    Universal Synthesizer Agent App  ^|  http://localhost:8000
echo  ============================================================
echo.

:: Move to the backend folder (always relative to this .bat file's location)
cd /d "%~dp0backend"

:: ── Check virtual environment ────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo  [ERROR] Virtual environment not found.
    echo.
    echo  Run this ONE-TIME setup first:
    echo    cd %~dp0backend
    echo    python -m venv venv
    echo    venv\Scripts\activate
    echo    pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

:: ── Activate venv ────────────────────────────────────────────────────────────
echo  [1/4] Activating virtual environment...
call venv\Scripts\activate.bat

:: ── Install / update dependencies ────────────────────────────────────────────
echo  [2/4] Installing dependencies (pip install -r requirements.txt)...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] pip install failed. Check your internet connection or requirements.txt.
    pause
    exit /b 1
)
echo  [2/4] Dependencies ready.
echo.

:: ── Check port 8000 is free ──────────────────────────────────────────────────
netstat -ano | findstr ":8000 " | findstr LISTENING >nul 2>&1
if %errorlevel% == 0 (
    echo.
    echo  [WARN] Port 8000 is already in use.
    echo         The app may already be running — opening browser now.
    start "" "http://localhost:8000"
    goto :end
)

:: ── Open browser after 3-second delay (background) ──────────────────────────
echo  [3/4] Browser will open automatically in 3 seconds...
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"

:: ── Start FastAPI server (foreground — Ctrl+C to stop) ──────────────────────
echo  [4/4] Starting server...
echo.
echo  ┌─────────────────────────────────────────┐
echo  │  App URL  :  http://localhost:8000       │
echo  │  API Docs :  http://localhost:8000/docs  │
echo  │  Press Ctrl+C to stop the server         │
echo  └─────────────────────────────────────────┘
echo.

uvicorn main:app --host 0.0.0.0 --port 8000 --reload

:end
endlocal
