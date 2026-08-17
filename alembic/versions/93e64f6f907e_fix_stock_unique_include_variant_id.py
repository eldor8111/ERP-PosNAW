"""fix_stock_unique_include_variant_id

Revision ID: 93e64f6f907e
Revises: cc0719a3b1c2
Create Date: 2026-08-17 08:51:21.072406

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '93e64f6f907e'
down_revision: Union[str, None] = 'cc0719a3b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Eski unique constraint (product_id, warehouse_id) ni o'chirish
    # va yangi (product_id, variant_id, warehouse_id) qo'shish
    # Bu variantli mahsulotlar uchun alohida stock yozuvlariga ruxsat beradi
    op.execute("ALTER TABLE stock_levels DROP CONSTRAINT IF EXISTS uq_stock_product_warehouse")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_product_variant_warehouse "
        "ON stock_levels (product_id, warehouse_id, COALESCE(variant_id, 0))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_stock_product_variant_warehouse")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_product_warehouse "
        "ON stock_levels (product_id, warehouse_id) WHERE variant_id IS NULL"
    )
