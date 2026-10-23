"""Dorixona kirimi (D1.3): yuk xati, seriya/ishlab chiqarilgan sana, kategoriya ustamasi

Additiv: faqat nullable ustunlar; oddiy do'konlar uchun hech narsa o'zgarmaydi.

Revision ID: d1_3
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd1_3'
down_revision: Union[str, Sequence[str], None] = 't6_01_pharmacy_module'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS supplier_invoice_number VARCHAR(100)")
    op.execute("ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS supplier_invoice_date DATE")
    op.execute("ALTER TABLE po_items ADD COLUMN IF NOT EXISTS lot_number VARCHAR(100)")
    op.execute("ALTER TABLE po_items ADD COLUMN IF NOT EXISTS manufacture_date TIMESTAMP")
    op.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS markup_pct NUMERIC(6, 2)")


def downgrade() -> None:
    op.execute("ALTER TABLE categories DROP COLUMN IF EXISTS markup_pct")
    op.execute("ALTER TABLE po_items DROP COLUMN IF EXISTS manufacture_date")
    op.execute("ALTER TABLE po_items DROP COLUMN IF EXISTS lot_number")
    op.execute("ALTER TABLE purchase_orders DROP COLUMN IF EXISTS supplier_invoice_date")
    op.execute("ALTER TABLE purchase_orders DROP COLUMN IF EXISTS supplier_invoice_number")
