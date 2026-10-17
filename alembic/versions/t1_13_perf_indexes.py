"""T1.13 — transactions/shifts/users/warehouses/wallets/branches/stock_transfers/audit_logs indekslari

CREATE INDEX CONCURRENTLY tranzaksiyada ishlamaydi, shuning uchun autocommit_block ichida.
Migratsiyadan keyin: SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;  (bo'sh bo'lishi kerak)

Revision ID: t1_13b
Revises: t1_13
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_13b'
down_revision: Union[str, None] = 't1_13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    ("ix_transactions_company_created", "transactions", "(company_id, created_at)", False, None),
    ("ix_transactions_company_branch_created", "transactions", "(company_id, branch_id, created_at)", False, None),
    ("ix_transactions_reference", "transactions", "(reference_type, reference_id)", False, None),
    ("ix_shifts_company_branch_opened", "shifts", "(company_id, branch_id, opened_at)", False, None),
    ("ux_shifts_one_open_per_cashier", "shifts", "(cashier_id)", True, "status = 'open'"),
    ("ix_users_company_branch", "users", "(company_id, branch_id)", False, None),
    ("ix_warehouses_company_branch", "warehouses", "(company_id, branch_id)", False, None),
    ("ix_wallets_company_branch", "wallets", "(company_id, branch_id)", False, None),
    ("ix_branches_company_id", "branches", "(company_id)", False, None),
    ("ix_stock_transfers_from_wh", "stock_transfers", "(from_warehouse_id)", False, None),
    ("ix_stock_transfers_to_wh", "stock_transfers", "(to_warehouse_id)", False, None),
    ("ix_audit_logs_company_created", "audit_logs", "(company_id, created_at)", False, None),
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET statement_timeout = 0")
        for name, table, cols, unique, where in _INDEXES:
            sql = (
                f"CREATE {'UNIQUE ' if unique else ''}INDEX CONCURRENTLY IF NOT EXISTS {name} "
                f"ON {table} {cols}"
            )
            if where:
                sql += f" WHERE {where}"
            op.execute(sql)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, *_ in _INDEXES:
            # ix_audit_logs_company_created T1.19 ga tegishli — uni o'sha migratsiya o'chiradi
            if name == "ix_audit_logs_company_created":
                continue
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
