"""Sotuv to'lovlarini kassaga yozish va teskari qilish — yagona yordamchilar (T0.30).

- `build_sale_payment_entries` — `SaleCreate`/`SaleUpdate` dagi uch xil to'lov shaklini
  (payments ro'yxati, aralash paid_cash/paid_card, bitta payment_type/paid_amount)
  bir xil yozuvlar ro'yxatiga keltiradi;
- `post_sale_payments` — `SalePayment`, `Transaction` (T0.29: debt/cashback/mixed uchun yo'q),
  `KassaMovement` va `Wallet.balance` (faqat UZS) yozadi;
- `reverse_sale_payments` — sotuvning kassa harakatlarini sof qoldiq bo'yicha teskari
  qiladi (`reference_type = "<ref>_cancel"`), eski yozuvlar audit uchun o'chirilmaydi.
"""
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models.moliya import KassaMovement, KassaSession, Transaction, Wallet, NON_CASH_PAYMENT_TYPES
from app.models.sale import PaymentType, Sale, SalePayment


def _open_session_id(db: Session, wallet_id: Optional[int]) -> Optional[int]:
    if not wallet_id:
        return None
    ks = db.query(KassaSession).filter(
        KassaSession.wallet_id == wallet_id, KassaSession.status == "open",
    ).first()
    return ks.id if ks else None


def build_sale_payment_entries(data, sale_currency: str = "UZS") -> List[dict]:
    """So'rovdagi to'lovlarni bir xil ro'yxatga keltiradi.

    Har yozuv: `type` (str), `amount` (asl valyutada), `rate`, `currency` (Transaction),
    `km_currency` (KassaMovement/hamyon), `label` (tavsif qo'shimchasi).
    `create_sale` dagi avvalgi mantiq aynan saqlangan.
    """
    sale_currency = (sale_currency or "UZS").upper()
    entries: List[dict] = []
    payments = getattr(data, "payments", None)
    paid_amount = Decimal(str(getattr(data, "paid_amount", 0) or 0))
    payment_type = getattr(data, "payment_type", None)

    if payments and len(payments) > 0:
        for p in payments:
            if p.amount <= 0:
                continue
            rate = Decimal(str(getattr(p, "rate", 1.0) or 1.0))
            tx_currency = (getattr(p, "currency", "UZS") or "UZS").upper()
            km_currency = getattr(p, "currency", "UZS")
            if km_currency == "UZS" and sale_currency != "UZS" and p.amount == paid_amount:
                # Frontend to'lov valyutasini yubormagan, lekin sotuv valyutasini nazarda tutgan
                km_currency = sale_currency
            if km_currency is None:
                km_currency = "UZS"
            entries.append({
                "type": p.type.value, "amount": Decimal(str(p.amount)), "rate": rate,
                "currency": tx_currency, "km_currency": km_currency, "label": p.type.value,
                # C4.1 (T3.18): provayder tranzaksiya raqami va to'lov terminali SalePayment ga to'g'ridan-to'g'ri yoziladi
                "reference": (getattr(p, "reference", None) or "").strip() or None,
                "terminal_id": getattr(p, "terminal_id", None),
            })
    elif paid_amount > 0:
        if payment_type == PaymentType.mixed:
            for _pt, _amt in [("cash", getattr(data, "paid_cash", 0)), ("card", getattr(data, "paid_card", 0))]:
                _amt = Decimal(str(_amt or 0))
                if _amt > 0:
                    entries.append({
                        "type": _pt, "amount": _amt, "rate": Decimal("1"),
                        "currency": "UZS", "km_currency": sale_currency, "label": f"Aralash/{_pt}",
                    })
        elif payment_type is not None:
            entries.append({
                "type": payment_type.value, "amount": paid_amount, "rate": Decimal("1"),
                "currency": sale_currency, "km_currency": sale_currency, "label": None,
            })
    return entries


