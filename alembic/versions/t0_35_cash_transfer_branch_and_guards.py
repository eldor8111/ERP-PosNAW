"""T0.35 — kassalararo o'tkazma: filial snapshot, CHECK cheklovlar va ikki martalik harakatdan himoya

Revision ID: t0_35
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 't0_35'
down_revision: Union[str, None] = 't0_33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # cash_transfers uchun create_table migratsiyasi yo'q (jadval create_all bilan yaratilgan) — borligini tekshiramiz
    if not sa.inspect(bind).has_table("cash_transfers"):
        return

    op.execute(
        "ALTER TABLE cash_transfers "
        "ADD COLUMN IF NOT EXISTS sender_branch_id INTEGER REFERENCES branches(id), "
        "ADD COLUMN IF NOT EXISTS receiver_branch_id INTEGER REFERENCES branches(id)"
    )

    # Eski qatorlar uchun filial snapshot (kassaning hozirgi filialidan)
    op.execute(
        "UPDATE cash_transfers ct SET sender_branch_id = w.branch_id "
        "FROM wallets w WHERE w.id = ct.sender_wallet_id AND ct.sender_branch_id IS NULL"
    )
    op.execute(
        "UPDATE cash_transfers ct SET receiver_branch_id = w.branch_id "
        "FROM wallets w WHERE w.id = ct.receiver_wallet_id AND ct.receiver_branch_id IS NULL"
    )

    # NOT VALID: eski buzilgan qatorlar (manfiy summa) bo'lishi mumkin — yangi qatorlarga amal qiladi;
    # VALIDATE CONSTRAINT ni eski qatorlarni qo'lda tozalagandan keyin bajaring.
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cash_transfers_amount_pos') THEN
            ALTER TABLE cash_transfers ADD CONSTRAINT ck_cash_transfers_amount_pos CHECK (amount > 0) NOT VALID;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cash_transfers_distinct_wallets') THEN
            ALTER TABLE cash_transfers ADD CONSTRAINT ck_cash_transfers_distinct_wallets
              CHECK (sender_wallet_id <> receiver_wallet_id) NOT VALID;
          END IF;
        END $$;
    """)

    # Ikki martalik harakatdan DB himoyasi — faqat takrorlar bo'lmasa
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM kassa_movements
                     WHERE reference_type IN ('transfer_out','transfer_in','transfer_rejected')
                     GROUP BY wallet_id, reference_type, reference_id, direction HAVING count(*) > 1) THEN
            RAISE NOTICE 'ux_kassa_mv_transfer_ref yaratilmadi: takroriy transfer harakatlari bor (qo''lda tekshiring)';
          ELSE
            CREATE UNIQUE INDEX IF NOT EXISTS ux_kassa_mv_transfer_ref
              ON kassa_movements (wallet_id, reference_type, reference_id, direction)
              WHERE reference_type IN ('transfer_out','transfer_in','transfer_rejected');
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_kassa_mv_transfer_ref")
    op.execute("ALTER TABLE cash_transfers DROP CONSTRAINT IF EXISTS ck_cash_transfers_distinct_wallets")
    op.execute("ALTER TABLE cash_transfers DROP CONSTRAINT IF EXISTS ck_cash_transfers_amount_pos")
    op.execute(
        "ALTER TABLE cash_transfers DROP COLUMN IF EXISTS receiver_branch_id, "
        "DROP COLUMN IF EXISTS sender_branch_id"
    )
