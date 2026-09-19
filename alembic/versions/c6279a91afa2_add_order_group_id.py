"""merge heads and add order_group_id to orders

Revision ID: c6279a91afa2
Revises: c7d4e8f21a90, x9y0z1a2b3c4
Create Date: 2026-09-20 00:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6279a91afa2'
down_revision = ('c7d4e8f21a90', 'x9y0z1a2b3c4')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('order_group_id', sa.String(length=36), nullable=True))
    op.create_index('ix_orders_order_group_id', 'orders', ['order_group_id'])


def downgrade() -> None:
    op.drop_index('ix_orders_order_group_id', table_name='orders')
    op.drop_column('orders', 'order_group_id')
