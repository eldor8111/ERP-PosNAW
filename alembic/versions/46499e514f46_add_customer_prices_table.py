"""add customer_prices table

Revision ID: 46499e514f46
Revises: df9132535f4b
Create Date: 2026-06-07 12:29:41.802050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '46499e514f46'
down_revision: Union[str, None] = 'df9132535f4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tbl(conn, t):
    return conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name=:t)"), {"t": t}).scalar()

def _col(conn, t, c):
    return conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name=:c)"), {"t": t, "c": c}).scalar()

def _idx(conn, i):
    return conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname=:i)"), {"i": i}).scalar()

def _fk(conn, t, c):
    return conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_name=:t AND constraint_name=:c)"), {"t": t, "c": c}).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    if _tbl(conn, 'user_wallets'):
        if _idx(conn, 'ix_user_wallets_user'):
            op.drop_index(op.f('ix_user_wallets_user'), table_name='user_wallets')
        op.drop_table('user_wallets')

    if _tbl(conn, 'bot_sessions'):
        if _idx(conn, 'ix_bot_sessions_chat_id'):
            op.drop_index(op.f('ix_bot_sessions_chat_id'), table_name='bot_sessions')
        op.drop_table('bot_sessions')

    for col in ['payme_merchant_id', 'payme_is_test', 'payme_secret_key']:
        if _col(conn, 'companies', col):
            op.drop_column('companies', col)

    for idx, tbl in [
        ('ix_kassa_movements_company', 'kassa_movements'),
        ('ix_kassa_movements_created', 'kassa_movements'),
        ('ix_kassa_movements_wallet', 'kassa_movements'),
        ('ix_kassa_sessions_company', 'kassa_sessions'),
        ('ix_kassa_sessions_wallet', 'kassa_sessions'),
        ('ix_payme_txn_company', 'payme_transactions'),
        ('ix_payme_txn_payme_id', 'payme_transactions'),
    ]:
        if _idx(conn, idx):
            op.drop_index(op.f(idx), table_name=tbl)

    if _col(conn, 'sales', 'wallet_id'):
        if _fk(conn, 'sales', 'sales_wallet_id_fkey'):
            op.drop_constraint(op.f('sales_wallet_id_fkey'), 'sales', type_='foreignkey')
        op.drop_column('sales', 'wallet_id')


def downgrade() -> None:
    op.add_column('sales', sa.Column('wallet_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.create_foreign_key(op.f('sales_wallet_id_fkey'), 'sales', 'wallets', ['wallet_id'], ['id'])
    op.create_index(op.f('ix_payme_txn_payme_id'), 'payme_transactions', ['payme_id'], unique=True)
    op.create_index(op.f('ix_payme_txn_company'), 'payme_transactions', ['company_id'], unique=False)
    op.create_index(op.f('ix_kassa_sessions_wallet'), 'kassa_sessions', ['wallet_id'], unique=False)
    op.create_index(op.f('ix_kassa_sessions_company'), 'kassa_sessions', ['company_id'], unique=False)
    op.create_index(op.f('ix_kassa_movements_wallet'), 'kassa_movements', ['wallet_id'], unique=False)
    op.create_index(op.f('ix_kassa_movements_created'), 'kassa_movements', ['created_at'], unique=False)
    op.create_index(op.f('ix_kassa_movements_company'), 'kassa_movements', ['company_id'], unique=False)
    op.add_column('companies', sa.Column('payme_secret_key', sa.VARCHAR(length=128), autoincrement=False, nullable=True))
    op.add_column('companies', sa.Column('payme_is_test', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=True))
    op.add_column('companies', sa.Column('payme_merchant_id', sa.VARCHAR(length=50), autoincrement=False, nullable=True))
    op.create_table('bot_sessions',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
        sa.Column('token', sa.VARCHAR(length=300), autoincrement=False, nullable=False),
        sa.Column('step', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
        sa.Column('temp_name', sa.VARCHAR(length=200), autoincrement=False, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('bot_sessions_pkey'))
    )
    op.create_index(op.f('ix_bot_sessions_chat_id'), 'bot_sessions', ['chat_id'], unique=False)
    op.create_table('user_wallets',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('wallet_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('is_default', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('user_wallets_user_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], name=op.f('user_wallets_wallet_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('user_wallets_pkey')),
        sa.UniqueConstraint('user_id', 'wallet_id', name=op.f('user_wallets_user_id_wallet_id_key'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_user_wallets_user'), 'user_wallets', ['user_id'], unique=False)
