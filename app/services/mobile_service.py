"""Mobil ilova (kuryer/agent) uchun umumiy yordamchilar."""
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.courier import Courier
from app.models.moliya import Wallet
from app.models.user import User, UserRole, UserWallet


def ensure_personal_wallet(db: Session, user: User) -> Wallet:
    """Kuryer/agentning "qo'l kassasi". Yig'ilgan naqd pul shu kassaga
    kirim bo'ladi, kun oxirida asosiy kassaga o'tkaziladi — shunda kim
    qancha pul olib yurgani doim ko'rinadi."""
    link = db.query(UserWallet).filter(UserWallet.user_id == user.id, UserWallet.is_default == True).first()  # noqa: E712
    if link:
        w = db.query(Wallet).filter(Wallet.id == link.wallet_id, Wallet.company_id == user.company_id).first()
        if w:
            return w
    w = Wallet(
        name=f"{user.name} — qo'l kassasi",
        type="cash",
        balance=Decimal("0"),
        company_id=user.company_id,
        branch_id=user.branch_id,
        is_active=True,
        is_open=True,
    )
    db.add(w)
    db.flush()
    db.query(UserWallet).filter(UserWallet.user_id == user.id).update({"is_default": False})
    db.add(UserWallet(user_id=user.id, wallet_id=w.id, is_default=True))
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
    c = Courier(company_id=user.company_id, name=user.name, phone=user.phone, is_active=True, user_id=user.id)
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

def receivable_wallets(db: Session, user: User) -> list:
    """Pul topshirsa bo'ladigan kassalar — dala xodimlarining shaxsiy
    kassalari bundan mustasno."""
    from app.models.user import MOBILE_ONLY_ROLES
    personal = {
        wid for (wid,) in db.query(UserWallet.wallet_id).join(User, User.id == UserWallet.user_id).filter(
            User.company_id == user.company_id, User.role.in_(MOBILE_ONLY_ROLES),
        ).all()
    }
    return [
        w for w in db.query(Wallet).filter(Wallet.company_id == user.company_id, Wallet.is_active == True).order_by(Wallet.name).all()  # noqa: E712
        if w.id not in personal
    ]


def handover_cash(db: Session, user: User, receiver_wallet_id: int, amount: Decimal, note: Optional[str]):
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
    if amount > Decimal(str(sender.balance or 0)):
        raise HTTPException(status_code=400, detail="Qo'lingizdagi summadan ko'p topshirib bo'lmaydi")
    receiver = db.query(Wallet).filter(Wallet.id == receiver_wallet_id).first()
    ct = CashTransfer(
        company_id=user.company_id, sender_wallet_id=sender.id, receiver_wallet_id=receiver.id,
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
