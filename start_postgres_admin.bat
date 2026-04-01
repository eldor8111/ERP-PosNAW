@echo off
echo PostgreSQL servisini ishga tushirish...
net start postgresql-x64-17
if %errorlevel% == 0 (
    echo PostgreSQL muvaffaqiyatli ishga tushdi!
) else (
    echo Xato yuz berdi. Administrator sifatida ishga tushiring.
)
pause
