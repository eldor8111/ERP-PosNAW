"""R5.2: hisobni bo'lish — restaurant_orders.split_from_id.

Additiv va takroriy xavfsiz.

Revision ID: r5_3
Revises: r1_5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r5_3'
down_revision: Union[str, Sequence[str], None] = 'r1_5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(table):
    from alembic import context
    if context.is_offline_mode():
        return set()
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if 'split_from_id' not in _cols('restaurant_orders'):
        op.add_column('restaurant_orders', sa.Column('split_from_id', sa.Integer(),
                                                     sa.ForeignKey('restaurant_orders.id', ondelete='SET NULL'),
                                                     nullable=True))


def downgrade() -> None:
    op.drop_column('restaurant_orders', 'split_from_id')
