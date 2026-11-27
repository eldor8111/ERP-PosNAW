"""R7.5: tannarx o'zgarishlari jurnali — restaurant_cost_changes.

Additiv va takroriy xavfsiz.

Revision ID: r7_5
Revises: r6_1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r7_5'
down_revision: Union[str, Sequence[str], None] = 'r6_1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables():
    from alembic import context
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if 'restaurant_cost_changes' in _tables():
        return
    op.create_table(
        'restaurant_cost_changes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('threshold', sa.Numeric(5, 1), nullable=True),
        sa.Column('ingredients', sa.JSON(), nullable=True),
        sa.Column('dishes', sa.JSON(), nullable=True),
        sa.Column('over_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_restaurant_cost_changes_company_id', 'restaurant_cost_changes', ['company_id'])
    op.create_index('ix_restaurant_cost_changes_created_at', 'restaurant_cost_changes', ['created_at'])


def downgrade() -> None:
    op.drop_table('restaurant_cost_changes')
