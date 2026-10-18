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
    op.execute("""
        CREATE TABLE IF NOT EXISTS fiscal_devices (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            branch_id INTEGER REFERENCES branches(id) ON DELETE SET NULL,
            wallet_id INTEGER REFERENCES wallets(id) ON DELETE SET NULL,
            factory_id VARCHAR(64) NOT NULL,
            label VARCHAR(100),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW()
        );

        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_fiscal_devices_company_factory') THEN
                ALTER TABLE fiscal_devices ADD CONSTRAINT uq_fiscal_devices_company_factory UNIQUE (company_id, factory_id);
            END IF;
        END $$;

        CREATE INDEX IF NOT EXISTS ix_fiscal_devices_id ON fiscal_devices (id);
        CREATE INDEX IF NOT EXISTS ix_fiscal_devices_company_branch ON fiscal_devices (company_id, branch_id);

        CREATE TABLE IF NOT EXISTS payment_terminals (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            branch_id INTEGER REFERENCES branches(id) ON DELETE SET NULL,
            wallet_id INTEGER REFERENCES wallets(id) ON DELETE SET NULL,
            provider VARCHAR(20) NOT NULL,
            label VARCHAR(100),
            merchant_id VARCHAR(64),
            terminal_id VARCHAR(64),
            require_reference BOOLEAN NOT NULL DEFAULT true,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW()
        );

        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_payment_terminals_provider') THEN
                ALTER TABLE payment_terminals ADD CONSTRAINT ck_payment_terminals_provider 
                    CHECK (provider IN ('payme','click','uzum','uzcard','humo')) NOT VALID;
            END IF;
        END $$;

        CREATE INDEX IF NOT EXISTS ix_payment_terminals_id ON payment_terminals (id);
        CREATE INDEX IF NOT EXISTS ix_payment_terminals_company_branch_provider 
            ON payment_terminals (company_id, branch_id, provider);

        ALTER TABLE sale_payments ADD COLUMN IF NOT EXISTS reference VARCHAR(64);
        ALTER TABLE sale_payments ADD COLUMN IF NOT EXISTS terminal_id INTEGER REFERENCES payment_terminals(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS ix_sale_payments_reference ON sale_payments (reference);

        ALTER TABLE sales ADD COLUMN IF NOT EXISTS fiscal_factory_id VARCHAR(64);
    """)


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
