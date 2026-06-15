"""add_debt_currency_to_customers

Revision ID: a1b2c3d5e6f7
Revises: c475894a85b0
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d5e6f7'
down_revision = 'c475894a85b0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('customers',
        sa.Column('debt_currency', sa.String(3), nullable=False, server_default='UZS')
    )
    op.add_column('customers',
        sa.Column('debt_balances', sa.JSON(), nullable=False, server_default='{}')
    )


def downgrade():
    op.drop_column('customers', 'debt_balances')
    op.drop_column('customers', 'debt_currency')
