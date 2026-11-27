"""R6.1: ofitsiant planshetlari — restaurant_terminals.

Additiv va takroriy xavfsiz.

Revision ID: r6_1
Revises: r5_3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r6_1'
down_revision: Union[str, Sequence[str], None] = 'r5_3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables():
    from alembic import context
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if 'restaurant_terminals' in _tables():
        return
    op.create_table(
        'restaurant_terminals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_restaurant_terminals_company_id', 'restaurant_terminals', ['company_id'])
    op.create_index('ix_restaurant_terminals_branch_id', 'restaurant_terminals', ['branch_id'])
    op.create_index('ix_restaurant_terminals_token_hash', 'restaurant_terminals', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_table('restaurant_terminals')
