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

revision = 'a9f1b2c3d4e5'
down_revision = ('09735e25bc45', '4b197855415f')
branch_labels = None
depends_on = None


def upgrade():
    # Sales jadvali — dashboard va hisobotlarda eng ko'p filtrlash
    op.create_index('ix_sales_company_id',    'sales', ['company_id'],    if_not_exists=True)
    op.create_index('ix_sales_created_at',    'sales', ['created_at'],    if_not_exists=True)
    op.create_index('ix_sales_status',        'sales', ['status'],        if_not_exists=True)
    op.create_index('ix_sales_warehouse_id',  'sales', ['warehouse_id'],  if_not_exists=True)
    op.create_index('ix_sales_cashier_id',    'sales', ['cashier_id'],    if_not_exists=True)
    op.create_index('ix_sales_customer_id',   'sales', ['customer_id'],   if_not_exists=True)
    # Composite index: company + date — dashboard uchun eng muhimi
    op.create_index('ix_sales_company_created', 'sales', ['company_id', 'created_at'], if_not_exists=True)

    # Products jadvali
    op.create_index('ix_products_company_id',  'products', ['company_id'],  if_not_exists=True)
    op.create_index('ix_products_is_deleted',  'products', ['is_deleted'],  if_not_exists=True)
    op.create_index('ix_products_status',      'products', ['status'],      if_not_exists=True)
    op.create_index('ix_products_category_id', 'products', ['category_id'], if_not_exists=True)

    # Stock levels — inventar so'rovlar
    op.create_index('ix_stock_levels_warehouse_id', 'stock_levels', ['warehouse_id'], if_not_exists=True)
    op.create_index('ix_stock_levels_product_id',   'stock_levels', ['product_id'],   if_not_exists=True)

    # Sale items — hisobot agregatsiyalari
    op.create_index('ix_sale_items_sale_id',    'sale_items', ['sale_id'],    if_not_exists=True)
    op.create_index('ix_sale_items_product_id', 'sale_items', ['product_id'], if_not_exists=True)

    # Customers
    op.create_index('ix_customers_company_id', 'customers', ['company_id'], if_not_exists=True)

    # Expenses
    op.create_index('ix_expenses_company_id',  'expenses',  ['company_id'], if_not_exists=True)
    op.create_index('ix_expenses_created_at',  'expenses',  ['created_at'], if_not_exists=True)

    # Batches (FIFO)
    op.create_index('ix_batches_product_id',   'batches', ['product_id'],   if_not_exists=True)
    op.create_index('ix_batches_company_id',   'batches', ['company_id'],   if_not_exists=True)
    op.create_index('ix_batches_warehouse_id', 'batches', ['warehouse_id'], if_not_exists=True)


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
