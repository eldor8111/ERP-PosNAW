"""Mobil ilova (kuryer/agent) uchun umumiy yordamchilar."""
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.courier import Courier
from app.models.moliya import Wallet
from app.models.user import User, UserRole, UserWallet


def ensure_personal_wallet(db: Session, user: User) -> Wallet:
    """Kuryer/agentning "qo'l kassasi". Yig'ilgan naqd pul shu kassaga
    kirim bo'ladi, kun oxirida asosiy kassaga o'tkaziladi — shunda kim
    qancha pul olib yurgani doim ko'rinadi."""
    # T0.4: default kassa faqat joriy korxona ichida qidiriladi (user_wallets.company_id yoki,
    # eski company_id NULL qatorlar uchun, wallets.company_id orqali)
    company_wallet_ids = select(Wallet.id).where(Wallet.company_id == user.company_id)
    link = db.query(UserWallet).filter(
        UserWallet.user_id == user.id,
        UserWallet.is_default == True,  # noqa: E712
        UserWallet.wallet_id.in_(company_wallet_ids),
    ).first()
    from app.core.branch_context import effective_branch_id
    if link:
        w = db.query(Wallet).filter(Wallet.id == link.wallet_id, Wallet.company_id == user.company_id).first()
        if w:
            # T3.14: xodim filiali o'zgargan bo'lsa qo'l kassasi filiali ham sinxronlanadi
            cur_branch = effective_branch_id(db, user)
            if w.branch_id != cur_branch:
                w.branch_id = cur_branch
            return w
    w = Wallet(
        name=f"{user.name} — qo'l kassasi",
        type="cash",
        balance=Decimal("0"),
        company_id=user.company_id,
        # T1.2: filial joriy korxona bo'yicha (begona korxona users.branch_id yozilmaydi)
        branch_id=effective_branch_id(db, user),
        is_active=True,
        is_open=True,
        is_personal=True,  # T1.10: umumiy fallback va ro'yxatlarda ko'rinmaydi
    )
    db.add(w)
    db.flush()
    # Faqat shu korxona kassalaridagi default bekor qilinadi — boshqa korxona biriktirishiga tegilmaydi
    db.query(UserWallet).filter(
        UserWallet.user_id == user.id,
        UserWallet.wallet_id.in_(company_wallet_ids),
    ).update({"is_default": False}, synchronize_session=False)
    db.add(UserWallet(user_id=user.id, wallet_id=w.id, company_id=user.company_id, is_default=True))
    db.flush()
    return w


def _phone_tail(p: Optional[str]) -> str:
    digits = "".join(ch for ch in (p or "") if ch.isdigit())
    return digits[-9:]


def ensure_courier_profile(db: Session, user: User) -> Optional[Courier]:
    """courier rolidagi foydalanuvchini logistikadagi Courier yozuviga
    bog'laydi: avval user_id, keyin telefon (oxirgi 9 raqam) bo'yicha;
    topilmasa yangi Courier yaratiladi."""
    if user.role != UserRole.courier:
        return None
    c = db.query(Courier).filter(Courier.user_id == user.id, Courier.company_id == user.company_id).first()
    if c:
        return c
    tail = _phone_tail(user.phone)
    for cand in db.query(Courier).filter(Courier.company_id == user.company_id, Courier.user_id.is_(None)).all():
        if tail and _phone_tail(cand.phone) == tail:
            cand.user_id = user.id
            db.flush()
            return cand
    # T3.9: login yo'li — HTTPException ko'tarilmaydi; kvota to'lgan bo'lsa nofaol profil yaratiladi
    # (mobile/courier.py:_me "Kuryer profili faol emas" 403 beradi)
    from app.services.tariff_guard import courier_limit_reached
    active = not courier_limit_reached(db, user.company_id, exclude_user_id=user.id)
    c = Courier(company_id=user.company_id, name=user.name, phone=user.phone, is_active=active, user_id=user.id)
    db.add(c)
    db.flush()
    return c


# ── Oflayn navbat idempotentligi ─────────────────────────────────────────────

def idem_get(db: Session, user: User, key: Optional[str]):
    """Idempotency-Key bo'yicha avval saqlangan javob (bo'lmasa None)."""
    if not key:
        return None
    from app.models.mobile_misc import MobileIdempotency
    row = db.query(MobileIdempotency).filter(MobileIdempotency.user_id == user.id, MobileIdempotency.key == key[:64]).first()
    return row.response if row else None


def idem_put(db: Session, user: User, key: Optional[str], endpoint: str, response: dict):
    """Yozuvni qo'shadi (asosiy amal bilan bitta tranzaksiyada commit bo'lishi
    uchun amaldan OLDIN chaqiriladi). Qaytgan qatorning .response'i keyin
    yakuniy javob bilan yangilanadi."""
    if not key:
        return None
    from app.models.mobile_misc import MobileIdempotency
    row = MobileIdempotency(user_id=user.id, key=key[:64], endpoint=endpoint[:100], response=response)
    db.add(row)
    return row


