"""R1.3: taom qo'shimchalari — modifier_groups, modifiers, product_modifier_groups.

Additiv va takroriy xavfsiz.

Revision ID: r1_3
Revises: r5_2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r1_3'
down_revision: Union[str, Sequence[str], None] = 'r5_2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables():
    from alembic import context
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if 'modifier_groups' not in tables:
        op.create_table(
            'modifier_groups',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('min_select', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('max_select', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_modifier_groups_company_id', 'modifier_groups', ['company_id'])
    if 'modifiers' not in tables:
        op.create_table(
            'modifiers',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('group_id', sa.Integer(), sa.ForeignKey('modifier_groups.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('price', sa.Numeric(16, 2), nullable=False, server_default='0'),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='SET NULL'), nullable=True),
            sa.Column('quantity', sa.Numeric(12, 3), nullable=False, server_default='0'),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.create_index('ix_modifiers_company_id', 'modifiers', ['company_id'])
        op.create_index('ix_modifiers_group_id', 'modifiers', ['group_id'])
    if 'product_modifier_groups' not in tables:
        op.create_table(
            'product_modifier_groups',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
            sa.Column('group_id', sa.Integer(), sa.ForeignKey('modifier_groups.id', ondelete='CASCADE'), nullable=False),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.UniqueConstraint('product_id', 'group_id', name='uq_product_modifier_group'),
        )
        op.create_index('ix_product_modifier_groups_company_id', 'product_modifier_groups', ['company_id'])
        op.create_index('ix_product_modifier_groups_product_id', 'product_modifier_groups', ['product_id'])
        op.create_index('ix_product_modifier_groups_group_id', 'product_modifier_groups', ['group_id'])


def downgrade() -> None:
    op.drop_table('product_modifier_groups')
    op.drop_table('modifiers')
    op.drop_table('modifier_groups')
