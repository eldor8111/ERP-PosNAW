"""T4.6 — filial amallari uchun tasdiqlash qoidalari va so'rovlari

- `approval_rules`: rol/filial bo'yicha limitlar (chegirma, narx tushirish, xarajat, qaytarish, sotuvni o'chirish).
- `approval_requests`: bir martalik tasdiq so'rovlari (pending/approved/rejected/expired/used).
- `expenses`: `status` (default 'approved'), `created_by`, `approval_request_id`.
- Eski `expenses.approved_by` aslida yaratuvchi edi: `created_by` ga ko'chiriladi, `approved_by` NULL ("avto-tasdiq").
- Default qoidalar yaratilmaydi — qoidasiz korxonalar uchun xatti-harakat o'zgarmaydi.

Revision ID: t4_6
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't4_6'
down_revision: Union[str, None] = 't4_4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS approval_rules (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            branch_id INTEGER REFERENCES branches(id),
            action_type VARCHAR(20) NOT NULL,
            role VARCHAR(30),
            threshold_percent NUMERIC(5,2),
            threshold_amount NUMERIC(20,2),
            mode VARCHAR(20) NOT NULL DEFAULT 'require_approval',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_approval_rules_id ON approval_rules(id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_approval_rules_company_action "
        "ON approval_rules(company_id, action_type, is_active)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS approval_requests (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            branch_id INTEGER REFERENCES branches(id),
            action_type VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            requested_by INTEGER NOT NULL REFERENCES users(id),
            decided_by INTEGER REFERENCES users(id),
            amount NUMERIC(20,2),
            payload JSON,
            payload_hash VARCHAR(64) NOT NULL,
            reason TEXT,
            decision_note TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            decided_at TIMESTAMP,
            expires_at TIMESTAMP,
            used_at TIMESTAMP,
            reference_type VARCHAR(30),
            reference_id INTEGER,
            CONSTRAINT ck_approval_req_status CHECK (status IN ('pending','approved','rejected','expired','used'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_approval_requests_id ON approval_requests(id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_approval_req_company_status "
        "ON approval_requests(company_id, status, created_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_approval_req_branch ON approval_requests(branch_id)")

    op.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'approved'")
    op.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id)")
    op.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS approval_request_id INTEGER REFERENCES approval_requests(id)")

    # Eski approved_by aslida yaratuvchi edi: created_by ga ko'chirib, approved_by ni tozalaymiz.
    # Qayta ishga tushirilsa xavfsiz: created_by to'ldirilgan qatorlarga tegilmaydi.
    op.execute("UPDATE expenses SET created_by = approved_by WHERE created_by IS NULL AND approved_by IS NOT NULL")
    op.execute("UPDATE expenses SET approved_by = NULL WHERE created_by IS NOT NULL AND approved_by = created_by")


def downgrade() -> None:
    # approved_by ni created_by dan tiklaymiz (eski semantika: yaratuvchi)
    op.execute("UPDATE expenses SET approved_by = created_by WHERE approved_by IS NULL AND created_by IS NOT NULL")
    op.execute("ALTER TABLE expenses DROP COLUMN IF EXISTS approval_request_id")
    op.execute("ALTER TABLE expenses DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE expenses DROP COLUMN IF EXISTS status")
    op.execute("DROP TABLE IF EXISTS approval_requests")
    op.execute("DROP TABLE IF EXISTS approval_rules")
