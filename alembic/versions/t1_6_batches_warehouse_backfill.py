"""T1.6 — partiyalar uchun (korxona, ombor, mahsulot, variant) indeksi va xavfsiz warehouse_id to'ldirish

1) Faol partiyalar (quantity > 0) uchun qisman indeks — ombor bo'yicha FIFO/FEFO tanlash.
2) Faqat BITTA faol omborli korxonalarda omborsiz (NULL) partiyalar shu omborga biriktiriladi.
   Ko'p omborli korxonalarda NULL partiyalar tegilmaydi: allocator ularni 2-bosqichda oladi.

Downgrade faqat indeksni olib tashlaydi (ma'lumot qaytarilmaydi).

Revision ID: t1_6
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_6'
down_revision: Union[str, None] = 't1_4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_batch_company_wh_product "
        "ON batches (company_id, warehouse_id, product_id, variant_id) WHERE quantity > 0"
    )
    op.execute(
        "UPDATE batches b SET warehouse_id = w.id "
        "FROM (SELECT company_id, MIN(id) AS id FROM warehouses WHERE is_active "
        "      GROUP BY company_id HAVING COUNT(*) = 1) w "
        "WHERE b.warehouse_id IS NULL AND b.company_id = w.company_id"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_batch_company_wh_product")
