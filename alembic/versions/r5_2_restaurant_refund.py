"""R5.4: restoran chekini qaytarish — restaurant_orders (refunded_amount, refunds), restaurant_order_items.refunded_qty.

Additiv va takroriy xavfsiz.

Revision ID: r5_2
Revises: r5_1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r5_2'
down_revision: Union[str, Sequence[str], None] = 'r5_1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(table):
    from alembic import context
    if context.is_offline_mode():
        return set()
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    oc = _cols('restaurant_orders')
    if 'refunded_amount' not in oc:
        op.add_column('restaurant_orders', sa.Column('refunded_amount', sa.Numeric(16, 2), nullable=False,
                                                     server_default='0'))
    if 'refunds' not in oc:
        op.add_column('restaurant_orders', sa.Column('refunds', sa.JSON(), nullable=True))
    if 'refunded_qty' not in _cols('restaurant_order_items'):
        op.add_column('restaurant_order_items', sa.Column('refunded_qty', sa.Numeric(12, 3), nullable=False,
                                                          server_default='0'))


def downgrade() -> None:
    op.drop_column('restaurant_order_items', 'refunded_qty')
    op.drop_column('restaurant_orders', 'refunds')
    op.drop_column('restaurant_orders', 'refunded_amount')
