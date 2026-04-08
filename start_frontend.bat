@echo off
title ERP-POS Frontend (React)
cd /d "%~dp0"
echo =============================================
echo   ERP-POS Frontend ishga tushmoqda...
echo =============================================
echo.

cd frontend

REM node_modules mavjudligini tekshirish
if not exist "node_modules" (
    echo [INFO] node_modules topilmadi. O'rnatilmoqda...
    npm install
)

echo [OK] Frontend tayyor.
echo [INFO] Vite dev server 5173-portda ishga tushmoqda...
echo [INFO] Brauzerda: http://localhost:5173
echo.
npx vite
pause
