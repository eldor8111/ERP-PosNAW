"""T3.17 — marketplace: tovar ombori va agent to'lovini kassa/filial/tranzaksiyaga bog'lash

Revision ID: t3_17
Revises:

Additiv (hammasi NULL bo'lishi mumkin). `marketplace_*` jadvallari main.py da xom
CREATE TABLE bilan ham yaratiladi, shuning uchun ustun mavjudligi tekshiriladi.
Eski to'lovlar `wallet_id = NULL` bo'lib qoladi ("kassaga bog'lanmagan"); eski tasdiqlangan
tovarlar avtomatik kirimlanmaydi (qo'lda: POST /marketplace-agents/products/{id}/receive).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 't3_17'
down_revision: Union[str, None] = 't3_16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = {
    "marketplace_products": [
        ("warehouse_id", "warehouses", None),
        ("preferred_warehouse_id", "warehouses", None),
    ],
    "marketplace_agent_transactions": [
        ("wallet_id", "wallets", None),
        ("branch_id", "branches", None),
        ("finance_transaction_id", "transactions", "SET NULL"),
    ],
}


def _existing(insp, table: str) -> set:
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    for table, cols in _COLUMNS.items():
        if table not in tables:
            continue
        have = _existing(insp, table)
        for name, ref, ondelete in cols:
            if name in have:
                continue
            fk = sa.ForeignKey(f"{ref}.id", ondelete=ondelete) if ondelete else sa.ForeignKey(f"{ref}.id")
            op.add_column(table, sa.Column(name, sa.Integer(), fk, nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    for table, cols in _COLUMNS.items():
        if table not in tables:
            continue
        have = _existing(insp, table)
        for name, _ref, _ondelete in reversed(cols):
            if name in have:
                op.drop_column(table, name)
