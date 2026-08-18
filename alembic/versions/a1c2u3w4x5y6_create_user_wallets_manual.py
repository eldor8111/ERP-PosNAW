"""create user_wallets table (manual, safe)

Revision ID: a1c2u3w4x5y6
Revises: 92e3c075c1b5
Create Date: 2026-07-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1c2u3w4x5y6'
down_revision: Union[str, None] = '92e3c075c1b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect
    bind = op.get_bind()
    insp = inspect(bind)
    if 'user_wallets' not in insp.get_table_names():
        op.create_table(
            'user_wallets',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('wallet_id', sa.Integer(), sa.ForeignKey('wallets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.UniqueConstraint('user_id', 'wallet_id', name='uq_user_wallets_user_wallet'),
        )
        op.create_index('ix_user_wallets_user_id', 'user_wallets', ['user_id'])
        op.create_index('ix_user_wallets_wallet_id', 'user_wallets', ['wallet_id'])


def downgrade() -> None:
    op.drop_index('ix_user_wallets_wallet_id', table_name='user_wallets')
    op.drop_index('ix_user_wallets_user_id', table_name='user_wallets')
    op.drop_table('user_wallets')
