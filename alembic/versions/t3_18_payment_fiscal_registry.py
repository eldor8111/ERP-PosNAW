"""T3.18: fiscal_devices, payment_terminals, sale_payments.reference/terminal_id, sales.fiscal_factory_id

Revision ID: t3_18
Revises:
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = 't3_18'
down_revision = 't3_17'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'fiscal_devices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True),
        sa.Column('wallet_id', sa.Integer(), sa.ForeignKey('wallets.id', ondelete='SET NULL'), nullable=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('label', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('company_id', 'factory_id', name='uq_fiscal_devices_company_factory'),
    )
    op.create_index('ix_fiscal_devices_id', 'fiscal_devices', ['id'])
    op.create_index('ix_fiscal_devices_company_branch', 'fiscal_devices', ['company_id', 'branch_id'])

    op.create_table(
        'payment_terminals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True),
        sa.Column('wallet_id', sa.Integer(), sa.ForeignKey('wallets.id', ondelete='SET NULL'), nullable=True),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('label', sa.String(100), nullable=True),
        sa.Column('merchant_id', sa.String(64), nullable=True),
        sa.Column('terminal_id', sa.String(64), nullable=True),
        sa.Column('require_reference', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint("provider IN ('payme','click','uzum','uzcard','humo')", name='ck_payment_terminals_provider'),
    )
    op.create_index('ix_payment_terminals_id', 'payment_terminals', ['id'])
    op.create_index(
        'ix_payment_terminals_company_branch_provider', 'payment_terminals', ['company_id', 'branch_id', 'provider'],
    )

    op.add_column('sale_payments', sa.Column('reference', sa.String(64), nullable=True))
    op.add_column(
        'sale_payments',
        sa.Column('terminal_id', sa.Integer(), sa.ForeignKey('payment_terminals.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_sale_payments_reference', 'sale_payments', ['reference'])

    op.add_column('sales', sa.Column('fiscal_factory_id', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('sales', 'fiscal_factory_id')
    op.drop_index('ix_sale_payments_reference', table_name='sale_payments')
    op.drop_column('sale_payments', 'terminal_id')
    op.drop_column('sale_payments', 'reference')
    op.drop_index('ix_payment_terminals_company_branch_provider', table_name='payment_terminals')
    op.drop_index('ix_payment_terminals_id', table_name='payment_terminals')
    op.drop_table('payment_terminals')
    op.drop_index('ix_fiscal_devices_company_branch', table_name='fiscal_devices')
    op.drop_index('ix_fiscal_devices_id', table_name='fiscal_devices')
    op.drop_table('fiscal_devices')
