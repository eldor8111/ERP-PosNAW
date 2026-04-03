from fastapi import FastAPI, Request  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.middleware.gzip import GZipMiddleware  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
from fastapi.responses import JSONResponse  # type: ignore
import asyncio
import os
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler  # type: ignore
from slowapi.errors import RateLimitExceeded  # type: ignore
from app.core.limiter import limiter  # type: ignore

from app.routers import (
    auth, categories, inventory, products, reports, sales, users,
    suppliers, purchase_orders, transfers, inventory_counts,
    finance, customers, shifts, dashboard_mobile, currencies, api_keys,
    warehouses, branches, super_admin, companies, dashboard
)
from app.routers import bin_locations, uploads, agents, telegram  # type: ignore
from app.routers import billing  # type: ignore
from app.models import company  # noqa: F401 — ensure Alembic detects Company model
from app.models import agent  # noqa: F401 — ensure Alembic detects Agent model
from app.models import billing as billing_models  # noqa: F401 — ensure Alembic detects Tariff, BalanceLog

from app.services.scheduler import start_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(start_scheduler())
    yield
    # Clean shutdown: cancel the scheduler so uvicorn doesn't hang on reload
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

_is_dev = os.environ.get("ENV", "production").lower() == "development"

_cors_origins_env = os.environ.get("CORS_ORIGINS", "")
_cors_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else ["*"]  # .env da CORS_ORIGINS ko'rsatilmasa hamma domenga ochiq
)

app = FastAPI(
    title="ERP/POS Tizimi",
    description="Ombor va Savdo Boshqaruv Tizimi",
    version="1.0.0",
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(categories.router, prefix=API_PREFIX)
app.include_router(products.router, prefix=API_PREFIX)
app.include_router(inventory.router, prefix=API_PREFIX)
app.include_router(sales.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(suppliers.router, prefix=API_PREFIX)
app.include_router(purchase_orders.router, prefix=API_PREFIX)
app.include_router(transfers.router, prefix=API_PREFIX)
app.include_router(inventory_counts.router, prefix=API_PREFIX)
app.include_router(finance.router, prefix=API_PREFIX)
app.include_router(customers.router, prefix=API_PREFIX)
app.include_router(shifts.router, prefix=API_PREFIX)
app.include_router(dashboard_mobile.router, prefix=API_PREFIX)
app.include_router(currencies.router, prefix=API_PREFIX)
app.include_router(api_keys.router, prefix=API_PREFIX)
app.include_router(warehouses.router, prefix=API_PREFIX)
app.include_router(branches.router, prefix=API_PREFIX)
app.include_router(companies.router, prefix=API_PREFIX)
app.include_router(super_admin.router, prefix=API_PREFIX)
app.include_router(bin_locations.router, prefix=API_PREFIX)
app.include_router(uploads.router, prefix=API_PREFIX)
app.include_router(agents.router, prefix=API_PREFIX)
app.include_router(telegram.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(billing.router, prefix=API_PREFIX)

# Serve uploaded static files
import os
os.makedirs("static/uploads/products", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", tags=["Root"])
def root():
    return {
        "app": "ERP/POS Tizimi",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health", tags=["Root"])
def health():
    return {"status": "ok"}


@app.get("/api/health", tags=["Root"])
def api_health():
    return {"status": "ok"}
