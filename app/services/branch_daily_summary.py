"""Kunlik hisobot uchun filial kesimi (T2.11).

`branch_day_summary(db, company_id, day)` — har bir filial uchun shu kunning sof tushumi, xarajati,
yopilgan smenalar soni va kassa yopilishidagi kamomad/ortiqchasi. Filialga bog'lanmagan yozuvlar
alohida "Filialsiz" qatorida (faqat ma'lumot bo'lsa) chiqadi, shuning uchun qatorlar yig'indisi butun
korxonaga teng bo'ladi.

Manbalar:
  - tushum: `Sale.branch_id` snapshot'i (T1.9), snapshot'siz eski sotuvlar — ombor filiali bo'yicha
    (`sale_branch_filter`); qaytarishlar ayiriladi;
  - xarajat: `Expense.branch_id` + `created_at` (bekor qilinganlari — `voided_at` — sanalmaydi);
  - smena: `Shift.branch_id` + `closed_at` (status `closed`);
  - kamomad: kun ichida yopilgan `KassaSession.difference_summary` (filial: sessiya filiali, bo'lmasa kassa
    filiali). Eski sessiyalarda (`difference_summary` NULL) ma'lumot yo'q — o'tkazib yuboriladi.
"""
from datetime import date
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.moliya import Expense, KassaSession, Wallet
from app.models.shift import Shift
from app.services.pnl_service import UNASSIGNED_BRANCH
from app.utils.report_utils import (
    _date_range, currency_rate_map, day_sales_summary, sale_branch_filter,
)

UNASSIGNED_LABEL = "Filialsiz"


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _session_diffs(db: Session, company_id: int, start, end) -> dict:
    """{branch_id|None: [kamomad, ortiqcha]} — kun ichida yopilgan kassa sessiyalari (UZS ekvivalentida)."""
    rates = currency_rate_map(db, company_id)
    rows = (
        db.query(KassaSession.difference_summary, KassaSession.branch_id, Wallet.branch_id)
        .outerjoin(Wallet, Wallet.id == KassaSession.wallet_id)
        .filter(
            KassaSession.company_id == company_id,
            KassaSession.status == "closed",
            KassaSession.closed_at >= start,
            KassaSession.closed_at < end,
        )
        .all()
    )
    out: dict = {}
    for diff, sess_branch, wallet_branch in rows:
        if not isinstance(diff, dict) or not diff:
            continue
        bid = sess_branch or wallet_branch
        acc = out.setdefault(bid, [0.0, 0.0])
        for by_cur in diff.values():
            if not isinstance(by_cur, dict):
                continue
            for cur, val in by_cur.items():
                code = (cur or "UZS").upper()
                rate = 1.0 if code == "UZS" else rates.get(code)
                if rate is None:
                    continue     # kursi noma'lum valyuta — UZS ga o'tkazib bo'lmaydi
                v = _f(val) * rate
                if v > 0:
                    acc[0] += v
                elif v < 0:
                    acc[1] += -v
    return out


def branch_day_summary(db: Session, company_id: int, day: date) -> List[dict]:
    """Har filial uchun `day` kunining ko'rsatkichlari.

    Qator: `{branch_id, name, net, expense, shifts_closed, shortage, surplus}`; summalar UZS da.
    Faol filiallar har doim, nofaol filial va "Filialsiz" (`branch_id=None`) — faqat ma'lumot bo'lsa."""
    start, end = _date_range(day, day)

    expenses = dict(
        db.query(Expense.branch_id, func.coalesce(func.sum(func.coalesce(Expense.amount_uzs, Expense.amount)), 0))
        .join(Branch, Branch.id == Expense.branch_id)
        .filter(
            Branch.company_id == company_id,
            Expense.created_at >= start, Expense.created_at < end,
            Expense.voided_at.is_(None),
        )
        .group_by(Expense.branch_id)
        .all()
    )
    shifts = dict(
        db.query(Shift.branch_id, func.count(Shift.id))
        .filter(
            Shift.company_id == company_id, Shift.status == "closed",
            Shift.closed_at >= start, Shift.closed_at < end,
        )
        .group_by(Shift.branch_id)
        .all()
    )
    diffs = _session_diffs(db, company_id, start, end)

    def _row(branch_id: Optional[int], name: str) -> dict:
        sale_flt = sale_branch_filter(branch_id if branch_id else UNASSIGNED_BRANCH, db, company_id)
        short, surplus = diffs.get(branch_id, [0.0, 0.0])
        return {
            "branch_id": branch_id,
            "name": name,
            "net": _f(day_sales_summary(db, company_id, day, sale_filter=sale_flt)["net"]),
            "expense": _f(expenses.get(branch_id)),
            "shifts_closed": int(shifts.get(branch_id) or 0),
            "shortage": short,
            "surplus": surplus,
        }

    result = []
    for b in db.query(Branch).filter(Branch.company_id == company_id).order_by(Branch.id).all():
        row = _row(b.id, b.name or "")
        active = b.is_active is not False
        if active or any(row[k] for k in ("net", "expense", "shifts_closed", "shortage", "surplus")):
            result.append(row)

    un = _row(None, UNASSIGNED_LABEL)
    if any(un[k] for k in ("net", "expense", "shifts_closed", "shortage", "surplus")):
        result.append(un)
    return result
