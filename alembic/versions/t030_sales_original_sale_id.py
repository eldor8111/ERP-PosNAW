"""T0.30 — qaytarish hujjatiga asl sotuv havolasi (sales.original_sale_id),
kassa harakatlari uchun havola indeksi

1. `sales.original_sale_id INTEGER NULL REFERENCES sales(id)` + `ix_sales_original_sale_id`.
2. Backfill: faqat qisman qaytarish hujjatlari (`R...`, izohi
   "Qisman qaytarish (Sotuv #<raqam>)") shu korxonadagi asl sotuvga bog'lanadi.
   To'liq qaytarish ("Vazvrat: ...") hujjatlari asl sotuvga bog'lanmagan — NULL qoladi.
3. `kassa_movements` uchun `ix_kassa_movements_ref (company_id, reference_type, reference_id)`
   — teskari qilish so'rovlari shu bo'yicha (CONCURRENTLY, jadval qulflanmaydi).
`stock_movements.warehouse_id` NULL qatorlari bu yerda to'ldirilmaydi (T1.7);
teskari qilish kodi `SaleItem.warehouse_id` zaxirasi bilan eski yozuvlarda ham ishlaydi.

Revision ID: t0_30
Revises: t028
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't0_30'
down_revision: Union[str, None] = 't028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ustun va indeks (idempotent)
    op.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS original_sale_id INTEGER NULL REFERENCES sales(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sales_original_sale_id ON sales(original_sale_id)")

    # 2. Backfill — faqat qisman qaytarish hujjatlari, izoh matnidagi raqam bo'yicha
    op.execute("""
        UPDATE sales r SET original_sale_id = o.id FROM sales o
        WHERE r.number LIKE 'R%' AND r.original_sale_id IS NULL AND r.company_id = o.company_id
          AND r.note LIKE 'Qisman qaytarish (Sotuv #%)'
          AND o.number = substring(r.note from 'Sotuv #([^)]+)')
    """)

    # 3. Kassa harakatlari havola indeksi — CONCURRENTLY tranzaksiyadan tashqarida
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_kassa_movements_ref "
            "ON kassa_movements (company_id, reference_type, reference_id)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_kassa_movements_ref")
    op.execute("DROP INDEX IF EXISTS ix_sales_original_sale_id")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS original_sale_id")
