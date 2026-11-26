"""R1.1/R1.2/R1.4: restoran menyusi — products.item_kind, products.station_id, categories.station_id,
boms (output_qty, output_weight_g, cooking_time_min, instructions, version, created_by),
bom_items (gross_qty, net_qty, loss_cold_pct, loss_hot_pct).

Additiv va takroriy xavfsiz: mavjud mahsulotlar 'goods' bo'ladi, mavjud retsepturalar o'zgarmaydi.

Revision ID: r1_1
Revises: r0_1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r1_1'
down_revision: Union[str, Sequence[str], None] = 'r0_1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _insp():
    from alembic import context
    if context.is_offline_mode():
        return None
    return sa.inspect(op.get_bind())


def _cols(insp, table):
    if insp is None:
        return set()
    return {c['name'] for c in insp.get_columns(table)}


def _checks(insp, table):
    if insp is None:
        return set()
    try:
        return {c['name'] for c in insp.get_check_constraints(table)}
    except NotImplementedError:
        return set()


def _add(insp, table, column):
    if column.name not in _cols(insp, table):
        op.add_column(table, column)


def upgrade() -> None:
    insp = _insp()

    _add(insp, 'products', sa.Column('item_kind', sa.String(20), nullable=False, server_default='goods'))
    _add(insp, 'products', sa.Column('station_id', sa.Integer(),
                                     sa.ForeignKey('kitchen_stations.id', ondelete='SET NULL',
                                                   name='fk_products_station_id'), nullable=True))
    if 'ck_products_item_kind' not in _checks(insp, 'products'):
        op.create_check_constraint('ck_products_item_kind', 'products',
                                   "item_kind IN ('goods','dish','semi','ingredient','modifier')")
    _add(insp, 'categories', sa.Column('station_id', sa.Integer(),
                                       sa.ForeignKey('kitchen_stations.id', ondelete='SET NULL',
                                                     name='fk_categories_station_id'), nullable=True))

    _add(insp, 'boms', sa.Column('output_qty', sa.Numeric(14, 3), nullable=True))
    _add(insp, 'boms', sa.Column('output_weight_g', sa.Numeric(10, 1), nullable=True))
    _add(insp, 'boms', sa.Column('cooking_time_min', sa.Integer(), nullable=True))
    _add(insp, 'boms', sa.Column('instructions', sa.Text(), nullable=True))
    _add(insp, 'boms', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    _add(insp, 'boms', sa.Column('created_by', sa.Integer(),
                                 sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_boms_created_by'),
                                 nullable=True))

    _add(insp, 'bom_items', sa.Column('gross_qty', sa.Numeric(14, 4), nullable=True))
    _add(insp, 'bom_items', sa.Column('net_qty', sa.Numeric(14, 4), nullable=True))
    _add(insp, 'bom_items', sa.Column('loss_cold_pct', sa.Numeric(5, 2), nullable=True))
    _add(insp, 'bom_items', sa.Column('loss_hot_pct', sa.Numeric(5, 2), nullable=True))

    # Restoran menyusi ro'yxati tez ochilsin
    if insp is None or 'ix_products_company_item_kind' not in {i['name'] for i in insp.get_indexes('products')}:
        op.create_index('ix_products_company_item_kind', 'products', ['company_id', 'item_kind'])


def downgrade() -> None:
    op.drop_index('ix_products_company_item_kind', table_name='products')
    for col in ('loss_hot_pct', 'loss_cold_pct', 'net_qty', 'gross_qty'):
        op.drop_column('bom_items', col)
    op.drop_constraint('fk_boms_created_by', 'boms', type_='foreignkey')
    for col in ('created_by', 'version', 'instructions', 'cooking_time_min', 'output_weight_g', 'output_qty'):
        op.drop_column('boms', col)
    op.drop_constraint('fk_categories_station_id', 'categories', type_='foreignkey')
    op.drop_column('categories', 'station_id')
    op.drop_constraint('ck_products_item_kind', 'products', type_='check')
    op.drop_constraint('fk_products_station_id', 'products', type_='foreignkey')
    op.drop_column('products', 'station_id')
    op.drop_column('products', 'item_kind')
