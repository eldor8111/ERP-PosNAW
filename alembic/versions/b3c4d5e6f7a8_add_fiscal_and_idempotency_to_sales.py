"""add fiscal fields and idempotency_key to sales

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b3c4d5e6f7a8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sales', sa.Column('idempotency_key', sa.String(64), nullable=True))
    # Unikallik kompaniya doirasida — global emas (boshqa kompaniya kaliti
    # bilan tasodifiy to'qnashuv 500 bermasligi uchun).
    op.create_index('ux_sales_company_idem_key', 'sales', ['company_id', 'idempotency_key'], unique=True)
    op.add_column('sales', sa.Column('fiscal_sign', sa.String(64), nullable=True))
    op.add_column('sales', sa.Column('fiscal_qr_url', sa.Text(), nullable=True))
    op.add_column('sales', sa.Column('fiscal_receipt_seq', sa.Integer(), nullable=True))
    op.add_column('sales', sa.Column('fiscal_transaction_id', sa.String(64), nullable=True))
    op.add_column('sales', sa.Column('fiscal_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('sales', 'fiscal_at')
    op.drop_column('sales', 'fiscal_transaction_id')
    op.drop_column('sales', 'fiscal_receipt_seq')
    op.drop_column('sales', 'fiscal_qr_url')
    op.drop_column('sales', 'fiscal_sign')
    op.drop_index('ux_sales_company_idem_key', table_name='sales')
    op.drop_column('sales', 'idempotency_key')
