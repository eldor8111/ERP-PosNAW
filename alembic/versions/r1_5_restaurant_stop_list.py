"""R1.5: stop-list — menu_stops (filial bo'yicha to'xtatish va porsiya hisoblagichi).

Additiv va takroriy xavfsiz.

Revision ID: r1_5
Revises: r1_3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r1_5'
down_revision: Union[str, Sequence[str], None] = 'r1_3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables():
    from alembic import context
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if 'menu_stops' in _tables():
        return
    op.create_table(
        'menu_stops',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('stopped', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('reason', sa.String(200), nullable=True),
        sa.Column('until', sa.DateTime(), nullable=True),
        sa.Column('remaining', sa.Numeric(12, 3), nullable=True),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('branch_id', 'product_id', name='uq_menu_stop_branch_product'),
    )
    op.create_index('ix_menu_stops_company_id', 'menu_stops', ['company_id'])
    op.create_index('ix_menu_stops_branch_id', 'menu_stops', ['branch_id'])
    op.create_index('ix_menu_stops_product_id', 'menu_stops', ['product_id'])


def downgrade() -> None:
    op.drop_table('menu_stops')
