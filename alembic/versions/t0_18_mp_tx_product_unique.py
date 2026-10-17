"""T0.18: marketplace_agent_transactions.marketplace_product_id + income idempotentlik indeksi

Mir-maza webhook va pull_mirmaza_orders bitta buyurtma+mahsulot uchun faqat bitta
`income` yozuvi yozishi uchun: yangi nullable ustun (mahsulotga FK), oddiy indeks va
qisman (partial) unikal indeks. Eski qatorlar ko'chirilmaydi (ustun NULL, indeksga kirmaydi).

Revision ID: t0_18
Revises: t0_16
"""
from alembic import op
import sqlalchemy as sa


revision = 't0_18'
down_revision = 't0_16'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'marketplace_agent_transactions',
        sa.Column(
            'marketplace_product_id', sa.Integer(),
            sa.ForeignKey('marketplace_products.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.create_index(
        'ix_marketplace_agent_transactions_marketplace_product_id',
        'marketplace_agent_transactions', ['marketplace_product_id'],
    )
    op.create_index(
        'uq_mp_tx_income_order_product',
        'marketplace_agent_transactions', ['order_id', 'marketplace_product_id'],
        unique=True,
        postgresql_where=sa.text("transaction_type = 'income' AND marketplace_product_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index('uq_mp_tx_income_order_product', table_name='marketplace_agent_transactions')
    op.drop_index('ix_marketplace_agent_transactions_marketplace_product_id', table_name='marketplace_agent_transactions')
    op.drop_column('marketplace_agent_transactions', 'marketplace_product_id')
