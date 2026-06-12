"""add_mxik_reference_mxik_package_and_vat_fields_to_product

Revision ID: 191cf33ddce8
Revises: 36f7cf7bb6d5
Create Date: 2026-06-12 11:41:45.470446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '191cf33ddce8'
down_revision: Union[str, None] = '36f7cf7bb6d5'
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

    # --- mxik_references jadvali ---
    if not _tbl(conn, 'mxik_references'):
        op.create_table('mxik_references',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('mxik_code', sa.String(length=20), nullable=False),
            sa.Column('mxik_name', sa.String(length=500), nullable=True),
            sa.Column('short_name', sa.String(length=500), nullable=True),
            sa.Column('group_code', sa.String(length=10), nullable=True),
            sa.Column('group_name', sa.String(length=255), nullable=True),
            sa.Column('class_code', sa.String(length=10), nullable=True),
            sa.Column('class_name', sa.String(length=255), nullable=True),
            sa.Column('position_code', sa.String(length=20), nullable=True),
            sa.Column('position_name', sa.String(length=255), nullable=True),
            sa.Column('sub_position_code', sa.String(length=20), nullable=True),
            sa.Column('sub_position_name', sa.String(length=255), nullable=True),
            sa.Column('brand_code', sa.String(length=20), nullable=True),
            sa.Column('brand_name', sa.String(length=100), nullable=True),
            sa.Column('attribute_name', sa.String(length=255), nullable=True),
            sa.Column('international_code', sa.String(length=50), nullable=True),
            sa.Column('label', sa.SmallInteger(), nullable=True),
            sa.Column('use_card', sa.SmallInteger(), nullable=True),
            sa.Column('lgota_id', sa.Integer(), nullable=True),
            sa.Column('lgota_name', sa.Text(), nullable=True),
            sa.Column('vat_rate_type', sa.Enum('standard', 'zero', 'exempt', name='vatratetype'), nullable=False),
            sa.Column('last_synced_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
    if not _idx(conn, 'ix_mxik_references_id'):
        op.create_index(op.f('ix_mxik_references_id'), 'mxik_references', ['id'], unique=False)
    if not _idx(conn, 'ix_mxik_references_mxik_code'):
        op.create_index(op.f('ix_mxik_references_mxik_code'), 'mxik_references', ['mxik_code'], unique=True)

    # --- mxik_packages jadvali ---
    if not _tbl(conn, 'mxik_packages'):
        op.create_table('mxik_packages',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('mxik_reference_id', sa.Integer(), nullable=False),
            sa.Column('code', sa.Integer(), nullable=False),
            sa.Column('parent_code', sa.Integer(), nullable=True),
            sa.Column('container_code', sa.Integer(), nullable=True),
            sa.Column('container_name', sa.String(length=100), nullable=True),
            sa.Column('unit_id', sa.Integer(), nullable=True),
            sa.Column('unit_name', sa.String(length=50), nullable=True),
            sa.Column('parent_value', sa.Numeric(precision=12, scale=4), nullable=True),
            sa.Column('name', sa.String(length=500), nullable=True),
            sa.Column('type', sa.SmallInteger(), nullable=True),
            sa.Column('is_unit_package', sa.SmallInteger(), nullable=True),
            sa.ForeignKeyConstraint(['mxik_reference_id'], ['mxik_references.id']),
            sa.PrimaryKeyConstraint('id'),
        )
    for idx_name, cols, uniq in [
        ('ix_mxik_package_ref_code',           ['mxik_reference_id', 'code'], False),
        ('ix_mxik_packages_code',               ['code'],                      False),
        ('ix_mxik_packages_id',                 ['id'],                        False),
        ('ix_mxik_packages_mxik_reference_id',  ['mxik_reference_id'],         False),
    ]:
        if not _idx(conn, idx_name):
            op.create_index(idx_name, 'mxik_packages', cols, unique=uniq)

    # --- products ga yangi ustunlar ---
    for col, col_type in [
        ('mxik_reference_id', sa.Integer()),
        ('package_code',      sa.Integer()),
        ('vat_lgota_id',      sa.Integer()),
        ('vat_lgota_name',    sa.Text()),
        ('vat_checked_at',    sa.DateTime()),
    ]:
        if not _col(conn, 'products', col):
            op.add_column('products', sa.Column(col, col_type, nullable=True))

    if not _col(conn, 'products', 'vat_rate_type'):
        op.add_column('products', sa.Column(
            'vat_rate_type',
            sa.Enum('standard', 'zero', 'exempt', name='vatratetype'),
            nullable=True,
        ))
    if not _idx(conn, 'ix_products_mxik_reference_id'):
        op.create_index(op.f('ix_products_mxik_reference_id'), 'products', ['mxik_reference_id'], unique=False)
    if not _fk(conn, 'products', 'products_mxik_reference_id_fkey'):
        op.create_foreign_key(None, 'products', 'mxik_references', ['mxik_reference_id'], ['id'])

    # --- eski cleanup (idempotent) ---
    if _tbl(conn, 'bot_sessions'):
        if _idx(conn, 'ix_bot_sessions_chat_id'):
            op.drop_index(op.f('ix_bot_sessions_chat_id'), table_name='bot_sessions')
        op.drop_table('bot_sessions')
    if _tbl(conn, 'user_wallets'):
        if _idx(conn, 'ix_user_wallets_user'):
            op.drop_index(op.f('ix_user_wallets_user'), table_name='user_wallets')
        op.drop_table('user_wallets')
    for col in ['payme_merchant_id', 'payme_is_test', 'payme_secret_key']:
        if _col(conn, 'companies', col):
            op.drop_column('companies', col)
    for idx, tbl in [
        ('ix_kassa_movements_company', 'kassa_movements'),
        ('ix_kassa_movements_created', 'kassa_movements'),
        ('ix_kassa_movements_wallet',  'kassa_movements'),
        ('ix_kassa_sessions_company',  'kassa_sessions'),
        ('ix_kassa_sessions_wallet',   'kassa_sessions'),
        ('ix_payme_txn_company',       'payme_transactions'),
        ('ix_payme_txn_payme_id',      'payme_transactions'),
    ]:
        if _idx(conn, idx):
            op.drop_index(op.f(idx), table_name=tbl)
    if _col(conn, 'sales', 'wallet_id'):
        if _fk(conn, 'sales', 'sales_wallet_id_fkey'):
            op.drop_constraint(op.f('sales_wallet_id_fkey'), 'sales', type_='foreignkey')
        op.drop_column('sales', 'wallet_id')


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('sales', sa.Column('wallet_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.create_foreign_key(op.f('sales_wallet_id_fkey'), 'sales', 'wallets', ['wallet_id'], ['id'])
    op.drop_constraint(None, 'products', type_='foreignkey')
    op.drop_index(op.f('ix_products_mxik_reference_id'), table_name='products')
    op.drop_column('products', 'vat_checked_at')
    op.drop_column('products', 'vat_lgota_name')
    op.drop_column('products', 'vat_lgota_id')
    op.drop_column('products', 'vat_rate_type')
    op.drop_column('products', 'package_code')
    op.drop_column('products', 'mxik_reference_id')
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
    op.drop_index(op.f('ix_mxik_packages_mxik_reference_id'), table_name='mxik_packages')
    op.drop_index(op.f('ix_mxik_packages_id'), table_name='mxik_packages')
    op.drop_index(op.f('ix_mxik_packages_code'), table_name='mxik_packages')
    op.drop_index('ix_mxik_package_ref_code', table_name='mxik_packages')
    op.drop_table('mxik_packages')
    op.drop_index(op.f('ix_mxik_references_mxik_code'), table_name='mxik_references')
    op.drop_index(op.f('ix_mxik_references_id'), table_name='mxik_references')
    op.drop_table('mxik_references')
    # ### end Alembic commands ###
