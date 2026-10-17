"""Pul kirim-chiqimi — yagona servis (T2.8).

Kassa pulining YAGONA haqiqati — `KassaMovement` jurnali. `Wallet.balance` shundan hosil bo'lgan
keshlangan qiymat: `SUM(in) - SUM(out)`, faqat `currency='UZS'`. `WalletBalance` jadvaliga yangi
yozuv tushmaydi (jadval bir reliz qoladi).

`post_cash` bitta chaqiruvda quyidagilarni bajaradi:
- hamyon shu foydalanuvchi korxonasiniki ekanini tekshiradi (aks holda 404);
- `KassaMovement` yozadi (ochiq kassa sessiyasi bilan) — `payment_type` `debt`/`cashback` bundan mustasno;
- `Wallet.balance` ni faqat UZS bo'lsa o'zgartiradi (valyutali pul faqat jurnalda);
- `Transaction` yozadi (`user_id`, `company_id`, `branch_id`) — `with_transaction=False` bo'lsa yozmaydi.

Ataylab `Transaction` yozmaydigan yo'llar (`with_transaction=False`): kassadagi investitsiya, chiqarish
va kassalararo o'tkazma. Ular P&L ga kirmaydi (`finance_report` "boshqa daromad"ni `Transaction`dan oladi),
faqat kassa jurnaliga tushadi.

`reverse_cash` — teskari amal. Standart (`void=False`): hamyon balansi qaytariladi, kassa harakati va
tranzaksiya o'chiriladi (ta'minotchi to'lovlarining eski xatti-harakati). `void=True` (T1.19): hech narsa
o'chirilmaydi — teskari harakat yoziladi, tranzaksiya `voided_at` bilan bekor qilinadi.
"""
# pyright: reportMissingImports=false
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.models.moliya import KassaMovement, KassaSession, Transaction, Wallet

WALLET_NOT_FOUND = "Kassa (hamyon) topilmadi"
# Kassaga haqiqiy pul tushmaydigan to'lov turlari: KassaMovement yozilmaydi, hamyon o'zgarmaydi
NO_MOVEMENT_PAYMENT_TYPES = ("debt", "cashback")


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def _code(currency) -> str:
    return (currency or "UZS").strip().upper() or "UZS"


def _as_local_naive(dt: datetime) -> datetime:
    """Yangi (tz-aware, default) va bazadan o'qilgan (naive) vaqtlarni solishtirish uchun: Toshkent vaqti, naive."""
    if dt.tzinfo is not None:
        from app.utils.report_utils import LOCAL_TZ
        return dt.astimezone(LOCAL_TZ).replace(tzinfo=None)
    return dt


def open_session_id(db: Session, wallet_id: Optional[int]) -> Optional[int]:
    """Kassaning ochiq sessiyasi id si (yo'q bo'lsa None)."""
    if not wallet_id:
        return None
    s = db.query(KassaSession.id).filter(
        KassaSession.wallet_id == wallet_id, KassaSession.status == "open",
    ).first()
    return s[0] if s else None


def _check_wallet(user, wallet) -> None:
    if wallet is not None and wallet.company_id != getattr(user, "company_id", None):
        raise HTTPException(status_code=404, detail=WALLET_NOT_FOUND)


def apply_wallet_balance(wallet, direction: str, amount, currency) -> None:
    """`Wallet.balance` keshi: faqat UZS (valyutali pul faqat KassaMovement.currency da yuritiladi)."""
    if wallet is None or _code(currency) != "UZS":
        return
    sign = Decimal("-1") if direction == "out" else Decimal("1")
    wallet.balance = _d(wallet.balance) + sign * _d(amount)


