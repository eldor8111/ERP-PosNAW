"""add unit_cost and total_cost to production_orders

Revision ID: 7aaf2453672d
Revises: 2f3862078174
Create Date: 2026-09-27

Ishlab chiqarish buyurtmasi yakunlanganda hisoblangan tannarxni saqlash uchun.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7aaf2453672d'
down_revision = '2f3862078174'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('production_orders', sa.Column('unit_cost', sa.Numeric(16, 4), nullable=True))
    op.add_column('production_orders', sa.Column('total_cost', sa.Numeric(16, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('production_orders', 'total_cost')
    op.drop_column('production_orders', 'unit_cost')
