"""add warehouse_id and unit to sale_items

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-06-01 11:49:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'l6m7n8o9p0q1'
down_revision = 'k5l6m7n8o9p0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c['name'] for c in inspector.get_columns('sale_items')]
    if 'warehouse_id' not in cols:
        op.add_column('sale_items',
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=True)
        )
    if 'unit' not in cols:
        op.add_column('sale_items',
            sa.Column('unit', sa.String(length=20), nullable=True, server_default='dona')
        )
    # Mavjud yozuvlar uchun warehouse_id ni sale.warehouse_id dan ko'chirish
    op.execute("""
        UPDATE sale_items si
        SET warehouse_id = s.warehouse_id
        FROM sales s
        WHERE si.sale_id = s.id
          AND si.warehouse_id IS NULL
          AND s.warehouse_id IS NOT NULL
    """)
    # Mavjud yozuvlar uchun unit ni products.unit dan ko'chirish
    op.execute("""
        UPDATE sale_items si
        SET unit = p.unit
        FROM products p
        WHERE si.product_id = p.id
          AND (si.unit IS NULL OR si.unit = 'dona')
    """)


def downgrade():
    op.drop_column('sale_items', 'unit')
    op.drop_column('sale_items', 'warehouse_id')
