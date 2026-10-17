"""T4.1 — ikki bosqichli filiallararo transfer (yuborildi → yo'lda → qabul qilindi)

stock_transfers: sent_by, sent_at, cancel_reason + status/ombor indekslari;
stock_transfer_items: qty_sent, qty_received, discrepancy_reason;
stock_transfer_batches: dest_batch_id NULL bo'lishi mumkin (yo'lda/kamomad qismi) + item_id.
Eski ma'lumot: qty_sent = quantity, received transferlarda qty_received = quantity, sent_by/sent_at to'ldiriladi.

Revision ID: t4_1
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't4_1'
down_revision: Union[str, None] = 't3_19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. stock_transfers
    op.execute("ALTER TABLE stock_transfers ADD COLUMN IF NOT EXISTS sent_by INTEGER REFERENCES users(id)")
    op.execute("ALTER TABLE stock_transfers ADD COLUMN IF NOT EXISTS sent_at TIMESTAMP")
    op.execute("ALTER TABLE stock_transfers ADD COLUMN IF NOT EXISTS cancel_reason TEXT")

    # 2. stock_transfer_items
    op.execute("ALTER TABLE stock_transfer_items ADD COLUMN IF NOT EXISTS qty_sent NUMERIC(12,3)")
    op.execute("ALTER TABLE stock_transfer_items ADD COLUMN IF NOT EXISTS qty_received NUMERIC(12,3)")
    op.execute("ALTER TABLE stock_transfer_items ADD COLUMN IF NOT EXISTS discrepancy_reason VARCHAR(200)")

    # 3. stock_transfer_batches: yo'ldagi/kamomad qismi uchun manzil partiya yo'q; qator bog'lanishi
    op.execute("ALTER TABLE stock_transfer_batches ALTER COLUMN dest_batch_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE stock_transfer_batches ADD COLUMN IF NOT EXISTS item_id INTEGER "
        "REFERENCES stock_transfer_items(id) ON DELETE SET NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_transfer_batches_item_id ON stock_transfer_batches(item_id)")

    # 4. Indekslar (ombor indekslari T1.13 da yaratilgan — IF NOT EXISTS)
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_transfers_status ON stock_transfers(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_transfers_from_wh ON stock_transfers(from_warehouse_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_transfers_to_wh ON stock_transfers(to_warehouse_id)")

    # 5. Mavjud ma'lumotni ko'chirish (idempotent: faqat hali to'ldirilmagan qatorlar)
    op.execute("""
        UPDATE stock_transfer_items i
        SET qty_sent = i.quantity,
            qty_received = CASE WHEN t.status = 'received' THEN i.quantity END
        FROM stock_transfers t
        WHERE t.id = i.transfer_id AND i.qty_sent IS NULL
    """)
    # Eski hujjatlar bir bosqichli: yuborish vaqti = qabul vaqti (ilova shu bo'yicha ularni bir bosqichli deb biladi)
    op.execute("""
        UPDATE stock_transfers
        SET sent_by = created_by, sent_at = confirmed_at
        WHERE status = 'received' AND sent_by IS NULL
    """)
    # Tekshiruv (o'zgartirmaydi): eski create_transfer doim 'received' bilan tugagan, shuning uchun 0 kutiladi
    #   SELECT count(*) FROM stock_transfers WHERE status = 'pending';


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_stock_transfers_status")
    op.execute("DROP INDEX IF EXISTS ix_stock_transfer_batches_item_id")
    op.execute("ALTER TABLE stock_transfer_batches DROP COLUMN IF EXISTS item_id")
    # dest_batch_id NOT NULL ni faqat NULL qatorlar bo'lmasa qaytaramiz (ma'lumotni yo'qotmaslik uchun)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM stock_transfer_batches WHERE dest_batch_id IS NULL) THEN
                ALTER TABLE stock_transfer_batches ALTER COLUMN dest_batch_id SET NOT NULL;
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE stock_transfer_items DROP COLUMN IF EXISTS discrepancy_reason")
    op.execute("ALTER TABLE stock_transfer_items DROP COLUMN IF EXISTS qty_received")
    op.execute("ALTER TABLE stock_transfer_items DROP COLUMN IF EXISTS qty_sent")
    op.execute("ALTER TABLE stock_transfers DROP COLUMN IF EXISTS cancel_reason")
    op.execute("ALTER TABLE stock_transfers DROP COLUMN IF EXISTS sent_at")
    op.execute("ALTER TABLE stock_transfers DROP COLUMN IF EXISTS sent_by")
