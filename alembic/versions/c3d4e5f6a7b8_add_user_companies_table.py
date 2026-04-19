"""add_user_companies_table

Revision ID: c3d4e5f6a7b8
Revises: f1a2b3c4d5e6
Create Date: 2026-04-15 09:18:00.000000

Multi-korxona qo'llab-quvvatlash uchun user_companies jadvali qo'shiladi.
Mavjud users.company_id maydoni saqlanadi (backward compat.).
"""
from alembic import op


revision = 'c3d4e5f6a7b8'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use raw SQL to avoid re-creating the already-existing userrole enum type
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_companies (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            role userrole NOT NULL DEFAULT 'cashier',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP,
            CONSTRAINT uq_user_company UNIQUE (user_id, company_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_companies_user_id ON user_companies (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_companies_company_id ON user_companies (company_id)")

    # Migrate existing users into user_companies
    op.execute("""
        INSERT INTO user_companies (user_id, company_id, role, is_active, created_at)
        SELECT
            id,
            company_id,
            role,
            CASE WHEN status = 'active' THEN TRUE ELSE FALSE END,
            created_at
        FROM users
        WHERE company_id IS NOT NULL
        ON CONFLICT (user_id, company_id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_companies_company_id")
    op.execute("DROP INDEX IF EXISTS ix_user_companies_user_id")
    op.execute("DROP TABLE IF EXISTS user_companies")
