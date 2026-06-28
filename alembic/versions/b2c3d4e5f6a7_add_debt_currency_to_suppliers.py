"""add_debt_currency_to_suppliers

Revision ID: b2c3d4e5f6a7
Revises: 
Create Date: 2026-06-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # debt_currency ustuni mavjudligini tekshirish
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='suppliers' AND column_name='debt_currency'"
        )
    )
    if not result.fetchone():
        op.add_column(
            'suppliers',
            sa.Column('debt_currency', sa.String(10), nullable=False, server_default='UZS')
        )


def downgrade():
    op.drop_column('suppliers', 'debt_currency')
