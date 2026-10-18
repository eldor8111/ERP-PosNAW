"""T1.4 — warehouses.is_default, branches.is_main va ombor-filial backfill

Revision ID: t1_4
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_4'
down_revision: Union[str, None] = 't1_2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE branches ADD COLUMN IF NOT EXISTS is_main BOOLEAN NOT NULL DEFAULT false")

    # 1. Bir faol filialli korxonalarda filialsiz omborlarni shu filialga biriktirish (MODEL-09).
    #    2+ filialli korxonalarda tegilmaydi (qo'lda hisobot:
    #    SELECT id, name, company_id FROM warehouses WHERE branch_id IS NULL AND is_active)
    op.execute("""
        UPDATE warehouses w SET branch_id = b.id
        FROM (
            SELECT company_id, MIN(id) AS id FROM branches WHERE is_active
            GROUP BY company_id HAVING COUNT(*) = 1
        ) b
        WHERE w.branch_id IS NULL AND w.company_id = b.company_id
    """)

    # 2. Default ombor: har filialda eng kichik id li faol main/shop ombori (hali default yo'q filiallarda)
    op.execute("""
        UPDATE warehouses w SET is_default = true
        FROM (
            SELECT DISTINCT ON (branch_id) id FROM warehouses
            WHERE branch_id IS NOT NULL AND is_active AND type::text IN ('main', 'shop')
              AND branch_id NOT IN (SELECT branch_id FROM warehouses WHERE is_default AND branch_id IS NOT NULL)
            ORDER BY branch_id, id
        ) d
        WHERE w.id = d.id
    """)

    # 3. Asosiy filial: avval nomi '(Asosiy)' bilan tugagan (ro'yxatdan o'tishda yaratilgan),
    #    keyin is_main yo'q korxonalarda eng kichik id li faol filial
    op.execute("""
        UPDATE branches b SET is_main = true
        FROM (
            SELECT DISTINCT ON (company_id) id FROM branches
            WHERE company_id IS NOT NULL AND name LIKE '%(Asosiy)'
            ORDER BY company_id, id
        ) m
        WHERE b.id = m.id
          AND NOT EXISTS (SELECT 1 FROM branches x WHERE x.company_id = b.company_id AND x.is_main)
    """)
    op.execute("""
        UPDATE branches b SET is_main = true
        FROM (
            SELECT DISTINCT ON (company_id) id FROM branches
            WHERE company_id IS NOT NULL AND is_active
            ORDER BY company_id, id
        ) m
        WHERE b.id = m.id
          AND NOT EXISTS (SELECT 1 FROM branches x WHERE x.company_id = b.company_id AND x.is_main)
    """)

    # 4. Qisman unique indekslar (avval dublikatlar tozalanadi)
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY branch_id ORDER BY id ASC) as rn
            FROM warehouses WHERE is_default AND branch_id IS NOT NULL
        )
        UPDATE warehouses SET is_default = false WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY id ASC) as rn
            FROM branches WHERE is_main
        )
        UPDATE branches SET is_main = false WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
    """)

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_warehouses_branch_default "
        "ON warehouses (branch_id) WHERE is_default AND branch_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_branches_company_main ON branches (company_id) WHERE is_main"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_branches_company_main")
    op.execute("DROP INDEX IF EXISTS uq_warehouses_branch_default")
    op.execute("ALTER TABLE branches DROP COLUMN IF EXISTS is_main")
    op.execute("ALTER TABLE warehouses DROP COLUMN IF EXISTS is_default")
