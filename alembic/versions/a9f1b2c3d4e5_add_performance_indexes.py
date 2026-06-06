"""Add performance indexes for fast queries

Revision ID: a9f1b2c3d4e5
Revises: 09735e25bc45
Create Date: 2026-04-02

Bu migration eng ko'p ishlatiladigan filtrlash ustunlariga index qo'shadi:
- sales: company_id, created_at, status, warehouse_id
- products: company_id, is_deleted
- stock_levels: warehouse_id, product_id
- customers: company_id
- sale_items: sale_id, product_id
"""
from alembic import op
import sqlalchemy as sa

revision = 'a9f1b2c3d4e5'
down_revision = ('09735e25bc45', '4b197855415f')
branch_labels = None
depends_on = None


def _safe_index(inspector, table, index_name, columns, **kwargs):
    """Jadval va ustunlar mavjud bo'lsa index yaratadi."""
    tables = inspector.get_table_names()
    if table not in tables:
        return
    existing_cols = {c['name'] for c in inspector.get_columns(table)}
    if not all(c in existing_cols for c in columns):
        return
    op.create_index(index_name, table, columns, if_not_exists=True, **kwargs)


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    _safe_index(insp, 'sales', 'ix_sales_company_id',    ['company_id'])
    _safe_index(insp, 'sales', 'ix_sales_created_at',    ['created_at'])
    _safe_index(insp, 'sales', 'ix_sales_status',        ['status'])
    _safe_index(insp, 'sales', 'ix_sales_warehouse_id',  ['warehouse_id'])
    _safe_index(insp, 'sales', 'ix_sales_cashier_id',    ['cashier_id'])
    _safe_index(insp, 'sales', 'ix_sales_customer_id',   ['customer_id'])
    _safe_index(insp, 'sales', 'ix_sales_company_created', ['company_id', 'created_at'])

    _safe_index(insp, 'products', 'ix_products_company_id',  ['company_id'])
    _safe_index(insp, 'products', 'ix_products_is_deleted',  ['is_deleted'])
    _safe_index(insp, 'products', 'ix_products_status',      ['status'])
    _safe_index(insp, 'products', 'ix_products_category_id', ['category_id'])

    _safe_index(insp, 'stock_levels', 'ix_stock_levels_warehouse_id', ['warehouse_id'])
    _safe_index(insp, 'stock_levels', 'ix_stock_levels_product_id',   ['product_id'])

    _safe_index(insp, 'sale_items', 'ix_sale_items_sale_id',    ['sale_id'])
    _safe_index(insp, 'sale_items', 'ix_sale_items_product_id', ['product_id'])

    _safe_index(insp, 'customers', 'ix_customers_company_id', ['company_id'])

    _safe_index(insp, 'expenses', 'ix_expenses_company_id', ['company_id'])
    _safe_index(insp, 'expenses', 'ix_expenses_created_at', ['created_at'])

    _safe_index(insp, 'batches', 'ix_batches_product_id',   ['product_id'])
    _safe_index(insp, 'batches', 'ix_batches_company_id',   ['company_id'])
    _safe_index(insp, 'batches', 'ix_batches_warehouse_id', ['warehouse_id'])


def downgrade():
    op.drop_index('ix_sales_company_id',       table_name='sales')
    op.drop_index('ix_sales_created_at',       table_name='sales')
    op.drop_index('ix_sales_status',           table_name='sales')
    op.drop_index('ix_sales_warehouse_id',     table_name='sales')
    op.drop_index('ix_sales_cashier_id',       table_name='sales')
    op.drop_index('ix_sales_customer_id',      table_name='sales')
    op.drop_index('ix_sales_company_created',  table_name='sales')
    op.drop_index('ix_products_company_id',    table_name='products')
    op.drop_index('ix_products_is_deleted',    table_name='products')
    op.drop_index('ix_products_status',        table_name='products')
    op.drop_index('ix_products_category_id',   table_name='products')
    op.drop_index('ix_stock_levels_warehouse_id', table_name='stock_levels')
    op.drop_index('ix_stock_levels_product_id',   table_name='stock_levels')
    op.drop_index('ix_sale_items_sale_id',     table_name='sale_items')
    op.drop_index('ix_sale_items_product_id',  table_name='sale_items')
    op.drop_index('ix_customers_company_id',   table_name='customers')
    op.drop_index('ix_expenses_company_id',    table_name='expenses')
    op.drop_index('ix_expenses_created_at',    table_name='expenses')
    op.drop_index('ix_batches_product_id',     table_name='batches')
    op.drop_index('ix_batches_company_id',     table_name='batches')
    op.drop_index('ix_batches_warehouse_id',   table_name='batches')
