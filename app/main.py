from fastapi import FastAPI  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.middleware.gzip import GZipMiddleware  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
import asyncio
import os
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler  # type: ignore
from slowapi.errors import RateLimitExceeded  # type: ignore
from app.core.limiter import limiter  # type: ignore

from app.routers import (
    auth, categories, inventory, products, product_search, product_import,
    reports, sales_report, finance_report, sales, users,
    suppliers, purchase_orders, transfers, inventory_counts,
    finance, customers, shifts, dashboard_mobile, currencies, api_keys,
    warehouses, branches, super_admin, companies, dashboard
)
from app.routers import bin_locations, uploads, agents, telegram, lead  # type: ignore
from app.routers import billing  # type: ignore
from app.routers import payme as payme_router  # type: ignore
from app.models import company  # noqa: F401 — ensure Alembic detects Company model
from app.models import agent  # noqa: F401 — ensure Alembic detects Agent model
from app.models import billing as billing_models  # noqa: F401 — ensure Alembic detects Tariff, BalanceLog
from app.models import bot_session  # noqa: F401 — ensure bot_sessions table exists
from app.models import payme_transaction  # noqa: F401 — ensure payme_transactions table exists

from app.services.scheduler import start_scheduler

def _run_alembic_upgrade():
    """Alembic orqali barcha migratsiyalarni bajaradi (alembic upgrade head)."""
    import logging
    _log = logging.getLogger(__name__)
    try:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        _log.info("[MIGRATION] Alembic upgrade head — muvaffaqiyatli")
    except Exception as e:
        _log.error("[MIGRATION] Alembic upgrade xatosi: %s", e)


def _run_auto_migrations(engine):
    """DB da mavjud bo'lmagan ustunlarni avtomatik qo'shadi. Har biri alohida tranzaksiya."""
    migrations = [
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS extra_barcodes TEXT;",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS product_code VARCHAR(100);",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS extra_product_codes TEXT;",
        "CREATE INDEX IF NOT EXISTS ix_products_product_code ON products (product_code);",
        "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(14,2) DEFAULT 0;",
        "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(14,2) DEFAULT 0;",
        "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_type VARCHAR(50);",
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS debt_due_date DATE;",
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS loyalty_points_earned INTEGER DEFAULT 0;",
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS loyalty_points_used INTEGER DEFAULT 0;",
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(14,2) DEFAULT 1;",
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS currency_id INTEGER;",
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(14,2) DEFAULT 0;",
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS paid_cash NUMERIC(14,2) DEFAULT 0;",
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS paid_card NUMERIC(14,2) DEFAULT 0;",
        # ── Payme integratsiya ──
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS payme_merchant_id VARCHAR(50);",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS payme_secret_key VARCHAR(128);",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS payme_is_test BOOLEAN DEFAULT TRUE;",
        """CREATE TABLE IF NOT EXISTS payme_transactions (
            id               SERIAL PRIMARY KEY,
            company_id       INTEGER NOT NULL REFERENCES companies(id),
            payme_id         VARCHAR(25) UNIQUE NOT NULL,
            amount           BIGINT NOT NULL,
            state            INTEGER NOT NULL DEFAULT 1,
            reason           INTEGER,
            create_time      BIGINT,
            perform_time     BIGINT,
            cancel_time      BIGINT,
            account_org_code VARCHAR(20),
            log_id           INTEGER REFERENCES balance_logs(id),
            created_at       TIMESTAMP DEFAULT NOW()
        );""",
        "CREATE INDEX IF NOT EXISTS ix_payme_txn_company ON payme_transactions (company_id);",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_payme_txn_payme_id ON payme_transactions (payme_id);",
        """CREATE TABLE IF NOT EXISTS sale_payments (
            id SERIAL PRIMARY KEY,
            sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
            payment_type VARCHAR(50) NOT NULL,
            amount NUMERIC(14, 2) NOT NULL
        );""",
        """CREATE TABLE IF NOT EXISTS wallet_balances (
            id SERIAL PRIMARY KEY,
            wallet_id INTEGER NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
            payment_type VARCHAR(50) NOT NULL,
            balance NUMERIC(14, 2) DEFAULT 0,
            UNIQUE(wallet_id, payment_type)
        );""",
    ]
    _sa_text = __import__('sqlalchemy').text
    for sql in migrations:
        try:
            with engine.connect() as conn:
                conn.execute(_sa_text(sql))
                conn.commit()
        except Exception as e:
            print(f"[AUTO-MIGRATION] skip: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.routers.auth import run_otp_bot_polling
    from app.database import engine
    from app.models.bot_session import BotSession
    BotSession.__table__.create(bind=engine, checkfirst=True)
    # 1. Alembic migratsiyalar
    _run_alembic_upgrade()
    # 2. Qo'shimcha SQL migratsiyalar (Payme va boshqalar)
    _run_auto_migrations(engine)
    scheduler_task = asyncio.create_task(start_scheduler())
    otp_bot_task = asyncio.create_task(run_otp_bot_polling())
    yield
    # Clean shutdown
    for task in [scheduler_task, otp_bot_task]:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

_is_dev = os.environ.get("ENV", "production").lower() == "development"

_cors_origins_env = os.environ.get("CORS_ORIGINS", "")
if _cors_origins_env:
    _cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "CORS_ORIGINS sozlanmagan — barcha domenga ochiq (*). "
        "Production uchun .env faylida CORS_ORIGINS=https://sizning-domen.uz ni belgilang."
    )
    _cors_origins = ["*"]

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

from starlette.middleware.base import BaseHTTPMiddleware # type: ignore
class ForceHTTPSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Nginx ba'zan HTTPS ni bildirmaydi, shuning uchun manual https qilamiz (agar savdo.e-code.uz bo'lsa)
        host = request.headers.get("host", "").lower()
        if "savdo.e-code.uz" in host or "e-code.uz" in host:
            request.scope["scheme"] = "https"
        return await call_next(request)

app.add_middleware(ForceHTTPSMiddleware)
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
app.include_router(product_search.router, prefix=API_PREFIX)
app.include_router(product_import.router, prefix=API_PREFIX)
app.include_router(products.router, prefix=API_PREFIX)
app.include_router(inventory.router, prefix=API_PREFIX)
app.include_router(sales.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(sales_report.router, prefix=API_PREFIX)
app.include_router(finance_report.router, prefix=API_PREFIX)
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
app.include_router(lead.router, prefix=API_PREFIX)
app.include_router(payme_router.router, prefix=API_PREFIX)

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
