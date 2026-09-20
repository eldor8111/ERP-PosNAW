"""
Bir martalik skript: barcha hamyonlarning Wallet.balance qiymatini
KassaMovement jurnalidan (UZS kirim - UZS chiqim) qayta hisoblab yozadi.

Nega kerak: sotuv tushumi avval Wallet.balance ga qo'shilmasdan, kassa
yopilishidagi inkasso esa ayirilardi ([4.2] tuzatilgunga qadar) - shu
sabab balanslar vaqt o'tishi bilan manfiy tomonga driftlagan.

Ishlatish (server, loyiha ildizida, venv faol):
    python deploy/recalc_wallet_balances.py           # dry-run (faqat ko'rsatadi)
    python deploy/recalc_wallet_balances.py --apply   # haqiqatda yozadi
"""
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, or_  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.moliya import Wallet, KassaMovement  # noqa: E402


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        wallets = db.query(Wallet).order_by(Wallet.id).all()
        print(f"{'ID':>4} | {'Hamyon':<30} | {'Eski balans':>18} | {'Yangi (ledger)':>18} | Farq")
        print("-" * 95)
        changed = 0
        for w in wallets:
            # Faqat UZS (yoki currency ko'rsatilmagan eski yozuvlar) hisobga
            # olinadi - Wallet.balance UZS qiymati sifatida yuritiladi.
            uzs_filter = or_(KassaMovement.currency == "UZS", KassaMovement.currency.is_(None))

            income = db.query(func.coalesce(func.sum(KassaMovement.amount), 0)).filter(
                KassaMovement.wallet_id == w.id,
                KassaMovement.direction == "in",
                uzs_filter,
            ).scalar()
            expense = db.query(func.coalesce(func.sum(KassaMovement.amount), 0)).filter(
                KassaMovement.wallet_id == w.id,
                KassaMovement.direction == "out",
                uzs_filter,
            ).scalar()

            new_balance = Decimal(str(income)) - Decimal(str(expense))
            old_balance = Decimal(str(w.balance or 0))
            diff = new_balance - old_balance

            marker = "  <-- o'zgaradi" if abs(diff) >= Decimal("0.01") else ""
            print(f"{w.id:>4} | {(w.name or ''):<30} | {old_balance:>18,.2f} | {new_balance:>18,.2f} | {diff:>+,.2f}{marker}")

            if apply and abs(diff) >= Decimal("0.01"):
                w.balance = new_balance
                changed += 1

        if apply:
            db.commit()
            print(f"\n{changed} ta hamyon balansi yangilandi (commit qilindi).")
        else:
            print("\nDRY-RUN: hech narsa yozilmadi. Yozish uchun: python deploy/recalc_wallet_balances.py --apply")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
