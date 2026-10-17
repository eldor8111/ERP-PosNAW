"""T0.32 — transfer partiyalari jadvali, TRANSFER_OUT/IN harakatlariga ombor yozish,
transfer qatorlari miqdori musbat cheklovi

Revision ID: t0_32
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't0_32'
down_revision: Union[str, None] = 't0_30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ko'chirilgan partiyalar bog'lanishi (manba partiya → manzildagi ko'zgu partiya)
    op.execute("""
        CREATE TABLE IF NOT EXISTS stock_transfer_batches (
            id SERIAL PRIMARY KEY,
            transfer_id INTEGER NOT NULL REFERENCES stock_transfers(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            source_batch_id INTEGER NOT NULL REFERENCES batches(id),
            dest_batch_id INTEGER NOT NULL REFERENCES batches(id),
            quantity NUMERIC(12,3) NOT NULL,
            created_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_stb_transfer_id ON stock_transfer_batches(transfer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_stb_dest_batch_id ON stock_transfer_batches(dest_batch_id)")

    # 2. Tarixiy transfer harakatlariga ombor yozish (idempotent: faqat NULL bo'lganlar).
    #    Tahrirda harakatlar o'chirilib qayta yaratiladi, shuning uchun joriy sarlavha ombori to'g'ri.
    op.execute("""
        UPDATE stock_movements sm SET warehouse_id = st.from_warehouse_id
        FROM stock_transfers st
        WHERE sm.reference_type = 'stock_transfer' AND sm.reference_id = st.id
          AND sm.type = 'TRANSFER_OUT' AND sm.warehouse_id IS NULL
    """)
    op.execute("""
        UPDATE stock_movements sm SET warehouse_id = st.to_warehouse_id
        FROM stock_transfers st
        WHERE sm.reference_type = 'stock_transfer' AND sm.reference_id = st.id
          AND sm.type = 'TRANSFER_IN' AND sm.warehouse_id IS NULL
    """)

    # 3. Transfer qatori miqdori musbat (NOT VALID — eski qatorlar tekshirilmaydi;
    #    buzilgan qator bo'lmasa alohida VALIDATE qilinadi)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_stock_transfer_items_qty_pos'
            ) THEN
                ALTER TABLE stock_transfer_items
                    ADD CONSTRAINT ck_stock_transfer_items_qty_pos CHECK (quantity > 0) NOT VALID;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM stock_transfer_items WHERE quantity <= 0) THEN
                ALTER TABLE stock_transfer_items VALIDATE CONSTRAINT ck_stock_transfer_items_qty_pos;
            ELSE
                RAISE NOTICE 'stock_transfer_items: quantity <= 0 qatorlar bor — cheklov NOT VALID holda qoldi';
            END IF;
        END $$;
    """)

    # 4. Diagnostika (o'zgartirmaydi): partiya yig'indisi qoldiqdan katta bo'lgan
    #    (product, variant, warehouse) — eski transferlar partiyasiz ko'chirilgan.
    #    Tuzatish qo'lda yoki inventarizatsiya orqali:
    #    SELECT b.product_id, b.variant_id, b.warehouse_id, SUM(b.quantity) AS batch_qty, sl.quantity AS stock_qty
    #    FROM batches b JOIN stock_levels sl ON sl.product_id = b.product_id
    #      AND sl.warehouse_id = b.warehouse_id AND COALESCE(sl.variant_id, 0) = COALESCE(b.variant_id, 0)
    #    WHERE b.quantity > 0 GROUP BY b.product_id, b.variant_id, b.warehouse_id, sl.quantity
    #    HAVING SUM(b.quantity) > sl.quantity;


def downgrade() -> None:
    op.execute("ALTER TABLE stock_transfer_items DROP CONSTRAINT IF EXISTS ck_stock_transfer_items_qty_pos")
    op.execute("DROP TABLE IF EXISTS stock_transfer_batches")
