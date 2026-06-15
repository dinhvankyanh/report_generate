@echo off
title Report Generate Agent
cd /d "%~dp0"

REM --- Tim Python ---
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py" )
if not defined PY (
  echo [LOI] Khong tim thay Python 3. Hay cai Python tu https://python.org roi thu lai.
  echo.
  pause
  exit /b 1
)

REM --- Cai dependencies neu thieu (chi chay lan dau) ---
%PY% -c "import flask, pandas, openpyxl, docx, openai" 2>nul
if errorlevel 1 (
  echo Dang cai dependencies lan dau, vui long doi...
  %PY% -m pip install -r requirements.txt
)

echo.
echo ============================================================
echo   Report Generate Agent dang khoi dong...
echo   Trinh duyet se tu mo: http://localhost:5000
echo   (Dong cua so nay de TAT agent)
echo ============================================================
echo.

REM --- Mo trinh duyet sau 3 giay (cho server san sang) ---
start "" cmd /c "timeout /t 3 >nul & start "" http://localhost:5000"

REM --- Chay web server (giu cua so nay mo) ---
%PY% app.py

echo.
echo Agent da dung.
pause
