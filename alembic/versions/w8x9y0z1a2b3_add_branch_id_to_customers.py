"""add branch_id to customers

Revision ID: w8x9y0z1a2b3
Revises: v7w8x9y0z1a2
Create Date: 2026-09-19 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'w8x9y0z1a2b3'
down_revision = 'v7w8x9y0z1a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('branch_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_customers_branch_id', 'customers', 'branches', ['branch_id'], ['id'])
    op.create_index('ix_customers_branch_id', 'customers', ['branch_id'])


def downgrade() -> None:
    op.drop_index('ix_customers_branch_id', table_name='customers')
    op.drop_constraint('fk_customers_branch_id', 'customers', type_='foreignkey')
    op.drop_column('customers', 'branch_id')
