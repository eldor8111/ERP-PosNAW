"""sync_missing_models

Revision ID: df9132535f4b
Revises: 4d0797e31e56
Create Date: 2026-06-06 14:34:52.056311

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = 'df9132535f4b'
down_revision: Union[str, None] = '4d0797e31e56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name):
    conn = op.get_bind()
    return inspect(conn).has_table(name)


def _column_exists(table, column):
    conn = op.get_bind()
    cols = [c['name'] for c in inspect(conn).get_columns(table)]
    return column in cols


def _index_exists(name, table):
    conn = op.get_bind()
    idxs = [i['name'] for i in inspect(conn).get_indexes(table)]
    return name in idxs


def _constraint_exists(name, table):
    conn = op.get_bind()
    try:
        uqs = [u['name'] for u in inspect(conn).get_unique_constraints(table)]
        fks = [f['name'] for f in inspect(conn).get_foreign_keys(table)]
        return name in uqs or name in fks
    except Exception:
        return False


def upgrade() -> None:
    conn = op.get_bind()

    # --- Create tables (IF NOT EXISTS) ---
    if not _table_exists('bin_locations'):
        op.create_table('bin_locations',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('code', sa.String(length=50), nullable=False),
            sa.Column('label', sa.String(length=100), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_bin_locations_code'), 'bin_locations', ['code'], unique=True)
        op.create_index(op.f('ix_bin_locations_id'), 'bin_locations', ['id'], unique=False)

    if not _table_exists('purchase_orders'):
        op.create_table('purchase_orders',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('number', sa.String(length=30), nullable=False),
            sa.Column('supplier_id', sa.Integer(), nullable=False),
            sa.Column('warehouse_id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=True),
            sa.Column('status', sa.Enum('draft', 'sent', 'partial', 'received', 'cancelled', name='postatus'), nullable=True),
            sa.Column('total_amount', sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column('paid_amount', sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column('discount_amount', sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('expected_date', sa.DateTime(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id']),
            sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_purchase_orders_id'), 'purchase_orders', ['id'], unique=False)
        op.create_index(op.f('ix_purchase_orders_number'), 'purchase_orders', ['number'], unique=True)

    if not _table_exists('stock_transfers'):
        op.create_table('stock_transfers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('number', sa.String(length=30), nullable=False),
            sa.Column('from_warehouse_id', sa.Integer(), nullable=False),
            sa.Column('to_warehouse_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.Enum('pending', 'in_transit', 'received', 'cancelled', name='transferstatus'), nullable=True),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=False),
            sa.Column('confirmed_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('confirmed_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['confirmed_by'], ['users.id']),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.ForeignKeyConstraint(['from_warehouse_id'], ['warehouses.id']),
            sa.ForeignKeyConstraint(['to_warehouse_id'], ['warehouses.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_stock_transfers_id'), 'stock_transfers', ['id'], unique=False)
        op.create_index(op.f('ix_stock_transfers_number'), 'stock_transfers', ['number'], unique=True)

    if not _table_exists('wallets'):
        op.create_table('wallets',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('type', sa.String(length=20), nullable=False),
            sa.Column('balance', sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('branch_id', sa.Integer(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            sa.Column('is_open', sa.Boolean(), nullable=True),
            sa.Column('opening_balance', sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column('opened_by', sa.Integer(), nullable=True),
            sa.Column('closed_by', sa.Integer(), nullable=True),
            sa.Column('opened_at', sa.DateTime(), nullable=True),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
            sa.ForeignKeyConstraint(['closed_by'], ['users.id']),
            sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
            sa.ForeignKeyConstraint(['opened_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_wallets_id'), 'wallets', ['id'], unique=False)

    if not _table_exists('batches'):
        op.create_table('batches',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('warehouse_id', sa.Integer(), nullable=True),
            sa.Column('lot_number', sa.String(length=100), nullable=True),
            sa.Column('manufacture_date', sa.DateTime(), nullable=True),
            sa.Column('expiry_date', sa.DateTime(), nullable=True),
            sa.Column('initial_quantity', sa.Numeric(precision=12, scale=3), nullable=True),
            sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=True),
            sa.Column('purchase_price', sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column('po_id', sa.Integer(), nullable=True),
            sa.Column('company_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
            sa.ForeignKeyConstraint(['po_id'], ['purchase_orders.id']),
            sa.ForeignKeyConstraint(['product_id'], ['products.id']),
            sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_batch_company_product', 'batches', ['company_id', 'product_id', 'quantity'], unique=False)
        op.create_index('ix_batch_product_wh_qty', 'batches', ['product_id', 'warehouse_id', 'quantity'], unique=False)
        op.create_index(op.f('ix_batches_company_id'), 'batches', ['company_id'], unique=False)
        op.create_index(op.f('ix_batches_id'), 'batches', ['id'], unique=False)
        op.create_index(op.f('ix_batches_product_id'), 'batches', ['product_id'], unique=False)
        op.create_index(op.f('ix_batches_warehouse_id'), 'batches', ['warehouse_id'], unique=False)

    if not _table_exists('kassa_sessions'):
        op.create_table('kassa_sessions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('wallet_id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('opened_by', sa.Integer(), nullable=True),
            sa.Column('closed_by', sa.Integer(), nullable=True),
            sa.Column('opened_at', sa.DateTime(), nullable=True),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
            sa.Column('opening_balance', sa.Numeric(precision=14, scale=2), nullable=True),
            sa.Column('closing_summary', sa.JSON(), nullable=True),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.ForeignKeyConstraint(['closed_by'], ['users.id']),
            sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
            sa.ForeignKeyConstraint(['opened_by'], ['users.id']),
            sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_kassa_sessions_id'), 'kassa_sessions', ['id'], unique=False)

    if not _table_exists('payme_transactions'):
        op.create_table('payme_transactions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('payme_id', sa.String(length=25), nullable=False),
            sa.Column('amount', sa.BigInteger(), nullable=False),
            sa.Column('state', sa.Integer(), nullable=False),
            sa.Column('reason', sa.Integer(), nullable=True),
            sa.Column('create_time', sa.BigInteger(), nullable=True),
            sa.Column('perform_time', sa.BigInteger(), nullable=True),
            sa.Column('cancel_time', sa.BigInteger(), nullable=True),
            sa.Column('account_org_code', sa.String(length=20), nullable=True),
            sa.Column('log_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
            sa.ForeignKeyConstraint(['log_id'], ['balance_logs.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_payme_transactions_company_id'), 'payme_transactions', ['company_id'], unique=False)
        op.create_index(op.f('ix_payme_transactions_id'), 'payme_transactions', ['id'], unique=False)
        op.create_index(op.f('ix_payme_transactions_payme_id'), 'payme_transactions', ['payme_id'], unique=True)

    if not _table_exists('po_items'):
        op.create_table('po_items',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('po_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('qty_ordered', sa.Numeric(precision=12, scale=3), nullable=False),
            sa.Column('qty_received', sa.Numeric(precision=12, scale=3), nullable=True),
            sa.Column('unit_cost', sa.Numeric(precision=12, scale=2), nullable=False),
            sa.ForeignKeyConstraint(['po_id'], ['purchase_orders.id']),
            sa.ForeignKeyConstraint(['product_id'], ['products.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_po_items_id'), 'po_items', ['id'], unique=False)

    if not _table_exists('stock_transfer_items'):
        op.create_table('stock_transfer_items',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('transfer_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('target_product_id', sa.Integer(), nullable=True),
            sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=False),
            sa.ForeignKeyConstraint(['product_id'], ['products.id']),
            sa.ForeignKeyConstraint(['target_product_id'], ['products.id']),
            sa.ForeignKeyConstraint(['transfer_id'], ['stock_transfers.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_stock_transfer_items_id'), 'stock_transfer_items', ['id'], unique=False)

    if not _table_exists('wallet_balances'):
        op.create_table('wallet_balances',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('wallet_id', sa.Integer(), nullable=False),
            sa.Column('payment_type', sa.String(length=50), nullable=False),
            sa.Column('balance', sa.Numeric(precision=14, scale=2), nullable=True),
            sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_wallet_balances_id'), 'wallet_balances', ['id'], unique=False)

    if not _table_exists('kassa_movements'):
        op.create_table('kassa_movements',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('wallet_id', sa.Integer(), nullable=True),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('session_id', sa.Integer(), nullable=True),
            sa.Column('direction', sa.String(length=10), nullable=False),
            sa.Column('payment_type', sa.String(length=30), nullable=False),
            sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column('reference_type', sa.String(length=50), nullable=True),
            sa.Column('reference_id', sa.Integer(), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.ForeignKeyConstraint(['session_id'], ['kassa_sessions.id']),
            sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_kassa_movements_id'), 'kassa_movements', ['id'], unique=False)

    if not _table_exists('sale_item_batches'):
        op.create_table('sale_item_batches',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('sale_item_id', sa.Integer(), nullable=False),
            sa.Column('batch_id', sa.Integer(), nullable=False),
            sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=False),
            sa.Column('unit_cost', sa.Numeric(precision=14, scale=2), nullable=False),
            sa.ForeignKeyConstraint(['batch_id'], ['batches.id']),
            sa.ForeignKeyConstraint(['sale_item_id'], ['sale_items.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_sale_item_batches_id'), 'sale_item_batches', ['id'], unique=False)

    # --- Drop platform_settings if exists ---
    if _table_exists('platform_settings'):
        try:
            op.drop_index(op.f('ix_platform_settings_id'), table_name='platform_settings')
        except Exception:
            pass
        try:
            op.drop_index(op.f('ix_platform_settings_key'), table_name='platform_settings')
        except Exception:
            pass
        op.drop_table('platform_settings')

    # --- balance_logs index ---
    if not _index_exists('ix_balance_logs_id', 'balance_logs'):
        op.create_index(op.f('ix_balance_logs_id'), 'balance_logs', ['id'], unique=False)

    # --- companies columns ---
    if not _column_exists('companies', 'tg_bot_token'):
        op.add_column('companies', sa.Column('tg_bot_token', sa.String(length=100), nullable=True))
    if not _column_exists('companies', 'tg_bot_username'):
        op.add_column('companies', sa.Column('tg_bot_username', sa.String(length=100), nullable=True))
    if not _column_exists('companies', 'receipt_templates'):
        op.add_column('companies', sa.Column('receipt_templates', sa.JSON(), nullable=True))

    # --- customers columns ---
    if not _column_exists('customers', 'tg_chat_id'):
        op.add_column('customers', sa.Column('tg_chat_id', sa.String(length=50), nullable=True))
    if not _column_exists('customers', 'discount_percent'):
        op.add_column('customers', sa.Column('discount_percent', sa.Numeric(precision=5, scale=2), nullable=True))
    if not _column_exists('customers', 'card_number'):
        op.add_column('customers', sa.Column('card_number', sa.String(length=20), nullable=True))
    if not _column_exists('customers', 'cashback_percent'):
        op.add_column('customers', sa.Column('cashback_percent', sa.Numeric(precision=5, scale=2), nullable=True))
    if not _column_exists('customers', 'bonus_balance'):
        op.add_column('customers', sa.Column('bonus_balance', sa.Numeric(precision=14, scale=2), nullable=True))
    if not _column_exists('customers', 'total_spent'):
        op.add_column('customers', sa.Column('total_spent', sa.Numeric(precision=14, scale=2), nullable=True))

    # customers indexes
    try:
        op.drop_index(op.f('ix_customers_company_id'), table_name='customers')
    except Exception:
        pass
    try:
        op.drop_index(op.f('ix_customers_phone'), table_name='customers')
    except Exception:
        pass
    if not _index_exists('ix_customers_phone', 'customers'):
        op.create_index(op.f('ix_customers_phone'), 'customers', ['phone'], unique=False)
    if not _index_exists('ix_customers_card_number', 'customers'):
        op.create_index(op.f('ix_customers_card_number'), 'customers', ['card_number'], unique=False)
    if not _index_exists('ix_customers_tg_chat_id', 'customers'):
        op.create_index(op.f('ix_customers_tg_chat_id'), 'customers', ['tg_chat_id'], unique=False)

    if not _constraint_exists('uq_company_customer_card_number', 'customers'):
        try:
            op.create_unique_constraint('uq_company_customer_card_number', 'customers', ['company_id', 'card_number'])
        except Exception:
            pass
    if not _constraint_exists('uq_company_customer_phone', 'customers'):
        try:
            op.create_unique_constraint('uq_company_customer_phone', 'customers', ['company_id', 'phone'])
        except Exception:
            pass
    if not _constraint_exists('uq_company_customer_tg_chat_id', 'customers'):
        try:
            op.create_unique_constraint('uq_company_customer_tg_chat_id', 'customers', ['company_id', 'tg_chat_id'])
        except Exception:
            pass

    # --- expenses ---
    if not _column_exists('expenses', 'wallet_id'):
        op.add_column('expenses', sa.Column('wallet_id', sa.Integer(), nullable=True))
    try:
        op.drop_index(op.f('ix_expenses_company_id'), table_name='expenses')
    except Exception:
        pass
    try:
        op.drop_index(op.f('ix_expenses_created_at'), table_name='expenses')
    except Exception:
        pass
    if _table_exists('wallets') and _column_exists('expenses', 'wallet_id'):
        try:
            op.create_foreign_key(None, 'expenses', 'wallets', ['wallet_id'], ['id'])
        except Exception:
            pass

    # --- products columns ---
    if not _column_exists('products', 'brand'):
        op.add_column('products', sa.Column('brand', sa.String(length=200), nullable=True))
    if not _column_exists('products', 'customer_id'):
        op.add_column('products', sa.Column('customer_id', sa.Integer(), nullable=True))

    # products indexes
    for idx in ['ix_products_category_id', 'ix_products_company_id', 'ix_products_is_deleted',
                'ix_products_status', 'ix_products_barcode', 'ix_products_sku']:
        try:
            op.drop_index(op.f(idx), table_name='products')
        except Exception:
            pass

    if not _index_exists('ix_products_barcode', 'products'):
        op.create_index(op.f('ix_products_barcode'), 'products', ['barcode'], unique=False)
    if not _index_exists('ix_products_sku', 'products'):
        op.create_index(op.f('ix_products_sku'), 'products', ['sku'], unique=False)
    if not _index_exists('ix_product_company_name', 'products'):
        op.create_index('ix_product_company_name', 'products', ['company_id', 'name'], unique=False)
    if not _index_exists('ix_product_company_status_deleted', 'products'):
        op.create_index('ix_product_company_status_deleted', 'products', ['company_id', 'status', 'is_deleted'], unique=False)

    if _column_exists('products', 'customer_id'):
        try:
            op.create_foreign_key(None, 'products', 'customers', ['customer_id'], ['id'])
        except Exception:
            pass

    # --- sale_items indexes ---
    try:
        op.drop_index(op.f('ix_sale_items_product_id'), table_name='sale_items')
    except Exception:
        pass
    try:
        op.drop_index(op.f('ix_sale_items_sale_id'), table_name='sale_items')
    except Exception:
        pass
    if not _index_exists('ix_sale_item_product_id', 'sale_items'):
        op.create_index('ix_sale_item_product_id', 'sale_items', ['product_id'], unique=False)
    if not _index_exists('ix_sale_item_sale_id', 'sale_items'):
        op.create_index('ix_sale_item_sale_id', 'sale_items', ['sale_id'], unique=False)

    # --- sale_payments ---
    if not _index_exists('ix_sale_payments_id', 'sale_payments'):
        op.create_index(op.f('ix_sale_payments_id'), 'sale_payments', ['id'], unique=False)
    try:
        op.drop_constraint(op.f('sale_payments_sale_id_fkey'), 'sale_payments', type_='foreignkey')
    except Exception:
        pass
    try:
        op.create_foreign_key(None, 'sale_payments', 'sales', ['sale_id'], ['id'])
    except Exception:
        pass

    # --- sales indexes ---
    for idx in ['ix_sales_cashier_id', 'ix_sales_company_created', 'ix_sales_company_id',
                'ix_sales_created_at', 'ix_sales_customer_id', 'ix_sales_status', 'ix_sales_warehouse_id']:
        try:
            op.drop_index(op.f(idx), table_name='sales')
        except Exception:
            pass
    if not _index_exists('ix_sale_company_created', 'sales'):
        op.create_index('ix_sale_company_created', 'sales', ['company_id', 'created_at'], unique=False)
    if not _index_exists('ix_sale_company_status', 'sales'):
        op.create_index('ix_sale_company_status', 'sales', ['company_id', 'status'], unique=False)

    # --- stock_levels ---
    if not _column_exists('stock_levels', 'warehouse_id'):
        op.add_column('stock_levels', sa.Column('warehouse_id', sa.Integer(), nullable=True))
    try:
        op.drop_constraint(op.f('stock_levels_product_id_key'), 'stock_levels', type_='unique')
    except Exception:
        pass
    if not _index_exists('ix_stock_levels_warehouse_id', 'stock_levels'):
        op.create_index(op.f('ix_stock_levels_warehouse_id'), 'stock_levels', ['warehouse_id'], unique=False)
    if not _constraint_exists('uq_stock_product_warehouse', 'stock_levels'):
        try:
            op.create_unique_constraint('uq_stock_product_warehouse', 'stock_levels', ['product_id', 'warehouse_id'])
        except Exception:
            pass
    try:
        op.create_foreign_key(None, 'stock_levels', 'warehouses', ['warehouse_id'], ['id'])
    except Exception:
        pass

    # --- suppliers ---
    if not _index_exists('ix_suppliers_id', 'suppliers'):
        op.create_index(op.f('ix_suppliers_id'), 'suppliers', ['id'], unique=False)
    try:
        op.create_foreign_key(None, 'suppliers', 'companies', ['company_id'], ['id'])
    except Exception:
        pass

    # --- tariffs ---
    if not _column_exists('tariffs', 'bhm_percent'):
        op.add_column('tariffs', sa.Column('bhm_percent', sa.Float(), nullable=True))
    if not _index_exists('ix_tariffs_id', 'tariffs'):
        op.create_index(op.f('ix_tariffs_id'), 'tariffs', ['id'], unique=False)

    # --- transactions ---
    if not _column_exists('transactions', 'wallet_id'):
        op.add_column('transactions', sa.Column('wallet_id', sa.Integer(), nullable=True))
    try:
        op.alter_column('transactions', 'branch_id', existing_type=sa.INTEGER(), nullable=True)
    except Exception:
        pass
    try:
        op.create_foreign_key(None, 'transactions', 'wallets', ['wallet_id'], ['id'])
    except Exception:
        pass

    # --- user_companies ---
    if not _index_exists('ix_user_companies_id', 'user_companies'):
        op.create_index(op.f('ix_user_companies_id'), 'user_companies', ['id'], unique=False)


def downgrade() -> None:
    # Downgrade is left intentionally minimal for safety
    pass
