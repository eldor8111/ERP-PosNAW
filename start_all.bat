@echo off
title ERP-POS Tizimi
cd /d "%~dp0"
echo =============================================
echo        ERP-POS TIZIMI ISHGA TUSHMOQDA
echo =============================================
echo.
echo [1] Backend server yangi oynada ochilmoqda...
start "ERP-POS Backend" cmd /k "call start_backend.bat"

echo [2] 3 soniya kutilmoqda (backend yuklanishi uchun)...
timeout /t 3 /nobreak >nul

echo [3] Frontend server yangi oynada ochilmoqda...
start "ERP-POS Frontend" cmd /k "call start_frontend.bat"

echo.
echo =============================================
echo   Ikkala server ham ishga tushirildi!
echo   Backend:  http://localhost:8010
echo   Frontend: http://localhost:5173
echo   API docs: http://localhost:8010/docs
echo =============================================
echo.
pause
