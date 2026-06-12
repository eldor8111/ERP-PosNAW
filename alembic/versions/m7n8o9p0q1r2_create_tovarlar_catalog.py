"""create_tovarlar_catalog

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-06-12 16:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'm7n8o9p0q1r2'
down_revision: Union[str, None] = 'l6m7n8o9p0q1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tbl(conn, t):
    return conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name=:t)"),
        {"t": t}
    ).scalar()


def _idx(conn, i):
    return conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname=:i)"),
        {"i": i}
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    if not _tbl(conn, 'tovarlar_catalog'):
        op.create_table(
            'tovarlar_catalog',
            sa.Column('id',         sa.Integer(),     primary_key=True, autoincrement=True),
            sa.Column('mxik_code',  sa.String(30),    nullable=False),
            sa.Column('mxik_name',  sa.Text(),        nullable=True),
            sa.Column('barcode',    sa.String(30),    nullable=False),
            sa.Column('unit_name',  sa.String(200),   nullable=True),
            sa.Column('group_name', sa.Text(),        nullable=True),
            sa.Column('lgota_id',   sa.Integer(),     nullable=True),
        )

    if not _idx(conn, 'ix_tovarlar_catalog_barcode'):
        op.create_index('ix_tovarlar_catalog_barcode',   'tovarlar_catalog', ['barcode'],   unique=True)
    if not _idx(conn, 'ix_tovarlar_catalog_mxik_code'):
        op.create_index('ix_tovarlar_catalog_mxik_code', 'tovarlar_catalog', ['mxik_code'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_tovarlar_catalog_mxik_code', table_name='tovarlar_catalog')
    op.drop_index('ix_tovarlar_catalog_barcode',   table_name='tovarlar_catalog')
    op.drop_table('tovarlar_catalog')