def post_sale_payments(
    db: Session,
    sale: Sale,
    payments: Iterable[dict],
    user,
    wallet_id: Optional[int] = None,
    tx_branch_id: Optional[int] = None,
    created_at=None,
    desc_prefix: str = "Sotuv to'lovi",
) -> Optional[int]:
    """To'lov yozuvlarini yozadi: `SalePayment` (hammasi), `Transaction` + `KassaMovement` +
    `Wallet.balance` (faqat haqiqiy pul turlari, T0.29).

    `wallet_id` berilmasa kassirning kassasi (`resolve_cashier_wallet_id`). Hamyon
    korxonaga tegishli bo'lishi shart. Ishlatilgan hamyon id sini qaytaradi.
    """
    from app.services.sale_helpers import resolve_cashier_wallet_id
    from app.services.tenant_guards import find_tx_branch
    from app.services.wallet_access import find_company_wallet

    entries = list(payments or [])
    if not entries:
        return wallet_id
    # Hamyon: berilgan (tahrirda avval teskari qilingan asl hamyon) -> kassir kassasi.
    # Faqat shu korxonaning faol hamyoni; aks holda kassir kassasiga o'tiladi.
    wallet = find_company_wallet(db, wallet_id, sale.company_id) if wallet_id else None
    if wallet is not None and wallet.is_active is False:
        wallet = None
    if wallet is None:
        wallet_id = resolve_cashier_wallet_id(db, user)
        wallet = find_company_wallet(db, wallet_id, sale.company_id) if wallet_id else None
    wallet_id = wallet.id if wallet is not None else None
    session_id = _open_session_id(db, wallet_id)
    if tx_branch_id is None:
        tx_branch_id = find_tx_branch(db, user, warehouse_id=sale.warehouse_id)

    for e in entries:
        ptype = str(e["type"])
        amount = Decimal(str(e["amount"] or 0))
        if amount <= 0:
            continue
        rate = Decimal(str(e.get("rate", 1) or 1))
        tx_currency = (e.get("currency") or "UZS").upper()
        km_currency = e.get("km_currency") or tx_currency
        label = e.get("label")
        amount_uzs = amount * rate

        db.add(SalePayment(
            sale_id=sale.id, payment_type=ptype, amount=amount_uzs,
            reference=(e.get("reference") or None), terminal_id=e.get("terminal_id"),  # C4.1 (T3.18)
        ))
        if ptype in NON_CASH_PAYMENT_TYPES:
            # Qarz/keshbek/aralash qatori — haqiqiy pul emas: SalePayment (chek va tarix
            # uchun) qoladi, lekin pul oqimiga (Transaction/kassa) kirim yozilmaydi (T0.29).
            continue

        tx_amount = amount if tx_currency != "UZS" else amount_uzs
        tx_kwargs = dict(
            branch_id=tx_branch_id, company_id=sale.company_id, wallet_id=wallet_id,
            type="income", amount=tx_amount, payment_type=ptype, currency_code=tx_currency,
            reference_type="sale", reference_id=sale.id,
            description=f"{desc_prefix} #{sale.number}" + (f" ({label})" if label else "")
            + (f" ({amount} {tx_currency})" if tx_currency != "UZS" else ""),
        )
        if created_at is not None:
            tx_kwargs["created_at"] = created_at
        db.add(Transaction(**tx_kwargs))

        if wallet_id:
            db.add(KassaMovement(
                wallet_id=wallet_id, company_id=sale.company_id, session_id=session_id,
                direction="in", payment_type=ptype, amount=amount, currency=km_currency,
                reference_type="sale", reference_id=sale.id,
                description=f"Sotuv #{sale.number}" + (f" ({amount} {km_currency})" if km_currency != "UZS" else ""),
                created_by=user.id,
            ))
            # close_kassa bilan simmetriya: faqat UZS harakatlari balansga yoziladi
            if (km_currency or "UZS").upper() == "UZS" and wallet is not None:
                wallet.balance = Decimal(str(wallet.balance or 0)) + amount
    db.flush()
    return wallet_id


def reverse_sale_payments(db: Session, sale: Sale, user, ref_type: str = "sale") -> List[int]:
    """Sotuvning kassa harakatlarini teskari qiladi.

    Har `(wallet_id, payment_type, currency)` uchun sof qoldiq
    `Σ in(ref_type) − Σ out(ref_type + "_cancel")` hisoblanadi — bir sotuv qayta-qayta
    tahrirlanganda takror qaytarilmaydi. Shu miqdorda `direction="out"`,
    `reference_type=ref_type + "_cancel"` yozuv kassaning hozirgi ochiq sessiyasiga
    (yoki `session_id=NULL`) yoziladi; yopilgan sessiya o'zgarmaydi. UZS bo'lsa
    `Wallet.balance` kamayadi (hamyon `with_for_update`). Qaytariladigan hamyon id'lari.
    """
    cancel_ref = f"{ref_type}_cancel"
    rows = db.query(KassaMovement).filter(
        KassaMovement.company_id == sale.company_id,
        KassaMovement.reference_type.in_([ref_type, cancel_ref]),
        KassaMovement.reference_id == sale.id,
    ).order_by(KassaMovement.id.asc()).all()

    net: dict = {}
    for m in rows:
        key = (m.wallet_id, m.payment_type, (m.currency or "UZS").upper())
        sign = Decimal("1") if m.direction == "in" else Decimal("-1")
        net[key] = net.get(key, Decimal("0")) + sign * Decimal(str(m.amount or 0))

    wallet_ids: List[int] = []
    for (wallet_id, ptype, currency), amount in net.items():
        if abs(amount) <= Decimal("0.001"):
            continue
        wallet = None
        if wallet_id:
            wallet = db.query(Wallet).filter(
                Wallet.id == wallet_id, Wallet.company_id == sale.company_id,
            ).with_for_update().first()
        direction = "out" if amount > 0 else "in"
        amount = abs(amount)
        db.add(KassaMovement(
            wallet_id=wallet_id, company_id=sale.company_id,
            session_id=_open_session_id(db, wallet_id),
            direction=direction, payment_type=ptype, amount=amount, currency=currency,
            reference_type=cancel_ref, reference_id=sale.id,
            description=f"Sotuv bekor qilish #{sale.number}",
            created_by=user.id,
        ))
        if wallet is not None and currency == "UZS":
            delta = amount if direction == "in" else -amount
            wallet.balance = Decimal(str(wallet.balance or 0)) + delta
        if wallet_id and wallet_id not in wallet_ids:
            wallet_ids.append(wallet_id)
    db.flush()
    return wallet_ids
