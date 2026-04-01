"""add_agents_table

Revision ID: 08e432b58c66
Revises: a6ffaadaea75
Create Date: 2026-03-25 12:51:24.670796

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '08e432b58c66'
down_revision: Union[str, None] = 'a6ffaadaea75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.UniqueConstraint('phone'),
    )
    op.create_index(op.f('ix_agents_id'), 'agents', ['id'], unique=False)
    op.create_index(op.f('ix_agents_code'), 'agents', ['code'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_agents_code'), table_name='agents')
    op.drop_index(op.f('ix_agents_id'), table_name='agents')
    op.drop_table('agents')
