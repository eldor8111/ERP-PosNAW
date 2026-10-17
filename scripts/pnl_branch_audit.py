"""P&L eski va yangi formulasi farqi, korxona/filial kesimida (T2.2). FAQAT O'QIYDI.

ESKI formula (T2.2 dan oldingi `/reports/profit-loss`): tushum/tannarx — sotuv OMBORI filiali bo'yicha
(`Sale.warehouse_id`), xarajat — `Expense.amount` (valyuta o'girilmagan, bekor qilinganlar ham kirgan),
boshqa kirim yo'q.
YANGI formula: `app.services.pnl_service.compute_pnl` — sotuv filiali (`Sale.branch_id` snapshot'i),
xarajat UZS ekvivalentida va bekor qilinmagan, boshqa kirim qo'shiladi.

Har bir korxona uchun butun korxona qatori va har bir filial (hamda filialsiz guruh) qatori chop etiladi:
eski/yangi sof foyda va farq. Hech narsa yozilmaydi (sessiya oxirida rollback).

Ishlatish (repo ildizidan):
    python scripts/pnl_branch_audit.py
    python scripts/pnl_branch_audit.py --company-id 5 --date-from 2025-01-01 --date-to 2025-03-31
    python scripts/pnl_branch_audit.py --only-diff        # faqat farqi bor qatorlar
"""
import argparse
import os
import sys
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.database import SessionLocal
from app.models.branch import Branch
from app.models.company import Company
from app.models.moliya import Expense
from app.models.sale import Sale, SaleItem
from app.services.pnl_service import UNASSIGNED_BRANCH, compute_pnl
from app.utils.report_utils import (
    _date_range, branch_warehouse_ids, doc_sign, item_cost_uzs, return_doc_filter,
    sale_doc_filter, sale_or_return_filter,
)


def old_net_profit(db, cid, start, end, branch_id=None) -> float:
    """T2.2 dan oldingi formula: ombor filiali bo'yicha sotuv, `Expense.amount` (bekor qilinganlar ham)."""
    flt = [Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end]
    wh_ids = branch_warehouse_ids(db, cid, branch_id)
    if wh_ids is not None:
        flt.append(Sale.warehouse_id.in_(wh_ids))

    def _total(doc_filter) -> float:
        return float(db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(*flt, doc_filter).scalar() or 0)

    revenue = _total(sale_doc_filter()) - _total(return_doc_filter())
    cogs = float(
        db.query(func.coalesce(func.sum(doc_sign() * item_cost_uzs()), 0))
        .select_from(SaleItem).join(Sale, Sale.id == SaleItem.sale_id)
        .filter(*flt, sale_or_return_filter()).scalar() or 0
    )
    eq = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.company_id == cid, Expense.created_at >= start, Expense.created_at < end,
    )
    if branch_id == UNASSIGNED_BRANCH:
        eq = eq.filter(Expense.branch_id.is_(None))
    elif branch_id:
        eq = eq.filter(Expense.branch_id == branch_id)
    return revenue - cogs - float(eq.scalar() or 0)


def _row(db, cid, start, end, label, branch_id, only_diff):
    old = round(old_net_profit(db, cid, start, end, branch_id), 2)
    new = round(float(compute_pnl(db, cid, start, end, branch_id)["net_profit"]), 2)
    diff = round(new - old, 2)
    if only_diff and abs(diff) < 0.01:
        return 0, 0.0, 0.0
    print(f"  {label:<34} {old:>18,.2f} {new:>18,.2f} {diff:>+18,.2f}")
    return 1, old, new


def main():
    ap = argparse.ArgumentParser(description="Eski va yangi P&L formulasi farqi (faqat o'qiydi)")
    ap.add_argument("--company-id", type=int, default=None, help="Faqat shu korxona")
    ap.add_argument("--date-from", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    ap.add_argument("--date-to", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    ap.add_argument("--only-diff", action="store_true", help="Faqat farqi bor qatorlar")
    args = ap.parse_args()

    start, end = _date_range(args.date_from, args.date_to)
    db = SessionLocal()
    try:
        q = db.query(Company.id, Company.name).order_by(Company.id)
        if args.company_id:
            q = q.filter(Company.id == args.company_id)
        companies = q.all()
        if not companies:
            print("Korxona topilmadi.")
            return
        print(f"Davr: {args.date_from or 'boshidan'} .. {args.date_to or 'hozirgacha'}")
        for cid, cname in companies:
            print(f"\n[{cid}] {cname}")
            print(f"  {'':<34} {'ESKI sof foyda':>18} {'YANGI sof foyda':>18} {'Farq':>18}")
            _row(db, cid, start, end, "Butun korxona", None, False)
            branches = db.query(Branch.id, Branch.name).filter(Branch.company_id == cid).order_by(Branch.id).all()
            for bid, bname in branches:
                _row(db, cid, start, end, f"Filial #{bid} {(bname or '')[:22]}", bid, args.only_diff)
            _row(db, cid, start, end, "Filialsiz guruh", UNASSIGNED_BRANCH, args.only_diff)
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
