"""R5: restoran to'lovi — restaurant_orders (payments, tips_amount, change_amount, paid_by),
restaurant_order_items (stock_deducted, stock_lines).

Additiv va takroriy xavfsiz.

Revision ID: r5_1
Revises: r3_1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r5_1'
down_revision: Union[str, Sequence[str], None] = 'r3_1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(table):
    from alembic import context
    if context.is_offline_mode():
        return set()
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    oc = _cols('restaurant_orders')
    if 'payments' not in oc:
        op.add_column('restaurant_orders', sa.Column('payments', sa.JSON(), nullable=True))
    if 'tips_amount' not in oc:
        op.add_column('restaurant_orders', sa.Column('tips_amount', sa.Numeric(16, 2), nullable=False, server_default='0'))
    if 'change_amount' not in oc:
        op.add_column('restaurant_orders', sa.Column('change_amount', sa.Numeric(16, 2), nullable=False, server_default='0'))
    if 'paid_by' not in oc:
        op.add_column('restaurant_orders', sa.Column('paid_by', sa.Integer(),
                                                     sa.ForeignKey('users.id', ondelete='SET NULL',
                                                                   name='fk_restaurant_orders_paid_by'), nullable=True))
    ic = _cols('restaurant_order_items')
    if 'stock_deducted' not in ic:
        op.add_column('restaurant_order_items', sa.Column('stock_deducted', sa.Boolean(), nullable=False,
                                                          server_default=sa.false()))
    if 'stock_lines' not in ic:
        op.add_column('restaurant_order_items', sa.Column('stock_lines', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('restaurant_order_items', 'stock_lines')
    op.drop_column('restaurant_order_items', 'stock_deducted')
    op.drop_constraint('fk_restaurant_orders_paid_by', 'restaurant_orders', type_='foreignkey')
    for c in ('paid_by', 'change_amount', 'tips_amount', 'payments'):
        op.drop_column('restaurant_orders', c)
