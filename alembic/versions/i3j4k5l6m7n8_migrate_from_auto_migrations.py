"""migrate remaining columns from _run_auto_migrations to Alembic

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-05-11

Eski _run_auto_migrations() dagi barcha qo'lda yozilgan SQL ni
Alembic versiyalash tizimiga ko'chirish.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'i3j4k5l6m7n8'
down_revision = 'h2i3j4k5l6m7'
branch_labels = None
depends_on = None


def _col_exists(table: str, col: str) -> bool:
    """Ustun mavjudligini tekshiradi (idempotent upgrade uchun)."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": col})
    return result.fetchone() is not None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name=:t"
    ), {"t": table})
    return result.fetchone() is not None


def upgrade():
    # ── products ──────────────────────────────────────────────────────────
    if not _col_exists('products', 'product_code'):
        op.add_column('products', sa.Column('product_code', sa.String(100), nullable=True))
        op.create_index('ix_products_product_code', 'products', ['product_code'])
    if not _col_exists('products', 'extra_product_codes'):
        op.add_column('products', sa.Column('extra_product_codes', sa.Text(), nullable=True))

    # ── purchase_orders ───────────────────────────────────────────────────
    if not _col_exists('purchase_orders', 'paid_amount'):
        op.add_column('purchase_orders', sa.Column('paid_amount', sa.Numeric(14, 2), server_default='0', nullable=True))
    if not _col_exists('purchase_orders', 'discount_amount'):
        op.add_column('purchase_orders', sa.Column('discount_amount', sa.Numeric(14, 2), server_default='0', nullable=True))

    # ── transactions ──────────────────────────────────────────────────────
    if not _col_exists('transactions', 'payment_type'):
        op.add_column('transactions', sa.Column('payment_type', sa.String(50), nullable=True))

    # ── sales ─────────────────────────────────────────────────────────────
    for col_name, col_def in [
        ('debt_due_date',         sa.Column('debt_due_date', sa.Date(), nullable=True)),
        ('loyalty_points_earned', sa.Column('loyalty_points_earned', sa.Integer(), server_default='0', nullable=True)),
        ('loyalty_points_used',   sa.Column('loyalty_points_used', sa.Integer(), server_default='0', nullable=True)),
        ('exchange_rate',         sa.Column('exchange_rate', sa.Numeric(14, 2), server_default='1', nullable=True)),
        ('currency_id',           sa.Column('currency_id', sa.Integer(), nullable=True)),
        ('discount_amount',       sa.Column('discount_amount', sa.Numeric(14, 2), server_default='0', nullable=True)),
        ('paid_cash',             sa.Column('paid_cash', sa.Numeric(14, 2), server_default='0', nullable=True)),
        ('paid_card',             sa.Column('paid_card', sa.Numeric(14, 2), server_default='0', nullable=True)),
        ('paid_cashback',         sa.Column('paid_cashback', sa.Numeric(14, 2), server_default='0', nullable=True)),
    ]:
        if not _col_exists('sales', col_name):
            op.add_column('sales', col_def)

    # ── PaymentType enum ga 'cashback' qo'shish ───────────────────────────
    bind = op.get_bind()
    bind.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'cashback'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'paymenttype')
            ) THEN
                ALTER TYPE paymenttype ADD VALUE 'cashback';
            END IF;
        END$$;
    """))

    # ── sale_payments ─────────────────────────────────────────────────────
    if not _table_exists('sale_payments'):
        op.create_table(
            'sale_payments',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id', ondelete='CASCADE'), nullable=False),
            sa.Column('payment_type', sa.String(50), nullable=False),
            sa.Column('amount', sa.Numeric(14, 2), nullable=False),
        )

    # ── wallet_balances ───────────────────────────────────────────────────
    if not _table_exists('wallet_balances'):
        op.create_table(
            'wallet_balances',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('wallet_id', sa.Integer(), sa.ForeignKey('wallets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('payment_type', sa.String(50), nullable=False),
            sa.Column('balance', sa.Numeric(14, 2), server_default='0'),
            sa.UniqueConstraint('wallet_id', 'payment_type', name='uq_wallet_payment_type'),
        )


def downgrade():
    # wallet_balances va sale_payments — faqat bo'sh bo'lsa o'chirish
    op.drop_table('wallet_balances')
    op.drop_table('sale_payments')

    op.drop_column('sales', 'paid_cashback')
    op.drop_column('sales', 'paid_card')
    op.drop_column('sales', 'paid_cash')
    op.drop_column('sales', 'discount_amount')
    op.drop_column('sales', 'currency_id')
    op.drop_column('sales', 'exchange_rate')
    op.drop_column('sales', 'loyalty_points_used')
    op.drop_column('sales', 'loyalty_points_earned')
    op.drop_column('sales', 'debt_due_date')

    op.drop_column('transactions', 'payment_type')
    op.drop_column('purchase_orders', 'discount_amount')
    op.drop_column('purchase_orders', 'paid_amount')
    op.drop_column('products', 'extra_product_codes')
    op.drop_index('ix_products_product_code', table_name='products')
    op.drop_column('products', 'product_code')
