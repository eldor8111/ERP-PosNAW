"""add customer_type and territory to customers

Revision ID: c41d8e9b7a52
Revises: 7aaf2453672d
Create Date: 2026-09-27

Distribyutorlar: mijoz turi (retail/distributor) va hudud.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c41d8e9b7a52'
down_revision = '7aaf2453672d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c['name'] for c in insp.get_columns('customers')}
    if 'customer_type' not in cols:
        op.add_column('customers', sa.Column('customer_type', sa.String(20), nullable=False, server_default='retail'))
    if 'territory' not in cols:
        op.add_column('customers', sa.Column('territory', sa.String(100), nullable=True))
    if 'ix_customers_customer_type' not in {i['name'] for i in insp.get_indexes('customers')}:
        op.create_index('ix_customers_customer_type', 'customers', ['customer_type'])


def downgrade() -> None:
    op.drop_index('ix_customers_customer_type', table_name='customers')
    op.drop_column('customers', 'territory')
    op.drop_column('customers', 'customer_type')
