@echo off
setlocal EnableExtensions
title CarbonAI - Carbon Emissions Management System

REM ============================================================
REM  CarbonAI startup script
REM  - Backend:  FastAPI (uvicorn) on http://127.0.0.1:8000
REM  - Frontend: built React app served by the backend at "/"
REM  - Database: data\carbonai.db (created/migrated automatically)
REM
REM  First run creates the default admin user:
REM      username: admin
REM      password: admin123   (you MUST change it after first login,
REM                            or set CARBONAI_ADMIN_PASSWORD before starting)
REM ============================================================

cd /d "%~dp0"
set "PORT=8000"

echo.
echo  ============================================================
echo    CarbonAI - Carbon Emissions Management System
echo  ============================================================
echo.

REM ---------- 1. Locate Python -------------------------------
set "PY="
   where py >nul 2>nul && set "PY=py -3.12"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python 3 was not found on PATH.
    echo         Install Python 3.11+ from https://www.python.org/downloads/
    goto :fail
)
echo [1/5] Python found: %PY%

REM ---------- 2. Check backend dependencies ------------------
%PY% -c "import fastapi, uvicorn, jose, pandas, reportlab, pdfplumber, sklearn" >nul 2>nul
if errorlevel 1 (
    echo [2/5] Installing backend dependencies ^(first run only^)...
    %PY% -m pip install --quiet "fastapi>=0.115" "uvicorn[standard]>=0.30" "python-jose[cryptography]>=3.3" "pandas>=2.2" "openpyxl>=3.1" "reportlab>=4.0" "pdfplumber>=0.11" "scikit-learn>=1.4" "numpy>=1.26" "arabic-reshaper>=3.0" "python-bidi>=0.4.2" "python-dotenv>=1.0" || goto :fail
) else (
    echo [2/5] Backend dependencies OK
)

REM ---------- 3. Build the React frontend ----------
REM Always rebuild when npm is available: a `git pull` updates the sources but NOT frontend\dist
REM (build artifacts are git-ignored), and a stale dist would hide the update.
where npm >nul 2>nul
if errorlevel 1 (
    if exist "frontend\dist\index.html" (
        echo [3/5] npm not found - using the existing frontend build
    ) else (
        echo [ERROR] Frontend build missing and npm is not installed.
        echo         Install Node.js 18+ from https://nodejs.org
        goto :fail
    )
) else (
    echo [3/5] Building the React frontend...
    pushd frontend
    if not exist node_modules call npm install --no-audit --no-fund || (popd & goto :fail)
    call npm run build
    if errorlevel 1 (
        popd
        if exist "frontend\dist\index.html" (
            echo [WARN] Frontend build failed - continuing with the existing build.
        ) else (
            goto :fail
        )
    ) else (
        popd
    )
)

REM ---------- 4. Optional environment ------------------------
if defined CARBONAI_ADMIN_PASSWORD (
    echo [4/5] Admin password: from CARBONAI_ADMIN_PASSWORD
) else (
    echo [4/5] Admin password: default 'admin123' ^(change it after first login^)
)

REM ---------- 5. Start the server ----------------------------
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [ERROR] Port %PORT% is already in use - CarbonAI may already be running.
    echo         Close the other instance ^(or open http://127.0.0.1:%PORT% in your browser^).
    goto :fail
)
echo [5/5] Starting CarbonAI on http://127.0.0.1:%PORT% ...
echo       Press Ctrl+C to stop.
echo.
start "" http://127.0.0.1:%PORT%
%PY% -m uvicorn api.main:app --host 127.0.0.1 --port %PORT%
goto :eof

:fail
echo.
echo [FAILED] CarbonAI could not start. Read the messages above.
pause
exit /b 1
