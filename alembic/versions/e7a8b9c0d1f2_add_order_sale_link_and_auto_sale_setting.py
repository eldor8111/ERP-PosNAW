"""add orders.sale_id link and companies.orders_auto_create_sale

Revision ID: e7a8b9c0d1f2
Revises: d5e6f7a8b9c0
Create Date: 2026-09-21

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e7a8b9c0d1f2'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id'), nullable=True))
    op.add_column('companies', sa.Column('orders_auto_create_sale', sa.Boolean(), server_default='false', nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'orders_auto_create_sale')
    op.drop_column('orders', 'sale_id')
