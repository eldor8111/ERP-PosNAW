"""Add currency_code and exchange_rate to sale_items

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'r3s4t5u6v7w8'
down_revision = 'q2r3s4t5u6v7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'sale_items',
        sa.Column('currency_code', sa.String(10), nullable=False, server_default='UZS')
    )
    op.add_column(
        'sale_items',
        sa.Column('exchange_rate', sa.Numeric(14, 2), nullable=False, server_default='1')
    )


def downgrade() -> None:
    op.drop_column('sale_items', 'exchange_rate')
    op.drop_column('sale_items', 'currency_code')