def post_cash(
    db: Session, *, user, wallet, direction: str, amount, currency: str = "UZS",
    payment_type: Optional[str] = "cash", reference_type: Optional[str] = None,
    reference_id: Optional[int] = None, description: Optional[str] = None,
    branch_id: Optional[int] = None, meta: Optional[dict] = None,
    created_at: Optional[datetime] = None, with_transaction: bool = True,
    link_movement_to_tx: bool = False,
):
    """Pul harakatini yozadi (modul docstring'iga qarang).

    direction: "in" (kirim) yoki "out" (chiqim). `wallet` — qulflangan `Wallet` (yoki `None`: faqat
    `Transaction`, kassa jurnalisiz). Qaytaradi: `with_transaction=True` da `Transaction`,
    aks holda `KassaMovement` (yozilmagan bo'lsa `None`).

    `link_movement_to_tx=True` — havolasiz (qo'lda kiritilgan) yozuv: tranzaksiya `reference_id=None` qoladi,
    kassa harakati esa `reference_type or "transaction"` + `reference_id = tx.id` bilan bog'lanadi.
    """
    if direction not in ("in", "out"):
        raise HTTPException(status_code=400, detail="Yo'nalish noto'g'ri")
    amount = _d(amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Summa musbat bo'lishi kerak")
    _check_wallet(user, wallet)
    code = _code(currency)
    ptype = payment_type or "cash"

    tx = None
    if with_transaction:
        if branch_id is None:
            from app.services.branch_attribution import resolve_money_branch_id
            branch_id = resolve_money_branch_id(db, user, wallet=wallet)
        tx = Transaction(
            company_id=user.company_id, branch_id=branch_id, user_id=user.id,
            wallet_id=wallet.id if wallet is not None else None,
            type="expense" if direction == "out" else "income",
            amount=amount, payment_type=ptype, currency_code=code,
            reference_type=reference_type, reference_id=reference_id,
            description=description, meta=meta,
        )
        if created_at is not None:
            tx.created_at = created_at
        db.add(tx)

    mv_ref_type, mv_ref_id = reference_type, reference_id
    if link_movement_to_tx and tx is not None:
        db.flush()
        mv_ref_type, mv_ref_id = reference_type or "transaction", tx.id
    mv = None
    if wallet is not None and ptype not in NO_MOVEMENT_PAYMENT_TYPES:
        mv = KassaMovement(
            wallet_id=wallet.id, company_id=user.company_id,
            session_id=open_session_id(db, wallet.id),
            direction=direction, payment_type=ptype, amount=amount, currency=code,
            reference_type=mv_ref_type, reference_id=mv_ref_id,
            description=description, created_by=user.id,
        )
        if created_at is not None:
            mv.created_at = created_at
        db.add(mv)
        apply_wallet_balance(wallet, direction, amount, code)
    db.flush()
    return tx if with_transaction else mv


def find_kassa_movement(db: Session, tx) -> Optional[KassaMovement]:
    """Tranzaksiyaga mos kassa harakati: bir xil havola, hamyon va summa, vaqti eng yaqini.

    Havolasiz (qo'lda kiritilgan) yozuvlarda harakat `reference_id = tx.id` bilan bog'langan."""
    q = db.query(KassaMovement)
    if tx.reference_id is not None:
        if not tx.reference_type:
            return None
        q = q.filter(
            KassaMovement.reference_type == tx.reference_type,
            KassaMovement.reference_id == tx.reference_id,
        )
        if tx.wallet_id:
            q = q.filter(KassaMovement.wallet_id == tx.wallet_id)
        candidates = [m for m in q.all() if abs(_d(m.amount) - _d(tx.amount)) < Decimal("0.01")]
        if candidates:
            if tx.created_at:
                base = _as_local_naive(tx.created_at)
                candidates.sort(key=lambda m: abs((_as_local_naive(m.created_at or tx.created_at) - base).total_seconds()))
            return candidates[0]
        return None
    if tx.id is None:
        return None
    q = q.filter(
        KassaMovement.reference_type == (tx.reference_type or "transaction"),
        KassaMovement.reference_id == tx.id,
    )
    if tx.wallet_id:
        q = q.filter(KassaMovement.wallet_id == tx.wallet_id)
    return q.first()


def reverse_movement(db: Session, mv, user, reference_type: str, reference_id: int, description: str):
    """Asl kassa harakati O'CHIRILMAYDI — qarama-qarshi yo'nalishdagi teskari harakat yoziladi
    (kassa balansi KassaMovement yig'indisidan hisoblanadi). Hamyon keshiga TEGMAYDI."""
    rev = KassaMovement(
        wallet_id=mv.wallet_id, company_id=mv.company_id,
        session_id=open_session_id(db, mv.wallet_id),
        direction="in" if mv.direction == "out" else "out",
        payment_type=mv.payment_type, amount=mv.amount, currency=mv.currency,
        reference_type=reference_type, reference_id=reference_id,
        description=description, created_by=user.id,
    )
    db.add(rev)
    return rev


def void_transaction(db: Session, tx, user, now, reference_type: str, reference_id: int, description: str) -> None:
    """Tranzaksiyani bekor qiladi (T1.19): `voided_at/voided_by` qo'yiladi va teskari yozuv (qarama-qarshi
    turdagi, o'zi ham voided) qo'shiladi. Hisobotlar `voided_at IS NULL` bilan ishlaydi; filtri unutilgan
    o'quvchida ham pul oqimi sof nolga teng bo'ladi."""
    tx.voided_at = now
    tx.voided_by = user.id
    db.add(Transaction(
        company_id=tx.company_id, branch_id=tx.branch_id, wallet_id=tx.wallet_id,
        type="income" if tx.type == "expense" else "expense",
        amount=tx.amount, payment_type=tx.payment_type, currency_code=tx.currency_code,
        reference_type=reference_type, reference_id=reference_id, description=description,
        user_id=user.id, voided_at=now, voided_by=user.id,
    ))


def reverse_cash(
    db: Session, tx, *, user=None, void: bool = False, now: Optional[datetime] = None,
    reference_type: str = "transaction_void", reference_id: Optional[int] = None,
    description: Optional[str] = None,
) -> None:
    """`post_cash` ni bekor qiladi: hamyon (UZS), kassa harakati va tranzaksiya.

    `void=False` — harakat va tranzaksiya o'chiriladi. `void=True` — o'chirilmaydi: teskari harakat
    (`reference_type`/`reference_id`) yoziladi, tranzaksiya `voided_at` bilan bekor qilinadi (`user` shart).
    Eski (meta siz) ta'minotchi yozuvlarida hamyon valyutadan qat'i nazar summaga o'zgargan edi —
    `void=False` bekor qilish ham shunday bo'ladi.
    """
    legacy = (not void) and tx.meta is None and tx.reference_type in (
        "purchase_order", "supplier_payment", "return_to_supplier",
    )
    mv = find_kassa_movement(db, tx)
    # Qarz/keshbek yozuvida kassa harakati ham, hamyon o'zgarishi ham bo'lmagan
    if tx.wallet_id and (tx.payment_type or "cash") not in NO_MOVEMENT_PAYMENT_TYPES:
        wallet = db.query(Wallet).filter(
            Wallet.id == tx.wallet_id, Wallet.company_id == tx.company_id,
        ).first()
        if wallet is not None and (legacy or _code(tx.currency_code) == "UZS"):
            sign = Decimal("1") if tx.type == "expense" else Decimal("-1")
            wallet.balance = _d(wallet.balance) + sign * _d(tx.amount)
    if void:
        ref_id = reference_id if reference_id is not None else tx.id
        desc = description or f"Tranzaksiya bekor qilindi (ID: {tx.id})"
        if mv is not None:
            reverse_movement(db, mv, user, reference_type, ref_id, desc)
        void_transaction(db, tx, user, now or datetime.utcnow(), reference_type, ref_id, desc)
    else:
        if mv is not None:
            db.delete(mv)
        db.delete(tx)
