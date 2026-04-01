from fastapi import FastAPI  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
import asyncio

from app.routers import (
    auth, categories, inventory, products, reports, sales, users,
    suppliers, purchase_orders, transfers, inventory_counts,
    finance, customers, shifts, dashboard_mobile, currencies, api_keys,
    warehouses, branches, super_admin, companies
)
from app.routers import bin_locations, uploads, agents, telegram  # type: ignore
from app.models import company  # noqa: F401 — ensure Alembic detects Company model
from app.models import agent  # noqa: F401 — ensure Alembic detects Agent model

app = FastAPI(
    title="ERP/POS Tizimi",
    description="Ombor va Savdo Boshqaruv Tizimi — MVP 1-Bosqich",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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

# Serve uploaded static files
import os
os.makedirs("static/uploads/products", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

from app.services.scheduler import start_scheduler

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_scheduler())

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
