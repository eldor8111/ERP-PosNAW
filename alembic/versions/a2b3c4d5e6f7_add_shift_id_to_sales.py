"""add shift_id to sales

Revision ID: a2b3c4d5e6f7
Revises: z1a2b3c4d5e6
Create Date: 2026-09-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = 'z1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sales', sa.Column('shift_id', sa.Integer(), nullable=True))
    op.create_index('ix_sales_shift_id', 'sales', ['shift_id'])
    op.create_foreign_key('fk_sales_shift_id', 'sales', 'shifts', ['shift_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_sales_shift_id', 'sales', type_='foreignkey')
    op.drop_index('ix_sales_shift_id', table_name='sales')
    op.drop_column('sales', 'shift_id')
