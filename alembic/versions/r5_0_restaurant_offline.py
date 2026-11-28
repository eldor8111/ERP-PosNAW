"""R5.0: E-Code POS Restoran oflayn sinxronlash — restaurant_orders.client_uuid/offline_no, restaurant_offline_ops.

Additiv va takroriy xavfsiz (enum turlariga tegmaydi).

Revision ID: r5_0
Revises: r9_1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r5_0'
down_revision: Union[str, Sequence[str], None] = 'r9_1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _insp():
    from alembic import context
    if context.is_offline_mode():
        return None
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    insp = _insp()
    tables = set(insp.get_table_names()) if insp else set()
    cols = {c['name'] for c in insp.get_columns('restaurant_orders')} if insp else set()
    idx = {i['name'] for i in insp.get_indexes('restaurant_orders')} if insp else set()
    if 'client_uuid' not in cols:
        op.add_column('restaurant_orders', sa.Column('client_uuid', sa.String(40), nullable=True))
    if 'offline_no' not in cols:
        op.add_column('restaurant_orders', sa.Column('offline_no', sa.String(20), nullable=True))
    if 'uq_rest_orders_client_uuid' not in idx:
        op.create_index('uq_rest_orders_client_uuid', 'restaurant_orders', ['company_id', 'client_uuid'], unique=True)
    if 'restaurant_offline_ops' not in tables:
        op.create_table(
            'restaurant_offline_ops',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('op_id', sa.String(64), nullable=False),
            sa.Column('order_id', sa.Integer(), sa.ForeignKey('restaurant_orders.id', ondelete='SET NULL'), nullable=True),
            sa.Column('device', sa.String(100), nullable=True),
            sa.Column('result', sa.JSON(), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('company_id', 'op_id', name='uq_rest_offline_op'),
        )
        op.create_index('ix_restaurant_offline_ops_company_id', 'restaurant_offline_ops', ['company_id'])
        op.create_index('ix_restaurant_offline_ops_order_id', 'restaurant_offline_ops', ['order_id'])


def downgrade() -> None:
    op.drop_table('restaurant_offline_ops')
    op.drop_index('uq_rest_orders_client_uuid', table_name='restaurant_orders')
    op.drop_column('restaurant_orders', 'offline_no')
    op.drop_column('restaurant_orders', 'client_uuid')
