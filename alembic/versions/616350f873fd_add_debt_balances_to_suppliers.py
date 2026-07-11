"""add debt_balances to suppliers

Revision ID: 616350f873fd
Revises: 56b1207dce6c
Create Date: 2026-07-01 17:38:54.066325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '616350f873fd'
down_revision: Union[str, None] = '56b1207dce6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    op.execute("DROP INDEX IF EXISTS ix_user_wallets_user")
    op.execute("DROP TABLE IF EXISTS user_wallets")
    op.execute("DROP INDEX IF EXISTS ix_bot_sessions_chat_id")
    op.execute("DROP TABLE IF EXISTS bot_sessions")

    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='categories' AND column_name='is_deleted') THEN
                ALTER TABLE categories ALTER COLUMN is_deleted DROP NOT NULL;
            END IF;
        END $$;
    """)

    for col in ['payme_is_test', 'payme_secret_key', 'payme_merchant_id']:
        op.execute(f"ALTER TABLE companies DROP COLUMN IF EXISTS {col}")

    op.execute("DROP INDEX IF EXISTS ix_kassa_movements_company")
    op.execute("DROP INDEX IF EXISTS ix_kassa_movements_created")
    op.execute("DROP INDEX IF EXISTS ix_kassa_movements_wallet")
    op.execute("DROP INDEX IF EXISTS ix_kassa_sessions_company")
    op.execute("DROP INDEX IF EXISTS ix_kassa_sessions_wallet")
    op.execute("DROP INDEX IF EXISTS ix_payme_txn_company")
    op.execute("DROP INDEX IF EXISTS ix_payme_txn_payme_id")

    op.execute("ALTER TABLE sales DROP CONSTRAINT IF EXISTS sales_wallet_id_fkey")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS wallet_id")

    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='suppliers' AND column_name='debt_balances'"
        )
    )
    if not result.fetchone():
        op.add_column(
            'suppliers',
            sa.Column('debt_balances', sa.JSON(), nullable=False, server_default='{}')
        )


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
    op.add_column('companies', sa.Column('payme_merchant_id', sa.VARCHAR(length=50), autoincrement=False, nullable=True))
    op.add_column('companies', sa.Column('payme_secret_key', sa.VARCHAR(length=128), autoincrement=False, nullable=True))
    op.add_column('companies', sa.Column('payme_is_test', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=True))
    op.alter_column('categories', 'is_deleted',
               existing_type=sa.BOOLEAN(),
               nullable=False,
               existing_server_default=sa.text('false'))
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
    op.execute("ALTER TABLE suppliers DROP COLUMN IF EXISTS debt_balances")