# ── Geo ──────────────────────────────────────────────────────────────────────

def distance_m(lat1, lng1, lat2, lng2) -> Optional[int]:
    """Haversine — ikki nuqta orasidagi masofa (metr)."""
    import math
    if None in (lat1, lng1, lat2, lng2):
        return None
    lat1, lng1, lat2, lng2 = map(float, (lat1, lng1, lat2, lng2))
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(round(2 * r * math.asin(math.sqrt(h))))


# ── Qo'l kassasidan asosiy kassaga topshirish ────────────────────────────────

def personal_cash_balance(db: Session, wallet: Wallet) -> Decimal:
    """Qo'l kassasidagi NAQD pul (UZS): faqat `payment_type='cash'` harakatlari qoldig'i.
    Karta/bank tushumi `Wallet.balance` ga kirsa ham "qo'lda turgan pul" emas va uni
    kassaga naqd deb topshirib bo'lmaydi (FIN-26). `Wallet.balance` dan oshmaydi."""
    from sqlalchemy import case, func
    from app.models.moliya import KassaMovement
    net = db.query(func.coalesce(func.sum(case(
        (KassaMovement.direction == "in", KassaMovement.amount), else_=-KassaMovement.amount)), 0)).filter(
        KassaMovement.wallet_id == wallet.id,
        KassaMovement.payment_type == "cash",
        func.upper(func.coalesce(KassaMovement.currency, "UZS")) == "UZS",
    ).scalar()
    cash = Decimal(str(net or 0))
    bal = Decimal(str(wallet.balance or 0))
    return max(Decimal("0"), min(cash, bal))


def receivable_wallets(db: Session, user: User) -> list:
    """Pul topshirsa bo'ladigan kassalar — dala xodimlarining shaxsiy
    kassalari bundan mustasno.

    Tartib (T3.14): xodim filialidagi kassalar, keyin filialsiz (`branch_id IS NULL`), keyin
    qolgan filiallar. Yopiq kassa (`is_open=False`) ham qaytadi: kun oxirida yopilgan kassaga
    topshirish `pending` bo'lib, kassa ochilganda qabul qilinadi. Boshqa filial kassasiga
    topshirish `handover_cash` da tasdiq (`confirm_other_branch`) talab qiladi."""
    # T1.10: shaxsiy kassalar `is_personal` bayrog'i bilan chiqarib tashlanadi (qo'shimcha JOIN o'rniga)
    q = db.query(Wallet).filter(
        Wallet.company_id == user.company_id, Wallet.is_active == True,  # noqa: E712
        Wallet.is_personal == False,  # noqa: E712
    )
    from app.core.branch_context import effective_branch_id
    branch_id = effective_branch_id(db, user)

    def _rank(w: Wallet) -> int:
        if branch_id is not None and w.branch_id == branch_id:
            return 0
        return 1 if w.branch_id is None else 2

    return sorted(q.order_by(Wallet.name).all(), key=_rank)  # sorted barqaror: ichida nom bo'yicha


def handover_cash(db: Session, user: User, receiver_wallet_id: int, amount: Decimal, note: Optional[str],
                  confirm_other_branch: bool = False):
    """Ikki bosqichli: pul xodim kassasidan darhol chiqadi (pending o'tkazma),
    kassir Kassa sahifasida "Qabul qilish" bosganda asosiy kassaga kiradi,
    "Rad etish" bosilsa xodimga qaytadi (mavjud /kassa/transfer/in|reject)."""
    from fastapi import HTTPException
    from app.models.moliya import CashTransfer, KassaMovement
    sender = ensure_personal_wallet(db, user)
    if receiver_wallet_id not in {w.id for w in receivable_wallets(db, user)}:
        raise HTTPException(status_code=404, detail="Kassa topilmadi")
    amount = Decimal(str(amount))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Summa musbat bo'lishi kerak")
    if amount > personal_cash_balance(db, sender):
        raise HTTPException(status_code=400, detail="Qo'lingizdagi summadan ko'p topshirib bo'lmaydi")
    receiver = db.query(Wallet).filter(Wallet.id == receiver_wallet_id).first()
    # T3.14: boshqa filial kassasiga topshirish — faqat aniq tasdiq bilan
    from app.core.branch_context import effective_branch_id
    own_branch = effective_branch_id(db, user)
    if (not confirm_other_branch and own_branch is not None
            and receiver.branch_id is not None and receiver.branch_id != own_branch):
        raise HTTPException(status_code=409, detail="Boshqa filial kassasi")
    ct = CashTransfer(
        company_id=user.company_id, sender_wallet_id=sender.id, receiver_wallet_id=receiver.id,
        sender_branch_id=sender.branch_id, receiver_branch_id=receiver.branch_id,
        amount=amount, currency="UZS", payment_type="cash", status="pending",
        sent_by=user.id, note=(note or f"{user.name} topshirdi")[:200],
    )
    db.add(ct)
    db.flush()
    db.add(KassaMovement(
        wallet_id=sender.id, company_id=user.company_id, direction="out", payment_type="cash",
        amount=amount, currency="UZS", reference_type="transfer_out", reference_id=ct.id,
        description=f"Kassaga topshirildi: {receiver.name}", created_by=user.id,
    ))
    sender.balance = Decimal(str(sender.balance or 0)) - amount
    from app.core.audit import log_action
    log_action(
        db, "CASH_TRANSFER_OUT", "cash_transfer", ct.id, user.id,
        new_values={
            "sender_wallet_id": sender.id, "receiver_wallet_id": receiver.id,
            "sender_branch_id": sender.branch_id, "receiver_branch_id": receiver.branch_id,
            "amount": str(amount), "currency": "UZS", "payment_type": "cash", "status": "pending",
        },
    )
    db.flush()
    return ct


