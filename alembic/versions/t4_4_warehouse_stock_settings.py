"""T4.4 — ombor bo'yicha min/max qoldiq (warehouse_stock_settings)

Har bir (ombor, mahsulot) juftligi uchun alohida min/max/reorder chegarasi va to'ldirish manbai.
Qator yo'q bo'lsa Product.min_stock / max_stock ishlatiladi, shuning uchun mavjud hisobotlar o'zgarmaydi
(ma'lumotni ko'chirish kerak emas).

Revision ID: t4_4
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't4_4'
down_revision: Union[str, None] = 't4_3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS warehouse_stock_settings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            min_qty NUMERIC(12,3),
            max_qty NUMERIC(12,3),
            reorder_qty NUMERIC(12,3),
            source_warehouse_id INTEGER REFERENCES warehouses(id),
            updated_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT uq_wss_warehouse_product UNIQUE (warehouse_id, product_id),
            CONSTRAINT ck_wss_min_nonneg CHECK (min_qty IS NULL OR min_qty >= 0),
            CONSTRAINT ck_wss_max_nonneg CHECK (max_qty IS NULL OR max_qty >= 0),
            CONSTRAINT ck_wss_reorder_nonneg CHECK (reorder_qty IS NULL OR reorder_qty >= 0),
            CONSTRAINT ck_wss_max_ge_min CHECK (min_qty IS NULL OR max_qty IS NULL OR max_qty >= min_qty),
            CONSTRAINT ck_wss_source_not_self CHECK (source_warehouse_id IS NULL OR source_warehouse_id <> warehouse_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_warehouse_stock_settings_id ON warehouse_stock_settings(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_warehouse_stock_settings_company_id ON warehouse_stock_settings(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wss_product ON warehouse_stock_settings(product_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS warehouse_stock_settings")
