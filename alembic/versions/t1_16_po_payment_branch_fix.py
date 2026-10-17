"""T1.16 — xarid (PO) to'lovi tranzaksiyalarining filialini ombor filialiga moslash

Yangi ustun/indeks yo'q (`po_items.variant_id` bazada allaqachon bor). Faqat ma'lumot tuzatiladi:

1. `transactions_branch_backup_t116` — `reference_type='purchase_order'` tranzaksiyalarining eski
   `branch_id` si zaxiralanadi (downgrade uchun).
2. `purchase_order` tranzaksiyalarining `branch_id` si xarid ombori filialiga (`warehouses.branch_id`)
   o'tkaziladi — faqat shu korxona doirasida va filial shu korxonaniki bo'lsa.

`supplier_payment` va `return_to_supplier` tranzaksiyalariga tegilmaydi (eski qatorda ombor saqlanmagan).

Diqqat: tarixiy filial P&L hisobotlari (Transaction.branch_id asosida) migratsiyadan keyin o'zgaradi.

Revision ID: t1_16
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_16'
down_revision: Union[str, None] = 't1_14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS transactions_branch_backup_t116 AS
        SELECT id, branch_id AS old_branch_id
        FROM transactions
        WHERE reference_type = 'purchase_order'
    """)
    op.execute("""
        UPDATE transactions t SET branch_id = w.branch_id
        FROM purchase_orders po
        JOIN warehouses w ON w.id = po.warehouse_id
        JOIN branches b ON b.id = w.branch_id
        WHERE t.reference_type = 'purchase_order'
          AND t.reference_id = po.id
          AND t.company_id = po.company_id
          AND w.branch_id IS NOT NULL
          AND b.company_id = po.company_id
          AND t.branch_id IS DISTINCT FROM w.branch_id
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE transactions t SET branch_id = bk.old_branch_id
        FROM transactions_branch_backup_t116 bk
        WHERE t.id = bk.id
    """)
    op.execute("DROP TABLE IF EXISTS transactions_branch_backup_t116")
