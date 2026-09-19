"""restore indexes dropped by df9132535f4b (customers.company_id, sales.customer_id/warehouse_id/cashier_id)

Revision ID: d8e2f4a6b1c3
Revises: c6279a91afa2
Create Date: 2026-09-20 01:20:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd8e2f4a6b1c3'
down_revision = 'c6279a91afa2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # df9132535f4b migratsiyasi bu indekslarni customers/sales jadvallaridan
    # o'chirib, faqat composite (company_id, created_at)/(company_id, status)
    # indekslar bilan almashtirgan edi. Lekin kod bazasida customer_id,
    # warehouse_id, cashier_id hali ham (company_id'siz) alohida filtrlanadi
    # (masalan mijoz profilidagi sotuv tarixi, kassir bo'yicha smena hisoboti,
    # filial bo'yicha hisobotlar) — composite indekslar bu so'rovlarga yordam
    # bermaydi, natijada sequential scan bo'ladi.
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_company_id ON customers (company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sales_customer_id ON sales (customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sales_warehouse_id ON sales (warehouse_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sales_cashier_id ON sales (cashier_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sales_cashier_id")
    op.execute("DROP INDEX IF EXISTS ix_sales_warehouse_id")
    op.execute("DROP INDEX IF EXISTS ix_sales_customer_id")
    op.execute("DROP INDEX IF EXISTS ix_customers_company_id")
