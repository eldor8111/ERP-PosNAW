"""T1.19 — audit_logs korxona/filial kesimi, indekslar; expenses/transactions uchun void ustunlari

Revision ID: t1_19
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_19'
down_revision: Union[str, None] = 't1_16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. audit_logs: korxona va filial kesimi
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)")
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS branch_id INTEGER REFERENCES branches(id)")

    # 2. Eski yozuvlar: faqat company_id to'ldiriladi (branch_id taxminiy bo'lardi — NULL qoladi)
    op.execute(
        "UPDATE audit_logs a SET company_id = u.company_id "
        "FROM users u WHERE a.user_id = u.id AND a.company_id IS NULL"
    )

    # 3. Indekslar
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_company_created ON audit_logs (company_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_company_branch ON audit_logs (company_id, branch_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_entity ON audit_logs (entity_type, entity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_user ON audit_logs (user_id)")

    # 4. expenses va transactions: bekor qilish (void) ustunlari
    for table in ("expenses", "transactions"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS voided_at TIMESTAMP NULL")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS voided_by INTEGER NULL REFERENCES users(id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_transactions_voided ON transactions (company_id) WHERE voided_at IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_expenses_voided ON expenses (company_id) WHERE voided_at IS NOT NULL"
    )


def downgrade() -> None:
    # Diqqat: voided_* ustunlari o'chiriladi — bekor qilingan yozuvlar qoladi, lekin "bekor" belgisi yo'qoladi.
    op.execute("DROP INDEX IF EXISTS ix_expenses_voided")
    op.execute("DROP INDEX IF EXISTS ix_transactions_voided")
    for table in ("transactions", "expenses"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS voided_by")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS voided_at")

    op.execute("DROP INDEX IF EXISTS ix_audit_logs_user")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_entity")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_company_branch")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_company_created")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS branch_id")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS company_id")
