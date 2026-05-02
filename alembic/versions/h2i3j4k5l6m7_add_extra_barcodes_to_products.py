"""add extra_barcodes to products

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-05-02

"""
from alembic import op
import sqlalchemy as sa

revision = 'h2i3j4k5l6m7'
down_revision = 'g1h2i3j4k5l6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('extra_barcodes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('products', 'extra_barcodes')
