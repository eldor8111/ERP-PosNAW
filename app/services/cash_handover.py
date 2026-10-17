"""Kassalararo ichki pul harakati (inkassatsiya / o'tkazma) — yagona yordamchi.

Inkassatsiya DAROMAD EMAS: manba kassa kamayadi, qabul qiluvchi kassa oshadi, jami
pul o'zgarmaydi. Shuning uchun `Transaction` yozilmaydi — faqat ikkita `KassaMovement`
(`transfer_out` / `transfer_in`) va bitta `CashTransfer(status="completed")`.
Smena yopilishi (T0.28) va `kassa.py::transfer_out` (T0.35) shu helperdan foydalanadi.
"""
# pyright: reportMissingImports=false
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from fastapi import HTTPException  # type: ignore
from sqlalchemy import case, func  # type: ignore
from sqlalchemy.orm import Session  # type: ignore


def _dec(v) -> Decimal:
    return Decimal(str(v or 0))


def lock_wallets(db: Session, wallet_ids: Iterable[Optional[int]]) -> None:
    """Hamyonlarni `id` tartibida qulflaydi (deadlock bo'lmasligi uchun) va yangilaydi."""
    from app.models.moliya import Wallet
    for wid in sorted({w for w in wallet_ids if w}):
        db.query(Wallet).filter(Wallet.id == wid).with_for_update().populate_existing().first()


def kassa_net(db: Session, wallet_id: int, payment_type: str, currency: str = "UZS") -> Decimal:
    """Kassadagi (to'lov turi + valyuta bo'yicha) sof qoldiq: kirim − chiqim (`KassaMovement`)."""
    from app.models.moliya import KassaMovement
    signed = case((KassaMovement.direction == "in", KassaMovement.amount), else_=-KassaMovement.amount)
    total = db.query(func.coalesce(func.sum(signed), 0)).filter(
        KassaMovement.wallet_id == wallet_id,
        KassaMovement.payment_type == payment_type,
        func.coalesce(KassaMovement.currency, "UZS") == (currency or "UZS"),
    ).scalar()
    return _dec(total)


def transfer_between_wallets(
    db: Session,
    *,
    company_id: int,
    source,
    target,
    amount,
    currency: str = "UZS",
    payment_type: str = "cash",
    user,
    note: Optional[str] = None,
    ref: Optional[str] = None,
):
    """Manba kassadan qabul qiluvchi kassaga ichki o'tkazma yozadi va `CashTransfer` qaytaradi.

    - Ikkala hamyon `id` tartibida `with_for_update()` bilan qulflanadi.
    - `KassaMovement(out, reference_type="transfer_out")` manbaga, `KassaMovement(in,
      "transfer_in")` qabul qiluvchiga — har biri o'z ochiq `KassaSession` iga bog'lanadi.
    - Valyuta UZS bo'lsa `Wallet.balance` ham mos ravishda o'zgaradi.
    - `Transaction` YOZILMAYDI (daromad/xarajat emas). `commit` chaqiruvchida.
    - `amount <= 0` bo'lsa hech narsa yozilmaydi (`None`).
    """
    from app.models.moliya import CashTransfer, KassaMovement, KassaSession

    amt = _dec(amount)
    if amt <= 0:
        return None
    if source.id == target.id:
        raise HTTPException(status_code=400, detail="Manba va qabul qiluvchi kassa bir xil")
    if source.company_id != company_id or target.company_id != company_id:
        raise HTTPException(status_code=404, detail="Kassa (hamyon) topilmadi")

    currency = (currency or "UZS").upper()
    lock_wallets(db, [source.id, target.id])

    def _session_id(wallet_id: int):
        s = db.query(KassaSession).filter(
            KassaSession.wallet_id == wallet_id, KassaSession.status == "open"
        ).first()
        return s.id if s else None

    suffix = f" ({ref})" if ref else ""
    tail = f": {note}" if note else ""
    mv_out = KassaMovement(
        wallet_id=source.id, company_id=company_id, session_id=_session_id(source.id),
        direction="out", payment_type=payment_type, amount=amt, currency=currency,
        reference_type="transfer_out",
        description=f"Transfer to {target.name}{suffix}{tail}",
        created_by=user.id,
    )
    mv_in = KassaMovement(
        wallet_id=target.id, company_id=company_id, session_id=_session_id(target.id),
        direction="in", payment_type=payment_type, amount=amt, currency=currency,
        reference_type="transfer_in",
        description=f"Transfer from {source.name}{suffix}{tail}",
        created_by=user.id,
    )
    db.add(mv_out)
    db.add(mv_in)

    if currency == "UZS":
        source.balance = _dec(source.balance) - amt
        target.balance = _dec(target.balance) + amt

    ct = CashTransfer(
        company_id=company_id, sender_wallet_id=source.id, receiver_wallet_id=target.id,
        amount=amt, currency=currency, payment_type=payment_type, status="completed",
        sent_by=user.id, received_by=user.id, received_at=datetime.now(timezone.utc),
        note=note,
    )
    db.add(ct)
    db.flush()
    mv_out.reference_id = ct.id
    mv_in.reference_id = ct.id
    return ct
