"""add currency columns to purchase_orders and po_items

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-07-25

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'q2r3s4t5u6v7'
down_revision: Union[str, None] = 'p1q2r3s4t5u6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add currency column to purchase_orders table
    op.execute("ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'UZS'")

    # Add original_unit_cost and cost_currency columns to po_items table
    op.execute("ALTER TABLE po_items ADD COLUMN IF NOT EXISTS original_unit_cost NUMERIC(12, 4)")
    op.execute("ALTER TABLE po_items ADD COLUMN IF NOT EXISTS cost_currency VARCHAR(3) DEFAULT 'UZS'")

    # Backfill cost_currency from product's cost_currency where available
    op.execute("""
        UPDATE po_items pi
        SET cost_currency = COALESCE(p.cost_currency, 'UZS'),
            original_unit_cost = pi.unit_cost
        FROM products p
        WHERE pi.product_id = p.id
          AND pi.cost_currency IS NULL
    """)

    # Backfill purchase_orders.currency from its items
    op.execute("""
        UPDATE purchase_orders po
        SET currency = COALESCE((
            SELECT pi.cost_currency
            FROM po_items pi
            WHERE pi.po_id = po.id
              AND pi.cost_currency IS NOT NULL
              AND pi.cost_currency != 'UZS'
            LIMIT 1
        ), 'UZS')
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE purchase_orders DROP COLUMN IF EXISTS currency")
    op.execute("ALTER TABLE po_items DROP COLUMN IF EXISTS original_unit_cost")
    op.execute("ALTER TABLE po_items DROP COLUMN IF EXISTS cost_currency")
