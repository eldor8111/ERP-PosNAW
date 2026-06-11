"""rebuild_currency_rates_table

Revision ID: a1d57e714b04
Revises: 37e71f86c9d7
Create Date: 2026-06-10 13:23:45.907376

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'a1d57e714b04'
down_revision: Union[str, None] = '37e71f86c9d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('currency_rates', if_exists=True)
    op.create_table(
        'currency_rates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('currency_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('updated_history', JSONB(), server_default='[]', nullable=False),
        sa.ForeignKeyConstraint(['currency_id'], ['currencies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('currency_id'),
    )
    op.create_index(op.f('ix_currency_rates_id'), 'currency_rates', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_currency_rates_id'), table_name='currency_rates')
    op.drop_table('currency_rates')
