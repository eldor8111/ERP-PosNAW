"""T1.9 — sales.branch_id (sotuv filiali snapshot) + backfill

1. `sales.branch_id INTEGER NULL REFERENCES branches(id)` + `ix_sales_branch_id`
   va `ix_sale_company_branch_created (company_id, branch_id, created_at)` (CONCURRENTLY).
2. Backfill (faqat `branch_id IS NULL` qatorlar, har bosqichda `branches.company_id = sales.company_id`
   sharti bilan, `id` oralig'i bo'yicha bo'lib):
     a. sotuv ombori filiali (`warehouses.branch_id`, ombor shu korxonaniki);
     b. smena filiali (`shifts.branch_id`);
     c. sotuv income tranzaksiyasi filiali (`transactions`, reference_type='sale');
     d. kassir filiali (`users.branch_id`);
     e. aynan bitta filiali bor korxonalar uchun shu filial.
3. NOT NULL qo'yilmaydi (oflayn sinxron, mobil, order_to_sale yo'llari). Oxirida qolgan NULL soni
   `RAISE NOTICE` bilan chiqariladi.

Eslatma: a-bosqich omborning HOZIRGI filialiga tayanadi — ko'chirilgan omborning eski sotuvlari yangi
filialga yoziladi (hisobotlar tarixni shunday hisoblagan edi); haqiqiy tarixiy filialni tiklab bo'lmaydi.

Revision ID: t1_9
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 't1_9'
down_revision: Union[str, None] = 't1_8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHUNK = 50000

# Har bir backfill bosqichi: (nom, SQL). :lo / :hi — sales.id oralig'i
BACKFILL_STEPS = [
    ("warehouse", """
        UPDATE sales AS s SET branch_id = w.branch_id
        FROM warehouses w JOIN branches b ON b.id = w.branch_id
        WHERE s.id BETWEEN :lo AND :hi AND s.branch_id IS NULL
          AND s.warehouse_id = w.id AND w.branch_id IS NOT NULL
          AND w.company_id = s.company_id AND b.company_id = s.company_id
    """),
    ("shift", """
        UPDATE sales AS s SET branch_id = sh.branch_id
        FROM shifts sh JOIN branches b ON b.id = sh.branch_id
        WHERE s.id BETWEEN :lo AND :hi AND s.branch_id IS NULL
          AND s.shift_id = sh.id AND sh.branch_id IS NOT NULL
          AND b.company_id = s.company_id
    """),
    ("transaction", """
        UPDATE sales AS s SET branch_id = t.branch_id
        FROM (
            SELECT DISTINCT ON (reference_id) reference_id, branch_id
            FROM transactions
            WHERE reference_type = 'sale' AND branch_id IS NOT NULL
              AND reference_id BETWEEN :lo AND :hi
            ORDER BY reference_id, id
        ) t JOIN branches b ON b.id = t.branch_id
        WHERE s.id = t.reference_id AND s.branch_id IS NULL
          AND b.company_id = s.company_id
    """),
    ("cashier", """
        UPDATE sales AS s SET branch_id = u.branch_id
        FROM users u JOIN branches b ON b.id = u.branch_id
        WHERE s.id BETWEEN :lo AND :hi AND s.branch_id IS NULL
          AND s.cashier_id = u.id AND u.branch_id IS NOT NULL
          AND b.company_id = s.company_id
    """),
    ("single_branch_company", """
        UPDATE sales AS s SET branch_id = x.branch_id
        FROM (
            SELECT company_id, MIN(id) AS branch_id
            FROM branches GROUP BY company_id HAVING COUNT(*) = 1
        ) x
        WHERE s.id BETWEEN :lo AND :hi AND s.branch_id IS NULL
          AND s.company_id = x.company_id
    """),
]


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Ustun (idempotent)
    op.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS branch_id INTEGER REFERENCES branches(id)")

    # 2. Backfill — id oralig'i bo'yicha bo'lib
    lo_hi = bind.execute(sa.text("SELECT MIN(id), MAX(id) FROM sales")).fetchone()
    if lo_hi and lo_hi[0] is not None:
        lo = lo_hi[0]
        max_id = lo_hi[1]
        while lo <= max_id:
            hi = lo + CHUNK - 1
            for _name, sql in BACKFILL_STEPS:
                bind.execute(sa.text(sql), {"lo": lo, "hi": hi})
            lo = hi + 1

    # 3. Indekslar — CONCURRENTLY tranzaksiyadan tashqarida
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_sales_branch_id ON sales (branch_id)")
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_sale_company_branch_created "
            "ON sales (company_id, branch_id, created_at)"
        )

    # 4. NOT NULL qo'yilmaydi; qolgan NULL soni xabar sifatida chiqariladi
    op.execute(sa.text("""
        DO $$
        DECLARE n_total integer; n_branch integer;
        BEGIN
            SELECT COUNT(*) INTO n_total FROM sales WHERE branch_id IS NULL;
            SELECT COUNT(*) INTO n_branch FROM sales s
              WHERE s.branch_id IS NULL
                AND EXISTS (SELECT 1 FROM branches b WHERE b.company_id = s.company_id);
            RAISE NOTICE 'T1.9: sales.branch_id IS NULL qolgan: % (shundan filiali bor korxonalarda: %)', n_total, n_branch;
        END $$;
    """))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_sale_company_branch_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_sales_branch_id")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS branch_id")
