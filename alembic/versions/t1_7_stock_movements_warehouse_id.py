"""T1.7 — stock_movements.warehouse_id ustuni, indekslar va tarixiy harakatlarga ombor to'ldirish (backfill)

Revision ID: t1_7
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_7'
down_revision: Union[str, None] = 't1_6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Katta jadvalda UPDATE lar id oralig'i bo'yicha bo'lib bajariladi
BATCH_SIZE = 50000


def _batched_update(set_expr: str, where_expr: str) -> None:
    """`UPDATE stock_movements m SET warehouse_id = <set_expr> WHERE <where_expr>` ni
    id oralig'i bo'yicha (BATCH_SIZE) bo'lib bajaradi. Faqat warehouse_id IS NULL qatorlar."""
    op.execute(f"""
        DO $$
        DECLARE
            min_id INTEGER;
            max_id INTEGER;
            cur_id INTEGER;
        BEGIN
            SELECT MIN(id), MAX(id) INTO min_id, max_id FROM stock_movements WHERE warehouse_id IS NULL;
            IF min_id IS NULL THEN
                RETURN;
            END IF;
            cur_id := min_id;
            WHILE cur_id <= max_id LOOP
                UPDATE stock_movements m
                SET warehouse_id = {set_expr}
                WHERE m.warehouse_id IS NULL
                  AND m.id >= cur_id AND m.id < cur_id + {BATCH_SIZE}
                  AND ({where_expr});
                cur_id := cur_id + {BATCH_SIZE};
            END LOOP;
        END $$;
    """)


def upgrade() -> None:
    # 1. Ustun (prod'da qo'lda qo'shilgan bo'lishi mumkin — IF NOT EXISTS)
    op.execute("ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(id)")

    # 2. Indekslar (idempotent)
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_movements_warehouse_id ON stock_movements(warehouse_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_movements_wh_created ON stock_movements(warehouse_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_movements_reftype_refid ON stock_movements(reference_type, reference_id)")

    # 3. Backfill — faqat warehouse_id IS NULL qatorlar, shu tartibda
    # 3.1 Sotuv: avval qator ombori (sale_items.warehouse_id), bo'lmasa sarlavha ombori (sales.warehouse_id)
    _batched_update(
        """COALESCE(
            (SELECT si.warehouse_id FROM sale_items si
              WHERE si.sale_id = m.reference_id AND si.product_id = m.product_id
                AND si.warehouse_id IS NOT NULL LIMIT 1),
            (SELECT s.warehouse_id FROM sales s WHERE s.id = m.reference_id)
        )""",
        "m.reference_type = 'sale'",
    )
    # 3.2 Transfer: TRANSFER_OUT -> from_warehouse_id, TRANSFER_IN -> to_warehouse_id
    _batched_update(
        "(SELECT st.from_warehouse_id FROM stock_transfers st WHERE st.id = m.reference_id)",
        "m.reference_type = 'stock_transfer' AND m.type = 'TRANSFER_OUT'",
    )
    _batched_update(
        "(SELECT st.to_warehouse_id FROM stock_transfers st WHERE st.id = m.reference_id)",
        "m.reference_type = 'stock_transfer' AND m.type = 'TRANSFER_IN'",
    )
    # 3.3 Revizya
    _batched_update(
        "(SELECT ic.warehouse_id FROM inventory_counts ic WHERE ic.id = m.reference_id)",
        "m.reference_type = 'revision'",
    )
    # 3.4 Muddati o'tgan partiyani hisobdan chiqarish (reference_id = batches.id)
    _batched_update(
        "(SELECT b.warehouse_id FROM batches b WHERE b.id = m.reference_id)",
        "m.reference_type IN ('auto_batch_write_off', 'batch_write_off')",
    )
    # 3.5 Sababdagi "Ombor #N" (deduct_stock yozadi) — faqat mavjud ombor bo'lsa
    _batched_update(
        """(SELECT w.id FROM warehouses w
             WHERE w.id = substring(m.reason from 'Ombor #([0-9]+)')::int)""",
        "m.reason ~ 'Ombor #[0-9]+'",
    )
    # 3.6 Qolgan (reference'siz qo'lda ADJUST) harakatlar aniqlanmaydi — NULL qoladi
    op.execute("""
        DO $$
        DECLARE
            remaining INTEGER;
        BEGIN
            SELECT count(*) INTO remaining FROM stock_movements WHERE warehouse_id IS NULL;
            RAISE NOTICE 'stock_movements: ombori aniqlanmagan (NULL) harakatlar soni: %', remaining;
        END $$;
    """)


def downgrade() -> None:
    # Ustun o'chirilmaydi (prod'da avvaldan bo'lishi mumkin) — faqat indekslar
    op.execute("DROP INDEX IF EXISTS ix_stock_movements_reftype_refid")
    op.execute("DROP INDEX IF EXISTS ix_stock_movements_wh_created")
    op.execute("DROP INDEX IF EXISTS ix_stock_movements_warehouse_id")
