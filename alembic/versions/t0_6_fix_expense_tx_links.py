"""T0.6 — xarajat tranzaksiyalarini to'g'rilash: company_id, reference_id va noto'g'ri filial

Revision ID: t0_6
Revises:

Sxema o'zgarmaydi, faqat ma'lumot to'g'rilanadi. Hammasi idempotent:
1. `expense_fix_audit` jadvali (filial tuzatishlari jurnali, downgrade uchun).
2. `transactions.company_id` — xarajat tranzaksiyalarida kassaning korxonasidan to'ldiriladi.
3. `transactions.reference_id` — faqat 1:1 mos kelganda (summa, filial, kassa, 5 soniya) bog'lanadi.
   Ikki ma'noli nomzodlar tegilmaydi, soni logga chiqadi.
4. Begona korxona filialiga yozilgan xarajatlar: kassa filiali (o'z korxonasiniki bo'lsa),
   aks holda korxonaning eng kichik id li faol filiali. Avval auditga yoziladi.

DIQQAT (FIN-07): 4-qadam avtomatik filial tuzatishi. Deploydan oldin quyidagi tanlovni
qo'lda ko'rib chiqing:
    SELECT e.id, e.company_id, e.branch_id, b.company_id AS branch_company
    FROM expenses e LEFT JOIN branches b ON b.id = e.branch_id
    WHERE e.company_id IS NOT NULL AND b.company_id IS DISTINCT FROM e.company_id;
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 't0_6'
down_revision: Union[str, None] = 't0_4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MATCH_WINDOW_SEC = 5  # reference_id bog'lashda vaqt farqi chegarasi


def _log(msg: str) -> None:
    print(f"[t0_6] {msg}")


def _seconds_between(a, b) -> float:
    """Ikki datetime (yoki ISO satr) orasidagi farq, soniyada."""
    from datetime import datetime
    if isinstance(a, str):
        a = datetime.fromisoformat(a)
    if isinstance(b, str):
        b = datetime.fromisoformat(b)
    if a is None or b is None:
        return float("inf")
    if a.tzinfo is not None and b.tzinfo is None:
        a = a.replace(tzinfo=None)
    if b.tzinfo is not None and a.tzinfo is None:
        b = b.replace(tzinfo=None)
    return abs((a - b).total_seconds())


def _step1_audit_table(bind) -> None:
    bind.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS expense_fix_audit ("
        "expense_id INTEGER, old_branch_id INTEGER, new_branch_id INTEGER, "
        "fixed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    ))


def _step2_company_from_wallet(bind) -> int:
    """transactions.company_id — kassa orqali. wallet_id NULL qatorlar tegilmaydi
    (ularning branch_id ishonchsiz: id=1)."""
    res = bind.execute(sa.text(
        "UPDATE transactions SET company_id = ("
        "  SELECT w.company_id FROM wallets w WHERE w.id = transactions.wallet_id) "
        "WHERE reference_type = 'expense' AND company_id IS NULL AND wallet_id IS NOT NULL "
        "AND EXISTS (SELECT 1 FROM wallets w2 WHERE w2.id = transactions.wallet_id)"
    ))
    return res.rowcount if res.rowcount is not None else 0


def _step3_link_reference_id(bind) -> tuple[int, int]:
    """reference_id ni faqat 1:1 mos kelganda bog'laydi. (bog'langan, ikki ma'noli) qaytaradi."""
    txs = bind.execute(sa.text(
        "SELECT id, amount, branch_id, wallet_id, company_id, created_at FROM transactions "
        "WHERE reference_type = 'expense' AND reference_id IS NULL AND type = 'expense'"
    )).fetchall()
    if not txs:
        return 0, 0
    exps = bind.execute(sa.text(
        "SELECT id, amount, branch_id, wallet_id, company_id, created_at FROM expenses"
    )).fetchall()

    def _amt(v) -> str:
        return f"{float(v or 0):.2f}"

    # Tez qidiruv: (summa, filial, kassa) → xarajatlar
    by_key: dict = {}
    for e in exps:
        key = (_amt(e.amount), e.branch_id, e.wallet_id)
        by_key.setdefault(key, []).append(e)

    tx_cands: dict = {}   # tx.id → [expense id]
    exp_cands: dict = {}  # expense.id → [tx id]
    tx_by_id = {}
    exp_by_id = {}
    for t in txs:
        tx_by_id[t.id] = t
        for e in by_key.get((_amt(t.amount), t.branch_id, t.wallet_id), []):
            if _seconds_between(t.created_at, e.created_at) < MATCH_WINDOW_SEC:
                tx_cands.setdefault(t.id, []).append(e.id)
                exp_cands.setdefault(e.id, []).append(t.id)
                exp_by_id[e.id] = e

    linked = 0
    ambiguous = 0
    for tid, eids in tx_cands.items():
        if len(eids) != 1 or len(exp_cands.get(eids[0], [])) != 1:
            ambiguous += 1
            continue
        e = exp_by_id[eids[0]]
        t = tx_by_id[tid]
        bind.execute(sa.text(
            "UPDATE transactions SET reference_id = :eid, company_id = COALESCE(company_id, :cid) WHERE id = :tid"
        ), {"eid": e.id, "cid": e.company_id if t.company_id is None else t.company_id, "tid": tid})
        linked += 1
    return linked, ambiguous


