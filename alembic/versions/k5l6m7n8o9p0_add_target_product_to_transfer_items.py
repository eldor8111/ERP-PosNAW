"""add_target_product_to_transfer_items

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-05-31

"""
from alembic import op
import sqlalchemy as sa

revision = 'k5l6m7n8o9p0'
down_revision = 'j4k5l6m7n8o9'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'stock_transfer_items' not in inspector.get_table_names():
        return
    cols = [c['name'] for c in inspector.get_columns('stock_transfer_items')]
    if 'target_product_id' not in cols:
        op.add_column(
            'stock_transfer_items',
            sa.Column(
                'target_product_id',
                sa.Integer(),
                sa.ForeignKey('products.id', ondelete='SET NULL'),
                nullable=True
            )
        )


def downgrade():
    op.drop_column('stock_transfer_items', 'target_product_id')