def reject_pending_transfer(db: Session, user, ct, sender: Wallet, ip_address: Optional[str] = None,
                            cancelled_by_sender: bool = False) -> None:
    """`pending` o'tkazmani rad etib pulni yuboruvchi kassaga qaytaradi (kassir "Rad etish" —
    `kassa.transfer_reject` va kuryer "Bekor qilish" — `mobile/cash` uchun umumiy mantiq).
    Chaqiruvchi o'tkazma va kassalarni qulflab, `pending` ekanini tekshirgan bo'lishi shart."""
    from datetime import datetime, timezone
    from app.core.audit import log_action
    from app.services import cash_service
    ct.status = "rejected"
    ct.received_by = user.id
    ct.received_at = datetime.now(timezone.utc)

    # Pulni orqaga qaytarish (refund) — `cash_service.post_cash` (Transaction yo'q; Wallet.balance faqat UZS)
    cash_service.post_cash(
        db, user=user, wallet=sender, direction="in", amount=ct.amount, currency=ct.currency,
        payment_type=ct.payment_type, reference_type="transfer_rejected", reference_id=ct.id,
        description="Transfer bekor qilindi, qaytarildi", with_transaction=False,
    )
    log_action(
        db, "CASH_TRANSFER_CANCEL" if cancelled_by_sender else "CASH_TRANSFER_REJECT",
        "cash_transfer", ct.id, user.id,
        old_values={"status": "pending"},
        new_values={
            "status": "rejected", "sender_wallet_id": sender.id, "amount": str(ct.amount),
            "currency": ct.currency, "payment_type": ct.payment_type,
        },
        ip_address=ip_address, company_id=user.company_id, branch_id=sender.branch_id,
    )


def cancel_handover(db: Session, user: User, transfer_id: int):
    """Xodim o'z `pending` topshirig'ini bekor qiladi — summa qo'l kassasiga qaytadi.
    Boshqa xodim topshirig'i yoki boshqa korxona — 404; `pending` bo'lmasa — 400."""
    from fastapi import HTTPException
    from app.models.moliya import CashTransfer
    sender = ensure_personal_wallet(db, user)
    ct = db.query(CashTransfer).filter(
        CashTransfer.id == transfer_id, CashTransfer.company_id == user.company_id,
        CashTransfer.sender_wallet_id == sender.id, CashTransfer.sent_by == user.id,
    ).with_for_update().populate_existing().first()
    if not ct:
        raise HTTPException(status_code=404, detail="Topshiriq topilmadi")
    if ct.status != "pending":
        raise HTTPException(status_code=400, detail="Topshiriq allaqachon qayta ishlangan")
    db.query(Wallet).filter(Wallet.id == sender.id).with_for_update().first()
    reject_pending_transfer(db, user, ct, sender, cancelled_by_sender=True)
    db.flush()
    return ct


# ── Push-xabarlar (FCM) ──────────────────────────────────────────────────────

def push_to_user(db: Session, user_id: Optional[int], title: str, body: str, data: Optional[dict] = None) -> None:
    """Xodimning barcha faol qurilmalariga push. Firebase sozlanmagan bo'lsa
    jim o'tadi — asosiy amalga (marshrut biriktirish, buyurtma tasdiqlash)
    hech qachon xalaqit bermaydi."""
    if not user_id:
        return
    try:
        from app.models.mobile_device import MobileDevice
        from app.services.fcm_service import send_multicast_notification
        tokens = [t for (t,) in db.query(MobileDevice.fcm_token).filter(
            MobileDevice.user_id == user_id, MobileDevice.revoked_at.is_(None), MobileDevice.fcm_token.isnot(None),
        ).all()]
        if tokens:
            send_multicast_notification(tokens, title, body, {k: str(v) for k, v in (data or {}).items()})
    except Exception as e:
        print(f"[push] yuborilmadi: {e}")
