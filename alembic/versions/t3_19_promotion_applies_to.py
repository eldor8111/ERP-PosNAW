"""T3.19 — promotions.applies_to ('all' | 'products') va customers.price_type tozalash

Mahsulotli aksiyalar 'products', mahsulotsizlari 'all' bo'lib qoladi (hozirgi universal xatti-harakat).
customers.price_type: 'retail' va bo'sh qiymatlar 'sale' ga o'giriladi.

Revision ID: t3_19
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't3_19'
down_revision: Union[str, None] = 't3_18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE promotions ADD COLUMN IF NOT EXISTS applies_to VARCHAR(10) NOT NULL DEFAULT 'all'")
    op.execute(
        "UPDATE promotions SET applies_to = 'products' "
        "WHERE id IN (SELECT DISTINCT promotion_id FROM promotion_products)"
    )
    op.execute("ALTER TABLE promotions DROP CONSTRAINT IF EXISTS ck_promotions_applies_to")
    op.execute(
        "ALTER TABLE promotions ADD CONSTRAINT ck_promotions_applies_to "
        "CHECK (applies_to IN ('all','products')) NOT VALID"
    )
    op.execute(
        "UPDATE customers SET price_type = 'sale' "
        "WHERE price_type IS NULL OR price_type NOT IN ('sale','wholesale','cost')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE promotions DROP CONSTRAINT IF EXISTS ck_promotions_applies_to")
    op.execute("ALTER TABLE promotions DROP COLUMN IF EXISTS applies_to")
