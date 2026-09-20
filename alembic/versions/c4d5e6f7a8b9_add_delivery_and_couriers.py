"""add couriers table, order delivery fields, company delivery_fee

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'couriers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('phone', sa.String(32), nullable=False),
        sa.Column('tg_chat_id', sa.String(32), nullable=True),
        sa.Column('transport', sa.String(30), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_couriers_company_id', 'couriers', ['company_id'])
    op.create_index('ix_couriers_tg_chat_id', 'couriers', ['tg_chat_id'])

    op.add_column('orders', sa.Column('delivery_type', sa.String(20), server_default='pickup', nullable=True))
    op.add_column('orders', sa.Column('delivery_address', sa.String(500), nullable=True))
    op.add_column('orders', sa.Column('delivery_lat', sa.Numeric(10, 7), nullable=True))
    op.add_column('orders', sa.Column('delivery_lng', sa.Numeric(10, 7), nullable=True))
    op.add_column('orders', sa.Column('contact_phone', sa.String(32), nullable=True))
    op.add_column('orders', sa.Column('delivery_fee', sa.Numeric(14, 2), server_default='0', nullable=True))
    op.add_column('orders', sa.Column('courier_id', sa.Integer(), sa.ForeignKey('couriers.id'), nullable=True))
    op.create_index('ix_orders_courier_id', 'orders', ['courier_id'])
    op.add_column('orders', sa.Column('assigned_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('on_way_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('delivered_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('cancel_reason', sa.String(300), nullable=True))

    op.add_column('companies', sa.Column('delivery_fee', sa.Numeric(14, 2), server_default='0', nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'delivery_fee')
    for col in ('cancel_reason', 'delivered_at', 'on_way_at', 'assigned_at'):
        op.drop_column('orders', col)
    op.drop_index('ix_orders_courier_id', table_name='orders')
    for col in ('courier_id', 'delivery_fee', 'contact_phone', 'delivery_lng', 'delivery_lat', 'delivery_address', 'delivery_type'):
        op.drop_column('orders', col)
    op.drop_index('ix_couriers_tg_chat_id', table_name='couriers')
    op.drop_index('ix_couriers_company_id', table_name='couriers')
    op.drop_table('couriers')
