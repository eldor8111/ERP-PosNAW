"""T1.7 (2-qism) — stock_levels: NULL-omborli "egasiz" qoldiq qatorlarini xavfsiz tozalash

Revision ID: t1_7b
Revises: t1_7

Faqat xavfsiz holatlar:
- quantity = 0 bo'lgan NULL qatorlar o'chiriladi;
- korxonada aynan bitta faol ombor bo'lsa NULL qator shu omborga ko'chiriladi
  (mavjud qatorga qo'shiladi yoki warehouse_id o'rnatiladi).
Ko'p omborli korxonalardagi nolga teng bo'lmagan NULL qatorlar TEGILMAYDI —
ular egasi tasdiqlagan omborga qo'lda ko'chiriladi (scripts/fix_null_warehouse_stock.py).
NOT NULL / CHECK cheklovi bu yerda qo'shilmaydi (faqat NULL soni 0 bo'lgandan keyin, alohida reliz).
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_7b'
down_revision: Union[str, None] = 't1_7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Nol qoldiqli NULL qatorlar (stock_levels.id ga FK yo'q — xavfsiz)
    op.execute("DELETE FROM stock_levels WHERE warehouse_id IS NULL AND COALESCE(quantity, 0) = 0")

    # 2. Yagona faol omborli korxonalar: NULL qator miqdori mavjud (product, variant, ombor)
    #    qatoriga qo'shiladi va NULL qator o'chiriladi; mos qator bo'lmasa warehouse_id o'rnatiladi.
    op.execute("""
        DO $$
        DECLARE
            moved INTEGER := 0;
            merged INTEGER := 0;
        BEGIN
            CREATE TEMP TABLE _t17_single_wh ON COMMIT DROP AS
                SELECT w.company_id, MIN(w.id) AS warehouse_id
                FROM warehouses w
                WHERE w.is_active = true
                GROUP BY w.company_id
                HAVING count(*) = 1;

            -- 2a. Mavjud (product, variant, ombor) qatoriga qo'shish. NULL qatorlar takrorlanishi
            --     mumkin (unikal indeks NULL omborni ushlamaydi) — avval guruhlab yig'iladi.
            WITH src AS (
                SELECT sl.product_id, COALESCE(sl.variant_id, 0) AS vkey, s.warehouse_id,
                       SUM(COALESCE(sl.quantity, 0)) AS qty, array_agg(sl.id) AS null_ids
                FROM stock_levels sl
                JOIN products p ON p.id = sl.product_id
                JOIN _t17_single_wh s ON s.company_id = p.company_id
                WHERE sl.warehouse_id IS NULL
                GROUP BY sl.product_id, COALESCE(sl.variant_id, 0), s.warehouse_id
            ),
            upd AS (
                UPDATE stock_levels dst
                SET quantity = COALESCE(dst.quantity, 0) + src.qty,
                    updated_at = now()
                FROM src
                WHERE dst.product_id = src.product_id
                  AND dst.warehouse_id = src.warehouse_id
                  AND COALESCE(dst.variant_id, 0) = src.vkey
                RETURNING src.null_ids
            )
            DELETE FROM stock_levels WHERE id IN (SELECT unnest(null_ids) FROM upd);
            GET DIAGNOSTICS merged = ROW_COUNT;

            -- 2b-i. Qolgan NULL qatorlar orasidagi takrorlar (bir mahsulot/variant) bitta qatorga yig'iladi,
            --       aks holda ombor o'rnatilganda unikal indeks buziladi
            WITH grp AS (
                SELECT MIN(sl.id) AS keep_id, SUM(COALESCE(sl.quantity, 0)) AS qty, array_agg(sl.id) AS ids
                FROM stock_levels sl
                JOIN products p ON p.id = sl.product_id
                JOIN _t17_single_wh s ON s.company_id = p.company_id
                WHERE sl.warehouse_id IS NULL
                GROUP BY sl.product_id, COALESCE(sl.variant_id, 0)
                HAVING count(*) > 1
            ),
            kept AS (
                UPDATE stock_levels k
                SET quantity = grp.qty, updated_at = now()
                FROM grp
                WHERE k.id = grp.keep_id
                RETURNING grp.ids, grp.keep_id
            )
            DELETE FROM stock_levels
            WHERE id IN (SELECT unnest(ids) FROM kept)
              AND id NOT IN (SELECT keep_id FROM kept);

            -- 2b-ii. Mos qator yo'q — ombor o'rnatiladi
            UPDATE stock_levels sl
            SET warehouse_id = s.warehouse_id, updated_at = now()
            FROM products p, _t17_single_wh s
            WHERE sl.warehouse_id IS NULL
              AND p.id = sl.product_id AND s.company_id = p.company_id;
            GET DIAGNOSTICS moved = ROW_COUNT;

            RAISE NOTICE 'stock_levels NULL-ombor tozalash: qo''shildi=%, ko''chirildi=%', merged, moved;
            RAISE NOTICE 'stock_levels: qolgan NULL-omborli qatorlar (ko''p omborli korxonalar, qo''lda): %',
                (SELECT count(*) FROM stock_levels WHERE warehouse_id IS NULL);
        END $$;
    """)


def downgrade() -> None:
    # Ma'lumot tozalash — orqaga qaytarilmaydi
    pass
