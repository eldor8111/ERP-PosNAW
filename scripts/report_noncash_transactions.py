"""Naqd bo'lmagan to'lov turi bilan yozilgan Transaction'lar hisoboti (T0.29). FAQAT O'QIYDI.

Eski kod qarz (`debt`) va keshbek (`cashback`) qatorlarini ham kassa daromadi (`Transaction`)
sifatida yozar edi — bu haqiqiy pul emas. Yangi kod ularni yozmaydi, hisobotlar esa eski
yozuvlarni hisobga olmaydi. Bu skript bazada qancha shunday yozuv qolganini korxona kesimida
ko'rsatadi (tozalash yoki tekshirish uchun).

Ishlatish (repo ildizidan):
    python scripts/report_noncash_transactions.py
    python scripts/report_noncash_transactions.py --company-id 5
    python scripts/report_noncash_transactions.py --by-type        # tur kesimida ham
"""
import argparse
import os
import sys
from decimal import Decimal

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.database import SessionLocal
from app.models.company import Company
from app.models.moliya import Transaction

NONCASH = ("debt", "cashback")


def main():
    ap = argparse.ArgumentParser(description="payment_type in ('debt','cashback') Transaction'lar soni va summasi")
    ap.add_argument("--company-id", type=int, default=None, help="Faqat shu korxona")
    ap.add_argument("--by-type", action="store_true", help="Korxona va to'lov turi kesimida")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        cols = [Transaction.company_id]
        if args.by_type:
            cols.append(Transaction.payment_type)
        q = db.query(*cols, func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.payment_type.in_(NONCASH),
        )
        if args.company_id:
            q = q.filter(Transaction.company_id == args.company_id)
        rows = q.group_by(*cols).order_by(*cols).all()
        if not rows:
            print("Naqd bo'lmagan (debt/cashback) Transaction yozuvlari topilmadi.")
            return

        names = {c.id: c.name for c in db.query(Company.id, Company.name).all()}
        head = f"{'korxona':>7} {'nomi':<30} " + (f"{'tur':<10} " if args.by_type else "") + f"{'soni':>7} {'summa':>16}"
        print(head)
        total_n, total_sum = 0, Decimal("0")
        for row in rows:
            if args.by_type:
                cid, ptype, n, s = row
            else:
                cid, n, s = row
                ptype = None
            name = (names.get(cid) or "-")[:30] if cid else "(korxonasiz)"
            line = f"{cid or '-':>7} {name:<30} " + (f"{ptype or '-':<10} " if args.by_type else "")
            print(line + f"{int(n):>7} {Decimal(str(s)):>16}")
            total_n += int(n)
            total_sum += Decimal(str(s))
        print(f"\nJami: {total_n} ta yozuv, summa {total_sum}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
