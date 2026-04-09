@echo off
title ERP-POS Backend Server
cd /d "%~dp0"
echo =============================================
echo   ERP-POS Backend serveri ishga tushmoqda...
echo =============================================
echo.

REM Virtual environment mavjudligini tekshirish
if not exist "venv\Scripts\python.exe" (
    echo [XATO] venv topilmadi! Yaratilmoqda...
    python -m venv venv
    echo [OK] venv yaratildi.
)

echo [OK] Virtual environment topildi.
call venv\Scripts\activate.bat

echo [OK] Virtual environment faollashtirildi.
echo [INFO] Backend server 8000-portda ishga tushmoqda...
echo [INFO] Brauzerda: http://localhost:8000/docs
echo.
python start.py
pause
