@echo off
title Hippo CORS Bridge
color 0A
echo.
echo  ============================================
echo   Hippo CORS Bridge - ishga tushmoqda...
echo  ============================================
echo.
cd /d "%~dp0"

:: Python bormi?
python --version >nul 2>&1
if errorlevel 1 (
    echo [XATO] Python topilmadi!
    echo Python yuklab oling: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo  Bridge porti : http://127.0.0.1:8082
echo  Hippo URL    : http://127.0.0.1:8081
echo  To'xtatish   : Bu oynani yoping yoki Ctrl+C bosing
echo.
python hippo_bridge.py
pause
