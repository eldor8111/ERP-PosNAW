"""T2.8 — kassa balansi va to'lovlar hisobotlari uchun indekslar

Faqat indekslar (ma'lumot o'zgarmaydi). CREATE INDEX CONCURRENTLY tranzaksiyada ishlamaydi,
shuning uchun autocommit_block ichida; IF NOT EXISTS — qayta ishga tushirish xavfsiz.
Migratsiyadan keyin: SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;  (bo'sh bo'lishi kerak)

`transactions (company_id, created_at)` va `transactions (reference_type, reference_id)` indekslari
T1.13 da (`ix_transactions_company_created`, `ix_transactions_reference`) allaqachon bor — takrorlanmaydi.
`transactions (wallet_id)` yo'q edi — kassa bo'yicha qidiruv va o'chirishdagi tekshiruvlar uchun qo'shiladi.

Ma'lumot ko'chirish: avtomatik YO'Q. Tarixiy nomuvofiqlikni qo'lda bajaring:
`deploy/find_missing_kassa_movements.py` (dry-run) -> ko'zdan kechirish -> `--apply` ->
`deploy/recalc_wallet_balances.py` (dry-run -> `--apply`). `GET /kassa/reconcile` kesh va jurnal farqini ko'rsatadi.

Revision ID: t2_8
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't2_8'
down_revision: Union[str, None] = 't2_7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    ("ix_km_wallet_ptype_cur_dir", "kassa_movements", "(wallet_id, payment_type, currency, direction)"),
    ("ix_km_reference", "kassa_movements", "(reference_type, reference_id)"),
    ("ix_tx_wallet", "transactions", "(wallet_id)"),
    ("ix_expenses_company_created", "expenses", "(company_id, created_at)"),
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET statement_timeout = 0")
        for name, table, cols in _INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {cols}")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _table, _cols in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
