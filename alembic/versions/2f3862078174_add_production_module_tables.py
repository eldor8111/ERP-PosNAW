"""add production module tables (bom, bom_items, production_orders, production_order_costs)

Revision ID: 2f3862078174
Revises: fa0e971873fa
Create Date: 2026-09-27

Ishlab chiqarish moduli (2-bosqich): retseptura (BOM), ishlab chiqarish
buyurtmalari va ularning qo'shimcha xarajatlari uchun jadvallar.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2f3862078174'
down_revision = 'fa0e971873fa'
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_col(table, col):
    return col in {c['name'] for c in _insp().get_columns(table)}


def _has_index(table, name):
    return name in {i['name'] for i in _insp().get_indexes(table)}


def upgrade() -> None:
    # Idempotent: server ishga tushganda (create_missing_tables) jadvallar
    # alembic'dan oldin yaratilgan bo'lishi mumkin
    insp = _insp()
    if not insp.has_table('boms'):
        op.create_table(
            'boms',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id'), nullable=True),
            sa.Column('name', sa.String(150), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_boms_product_id', 'boms', ['product_id'])
        op.create_index('ix_boms_company_id', 'boms', ['company_id'])

    if not insp.has_table('bom_items'):
        op.create_table(
            'bom_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('bom_id', sa.Integer(), sa.ForeignKey('boms.id'), nullable=False),
            sa.Column('component_product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('component_variant_id', sa.Integer(), sa.ForeignKey('product_variants.id'), nullable=True),
            sa.Column('quantity_per_unit', sa.Numeric(14, 4), nullable=False),
        )
        op.create_index('ix_bom_items_bom_id', 'bom_items', ['bom_id'])

    sa.Enum('draft', 'in_progress', 'completed', 'cancelled',
            name='productionorderstatus').create(op.get_bind(), checkfirst=True)
    production_order_status = postgresql.ENUM(
        'draft', 'in_progress', 'completed', 'cancelled',
        name='productionorderstatus', create_type=False,
    )

    if not insp.has_table('production_orders'):
        op.create_table(
            'production_orders',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('number', sa.String(30), unique=True, nullable=False),
            sa.Column('bom_id', sa.Integer(), sa.ForeignKey('boms.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id'), nullable=True),
            sa.Column('planned_quantity', sa.Numeric(14, 4), nullable=False),
            sa.Column('produced_quantity', sa.Numeric(14, 4), server_default='0'),
            sa.Column('defect_quantity', sa.Numeric(14, 4), server_default='0'),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=False),
            sa.Column('target_warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=False),
            sa.Column('status', production_order_status, server_default='draft'),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_production_orders_number', 'production_orders', ['number'])
        op.create_index('ix_production_orders_company_id', 'production_orders', ['company_id'])

    if not insp.has_table('production_order_costs'):
        op.create_table(
            'production_order_costs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('production_order_id', sa.Integer(), sa.ForeignKey('production_orders.id'), nullable=False),
            sa.Column('cost_type', sa.String(30), nullable=False),
            sa.Column('amount', sa.Numeric(16, 2), nullable=False),
            sa.Column('note', sa.String(300), nullable=True),
        )
        op.create_index('ix_production_order_costs_order_id', 'production_order_costs', ['production_order_id'])

    if not _has_col('batches', 'production_order_id'):
        op.add_column('batches', sa.Column('production_order_id', sa.Integer(), sa.ForeignKey('production_orders.id'), nullable=True))
    if not _has_index('batches', 'ix_batches_production_order_id'):
        op.create_index('ix_batches_production_order_id', 'batches', ['production_order_id'])


def downgrade() -> None:
    op.drop_index('ix_batches_production_order_id', table_name='batches')
    op.drop_column('batches', 'production_order_id')
    op.drop_table('production_order_costs')
    op.drop_table('production_orders')
    sa.Enum(name='productionorderstatus').drop(op.get_bind(), checkfirst=True)
    op.drop_table('bom_items')
    op.drop_table('boms')
