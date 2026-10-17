"""T3.15: background_leases — scheduler/admin bot "rahbar" jarayoni ijarasi

Kunlik vazifalar registri (scheduler_runs) T2.10 migratsiyasida (t2_10) yaratilgan.

Revision ID: t3_15
Revises:
Create Date: 2026-10-17
"""
from alembic import op

revision = 't3_15'
down_revision = 't3_14'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS background_leases (
            name VARCHAR(60) PRIMARY KEY,
            holder VARCHAR(120) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS background_leases")
