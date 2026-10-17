"""Eski smena inkassatsiyasi yozuvlarini tuzatish (T0.28).

Eski kod smena yopilganda qabul qiluvchi kassaga `Transaction(type='income',
reference_type='shift')` yozar edi — tushum sotuv vaqtida kassir kassasiga allaqachon
yozilgani uchun daromad IKKI MARTA hisoblanardi. Yangi kod inkassatsiyani kassalararo ichki
harakat (`CashTransfer` + `KassaMovement transfer_out/transfer_in`) sifatida yozadi.

Bu skript eski yozuvlarni shu ko'rinishga keltiradi:
  * kassir kassasi (manba) -> qabul qiluvchi kassa (tranzaksiya hamyoni) o'tkazmasi yoziladi;
  * manba kassa balansi kamayadi (qabul qiluvchi balansi eski kod tomonidan allaqachon oshirilgan);
  * eski `income` Transaction o'chiriladi (daromad hisobotlaridan chiqadi).

Ishlatish (repo ildizidan):
    python scripts/reconcile_shift_handover.py                      # dry-run: barcha eski yozuvlar
    python scripts/reconcile_shift_handover.py --company-id 5       # faqat bitta korxona
    python scripts/reconcile_shift_handover.py --apply --shift-ids 12,15,20

`--apply` faqat `--shift-ids` bilan ishlaydi (tasodifan hammasini o'zgartirib yubormaslik uchun).
Manba kassa topilmasa yoki qabul qiluvchi bilan bir xil bo'lsa — yozuv o'tkazib yuboriladi va
ogohlantirish chiqadi (qo'lda ko'rib chiqiladi).
"""
import argparse
import os
import sys
from decimal import Decimal

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.moliya import CashTransfer, KassaMovement, KassaSession, Transaction, Wallet
from app.models.shift import Shift
from app.models.user import User
from app.services.sale_helpers import resolve_cashier_wallet_id


def _note(tx: Transaction) -> str:
    return f"Smena #{tx.reference_id} inkassatsiyasi (reconcile tx #{tx.id})"


def _parse_ids(raw):
    if not raw:
        return set()
    return {int(x) for x in raw.split(",") if x.strip()}


def _load(db, company_id=None, shift_ids=None):
    q = db.query(Transaction).filter(
        Transaction.reference_type == "shift", Transaction.type == "income",
    )
    if company_id:
        q = q.filter(Transaction.company_id == company_id)
    if shift_ids:
        q = q.filter(Transaction.reference_id.in_(sorted(shift_ids)))
    return q.order_by(Transaction.company_id, Transaction.reference_id, Transaction.id).all()


def _session_id(db, wallet_id):
    s = db.query(KassaSession).filter(
        KassaSession.wallet_id == wallet_id, KassaSession.status == "open",
    ).first()
    return s.id if s else None


def _plan_row(db, tx: Transaction):
    """Bitta yozuv uchun manba/qabul qiluvchi kassani aniqlaydi; (row, warning) qaytaradi."""
    shift = db.get(Shift, tx.reference_id) if tx.reference_id else None
    target = db.get(Wallet, tx.wallet_id) if tx.wallet_id else None
    cashier = db.get(User, shift.cashier_id) if shift else None
    source = None
    if cashier is not None:
        src_id = resolve_cashier_wallet_id(db, cashier)
        source = db.get(Wallet, src_id) if src_id else None
    warn = None
    if shift is None:
        warn = "smena topilmadi"
    elif target is None:
        warn = "qabul qiluvchi kassa (wallet_id) yo'q"
    elif source is None:
        warn = "kassir kassasi aniqlanmadi"
    elif source.id == target.id:
        warn = "manba va qabul qiluvchi kassa bir xil"
    elif target.company_id != source.company_id:
        warn = "kassalar boshqa-boshqa korxonalarniki"
    done = db.query(CashTransfer.id).filter(CashTransfer.note == _note(tx)).first() is not None
    return dict(tx=tx, shift=shift, source=source, target=target, cashier=cashier, done=done), warn


