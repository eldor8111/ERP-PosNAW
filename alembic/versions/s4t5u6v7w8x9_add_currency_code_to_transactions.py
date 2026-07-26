"""Add currency_code to transactions table

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 's4t5u6v7w8x9'
down_revision = 'r3s4t5u6v7w8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'transactions',
        sa.Column('currency_code', sa.String(3), nullable=True, server_default='UZS')
    )


def downgrade() -> None:
    op.drop_column('transactions', 'currency_code')