def _step4_fix_branches(bind) -> tuple[int, int]:
    """Begona filialli xarajatlar: auditga yozib, filialni tuzatadi. (tuzatildi, tuzatib bo'lmadi) qaytaradi."""
    bad = bind.execute(sa.text(
        "SELECT e.id, e.company_id, e.branch_id, e.wallet_id FROM expenses e "
        "LEFT JOIN branches b ON b.id = e.branch_id "
        "WHERE e.company_id IS NOT NULL AND (b.company_id IS NULL OR b.company_id <> e.company_id)"
    )).fetchall()
    fixed = 0
    skipped = 0
    for e in bad:
        new_branch_id = None
        if e.wallet_id:
            row = bind.execute(sa.text(
                "SELECT b.id FROM wallets w JOIN branches b ON b.id = w.branch_id "
                "WHERE w.id = :wid AND b.company_id = :cid"
            ), {"wid": e.wallet_id, "cid": e.company_id}).fetchone()
            if row:
                new_branch_id = row[0]
        if new_branch_id is None:
            row = bind.execute(sa.text(
                "SELECT id FROM branches WHERE company_id = :cid AND (is_active IS NULL OR is_active = :t) "
                "ORDER BY id ASC LIMIT 1"
            ), {"cid": e.company_id, "t": True}).fetchone()
            if row:
                new_branch_id = row[0]
        if new_branch_id is None or new_branch_id == e.branch_id:
            skipped += 1
            continue
        bind.execute(sa.text(
            "INSERT INTO expense_fix_audit (expense_id, old_branch_id, new_branch_id) VALUES (:eid, :old, :new)"
        ), {"eid": e.id, "old": e.branch_id, "new": new_branch_id})
        bind.execute(sa.text("UPDATE expenses SET branch_id = :new WHERE id = :eid"),
                     {"new": new_branch_id, "eid": e.id})
        bind.execute(sa.text(
            "UPDATE transactions SET branch_id = :new WHERE reference_type = 'expense' AND reference_id = :eid"
        ), {"new": new_branch_id, "eid": e.id})
        fixed += 1
    return fixed, skipped


def upgrade() -> None:
    bind = op.get_bind()
    _step1_audit_table(bind)
    n2 = _step2_company_from_wallet(bind)
    _log(f"company_id kassadan to'ldirildi: {n2}")
    linked, ambiguous = _step3_link_reference_id(bind)
    _log(f"reference_id bog'landi: {linked}, ikki ma'noli (tegilmadi): {ambiguous}")
    fixed, skipped = _step4_fix_branches(bind)
    _log(f"filial tuzatildi: {fixed}, filial topilmadi (tegilmadi): {skipped}")


def downgrade() -> None:
    """expenses.branch_id auditdagi eski qiymatga qaytadi (har xarajat uchun eng birinchi yozuv).
    company_id/reference_id to'ldirilishi qaytarilmaydi."""
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT expense_id, old_branch_id FROM expense_fix_audit ORDER BY fixed_at ASC, rowid ASC"
        if bind.dialect.name == "sqlite" else
        "SELECT expense_id, old_branch_id FROM expense_fix_audit ORDER BY fixed_at ASC"
    )).fetchall()
    first: dict = {}
    for r in rows:
        first.setdefault(r.expense_id, r.old_branch_id)
    for eid, old in first.items():
        if old is None:
            continue
        exists = bind.execute(sa.text("SELECT 1 FROM branches WHERE id = :b"), {"b": old}).fetchone()
        if not exists:
            continue
        bind.execute(sa.text("UPDATE expenses SET branch_id = :b WHERE id = :e"), {"b": old, "e": eid})
    bind.execute(sa.text("DELETE FROM expense_fix_audit"))
