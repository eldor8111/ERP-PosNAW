"""add shop_allow_out_of_stock_orders to companies

Revision ID: f2a4c6e8d0b1
Revises: e1f3a5c7b9d2
Create Date: 2026-09-20 03:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2a4c6e8d0b1'
down_revision = 'e1f3a5c7b9d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'companies',
        sa.Column('shop_allow_out_of_stock_orders', sa.Boolean(), nullable=True, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column('companies', 'shop_allow_out_of_stock_orders')
