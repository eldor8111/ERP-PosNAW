"""
ERPPos backend ishga tushirish skripti.
Faqat app/ papkasini kuzatadi — test fayllar, skriptlar reload qilmaydi.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8010,
        reload=True,
        reload_dirs=["app"],          # faqat app/ papkasini kuzat
        reload_excludes=[             # bularni hech qachon kuzatma
            "*.pyc", "__pycache__",
            "venv/*", "alembic/*",
            "static/*", "tmp/*",
            "test_*.py", "check_*.py",
            "set_superadmin.py", "auto_tunnel.py",
            "kill_8000.py", "add_column.py",
        ],
        log_level="info",
        access_log=True,
    )
