"""T4.7 — filial/sotuvchi savdo rejasi (sales_targets) va sotuvchi komissiya stavkasi (employee_commissions)

Yangi jadvallar bo'sh boshlanadi (ma'lumotni ko'chirish kerak emas).
sales_targets: partial unique (branch_id, period_month) WHERE user_id IS NULL va
(branch_id, user_id, period_month) WHERE user_id IS NOT NULL; CHECK revenue_target >= 0 va oyning 1-kuni.

Revision ID: t4_7
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't4_7'
down_revision: Union[str, None] = 't4_6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sales_targets (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            branch_id INTEGER NOT NULL REFERENCES branches(id),
            user_id INTEGER REFERENCES users(id),
            period_month DATE NOT NULL,
            revenue_target NUMERIC(20,2) NOT NULL,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT ck_sales_targets_nonneg CHECK (revenue_target >= 0),
            CONSTRAINT ck_sales_targets_month_start CHECK (EXTRACT(DAY FROM period_month) = 1)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_sales_targets_id ON sales_targets(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sales_targets_company_month ON sales_targets(company_id, period_month)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_targets_branch "
        "ON sales_targets(branch_id, period_month) WHERE user_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_targets_user "
        "ON sales_targets(branch_id, user_id, period_month) WHERE user_id IS NOT NULL"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_commissions (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            percent NUMERIC(5,2) NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT uq_employee_commissions_company_user UNIQUE (company_id, user_id),
            CONSTRAINT ck_employee_commissions_percent CHECK (percent BETWEEN 0 AND 100)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_employee_commissions_id ON employee_commissions(id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS employee_commissions")
    op.execute("DROP TABLE IF EXISTS sales_targets")