def _apply_row(db, row):
    tx: Transaction = row["tx"]
    source: Wallet = row["source"]
    target: Wallet = row["target"]
    amt = Decimal(str(tx.amount or 0))
    currency = (tx.currency_code or "UZS").upper()
    p_type = tx.payment_type or "cash"
    note = _note(tx)
    user_id = tx.user_id or (row["cashier"].id if row["cashier"] else None)

    mv_out = KassaMovement(
        wallet_id=source.id, company_id=target.company_id, session_id=_session_id(db, source.id),
        direction="out", payment_type=p_type, amount=amt, currency=currency,
        reference_type="transfer_out", description=f"Transfer to {target.name} (Smena #{tx.reference_id}): {note}",
        created_by=user_id, created_at=tx.created_at,
    )
    mv_in = KassaMovement(
        wallet_id=target.id, company_id=target.company_id, session_id=_session_id(db, target.id),
        direction="in", payment_type=p_type, amount=amt, currency=currency,
        reference_type="transfer_in", description=f"Transfer from {source.name} (Smena #{tx.reference_id}): {note}",
        created_by=user_id, created_at=tx.created_at,
    )
    db.add(mv_out)
    db.add(mv_in)
    # Qabul qiluvchi balansi eski kod tomonidan allaqachon oshirilgan — faqat manba kamayadi
    if currency == "UZS":
        source.balance = Decimal(str(source.balance or 0)) - amt
    ct = CashTransfer(
        company_id=target.company_id, sender_wallet_id=source.id, receiver_wallet_id=target.id,
        sender_branch_id=source.branch_id, receiver_branch_id=target.branch_id,
        amount=amt, currency=currency, payment_type=p_type, status="completed",
        sent_by=user_id, received_by=user_id, sent_at=tx.created_at, received_at=tx.created_at,
        note=note,
    )
    db.add(ct)
    db.flush()
    mv_out.reference_id = ct.id
    mv_in.reference_id = ct.id
    db.delete(tx)


def main():
    ap = argparse.ArgumentParser(description="Eski smena inkassatsiyasi (income) yozuvlarini o'tkazmaga aylantirish")
    ap.add_argument("--apply", action="store_true", help="O'zgarishlarni bazaga yozish (--shift-ids shart)")
    ap.add_argument("--shift-ids", default="", help="Vergul bilan ajratilgan smena ID lari, masalan 12,15,20")
    ap.add_argument("--company-id", type=int, default=None, help="Faqat shu korxona yozuvlari")
    args = ap.parse_args()

    shift_ids = _parse_ids(args.shift_ids)
    if args.apply and not shift_ids:
        print("XATO: --apply faqat --shift-ids bilan ishlaydi (masalan --shift-ids 12,15)")
        sys.exit(2)

    db = SessionLocal()
    try:
        txs = _load(db, args.company_id, shift_ids)
        if not txs:
            print("Eski 'shift' income yozuvlari topilmadi.")
            return
        print(f"{'tx':>7} {'korxona':>7} {'smena':>6} {'sana':<20} {'summa':>14} {'tur':<8} {'manba':<20} {'qabul':<20} holat")
        applied = skipped = 0
        total = Decimal("0")
        for tx in txs:
            row, warn = _plan_row(db, tx)
            src = row["source"].name if row["source"] else "-"
            tgt = row["target"].name if row["target"] else "-"
            if row["done"]:
                status = "allaqachon tuzatilgan"
            elif warn:
                status = f"O'TKAZILDI: {warn}"
            else:
                status = "tuzatiladi" if args.apply else "dry-run"
            created = tx.created_at.strftime("%Y-%m-%d %H:%M") if tx.created_at else "-"
            print(f"{tx.id:>7} {tx.company_id or '-':>7} {tx.reference_id or '-':>6} {created:<20} "
                  f"{Decimal(str(tx.amount or 0)):>14} {tx.payment_type or '-':<8} {src[:20]:<20} {tgt[:20]:<20} {status}")
            total += Decimal(str(tx.amount or 0))
            if args.apply and not warn and not row["done"]:
                _apply_row(db, row)
                applied += 1
            elif args.apply:
                skipped += 1
        print(f"\nJami {len(txs)} ta yozuv, summa {total}.")
        if args.apply:
            db.commit()
            print(f"Tuzatildi: {applied}, o'tkazib yuborildi: {skipped}.")
        else:
            print("Dry-run: hech narsa o'zgartirilmadi. Qo'llash uchun: --apply --shift-ids <id,...>")
    except Exception as e:
        db.rollback()
        print(f"Xatolik yuz berdi, o'zgarishlar bekor qilindi: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
