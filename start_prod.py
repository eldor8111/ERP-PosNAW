"""
ERPPos — PRODUCTION ishga tushirish skripti.
reload=False, workers=4, log_level=warning

Yoki Linux serverda Gunicorn bilan:
    gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=4,
        log_level="warning",
        access_log=False,
    )
