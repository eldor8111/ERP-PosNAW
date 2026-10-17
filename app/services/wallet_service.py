"""Kassa (hamyon) CRUD — `/kassa` va `/finance/wallets` uchun yagona qoida (T2.8).

Ikki API (Kassa va Moliya sahifalari) bir xil qoidalar bo'yicha ishlaydi:
- ro'yxat: `wallet_resolver.list_visible_wallets` (korxona doirasi, faollik, shaxsiylik, filial), `id` bo'yicha;
- yaratish: filial shu korxonaniki va faol bo'lishi shart; kassa HAR DOIM yopiq (`is_open=False`) va
  sessiyasiz yaratiladi — ochish faqat `POST /kassa/{id}/open` orqali (Z-tarix saqlanadi);
  boshlang'ich balans `cash_service.post_cash` orqali kassa jurnaliga yoziladi;
- o'chirish: faqat yumshoq (`is_active=False`), hech qachon qattiq emas. Ochiq sessiya, kutilayotgan
  o'tkazma yoki nolga teng bo'lmagan qoldiq bo'lsa 409. Xodimlarga biriktirish (`user_wallets`) tozalanadi,
  shunda nofaol kassa hech kimga default bo'lib qolmaydi.

Funksiyalar commit QILMAYDI — chaqiruvchi (router) audit yozib, commit qiladi.
"""
# pyright: reportMissingImports=false
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException  # type: ignore
from sqlalchemy import or_  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.models.moliya import CashTransfer, KassaSession, Wallet
from app.services.cash_service import post_cash
from app.services.wallet_resolver import clear_wallet_assignments, list_visible_wallets

WALLET_HAS_OPEN_STATE = "Kassada ochiq sessiya yoki kutilayotgan o'tkazma bor"
WALLET_HAS_BALANCE = "Kassada qoldiq bor: avval pulni chiqaring yoki boshqa kassaga o'tkazing"
_EPS = Decimal("0.01")


def list_wallets(
    db: Session, user, *, branch_id: Optional[int] = None, active_only: bool = True, usable: bool = False,
) -> List[Wallet]:
    """Foydalanuvchiga ko'rinadigan kassalar (id bo'yicha). `super_admin` uchun ham korxona filtri qo'llanadi."""
    return list_visible_wallets(
        db, user, branch_id=branch_id, include_inactive=not active_only, usable=usable, company_scoped=True,
    )


def create_wallet(
    db: Session, user, *, name: str, type: str = "cash", branch_id: Optional[int] = None,
    is_active: bool = True, opening_balance=0, currency: str = "UZS", strict_lookup: bool = False,
) -> Wallet:
    """Kassa yaratadi: `is_open=False`, korxona = foydalanuvchi korxonasi.

    Filial berilgan bo'lsa — o'z korxonasiniki va faol bo'lishi shart: begona/mavjud emas/nofaol -> 400
    (`validate_branch`, T0.9). `strict_lookup=True` (Moliya API) — begona/mavjud emas filial avval alohida
    400 "Filial topilmadi" (T0.3) beradi; ikkala API xabari testlarda shunday qotirilgan.
    `opening_balance > 0` bo'lsa kassa jurnaliga
    "opening" kirimi yoziladi (`Wallet.balance` — faqat UZS bo'lsa)."""
    from app.services.tenant_guards import validate_branch
    from app.services.wallet_access import get_company_branch

    if strict_lookup:
        get_company_branch(db, branch_id, user.company_id)
    validate_branch(db, branch_id, user.company_id)
    opening = Decimal(str(opening_balance or 0))
    w = Wallet(
        name=name, type=type, company_id=user.company_id, branch_id=branch_id,
        balance=Decimal("0"), opening_balance=opening, is_active=is_active, is_open=False,
    )
    db.add(w)
    db.flush()
    if opening > 0:
        post_cash(
            db, user=user, wallet=w, direction="in", amount=opening, currency=currency,
            payment_type="cash", reference_type="opening", description="Boshlang'ich balans",
            with_transaction=False,
        )
    return w


def deactivate_wallet(db: Session, user, wallet: Wallet) -> bool:
    """Kassani yumshoq o'chiradi. Qaytaradi: oldingi `is_active` (takroriy chaqiruv xato bermaydi).

    409: ochiq kassa sessiyasi, kutilayotgan (`pending`) `CashTransfer` yoki nolga teng bo'lmagan
    `Wallet.balance`. Korxonaga tegishlilikni chaqiruvchi tekshiradi (begona kassa uchun 404)."""
    if wallet.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Kassa topilmadi")
    old_active = bool(wallet.is_active)
    if not old_active:
        return old_active
    has_session = db.query(KassaSession.id).filter(
        KassaSession.wallet_id == wallet.id, KassaSession.status == "open",
    ).first()
    has_transfer = db.query(CashTransfer.id).filter(
        CashTransfer.status == "pending",
        or_(CashTransfer.sender_wallet_id == wallet.id, CashTransfer.receiver_wallet_id == wallet.id),
    ).first()
    if has_session or has_transfer:
        raise HTTPException(status_code=409, detail=WALLET_HAS_OPEN_STATE)
    if abs(Decimal(str(wallet.balance or 0))) >= _EPS:
        raise HTTPException(status_code=409, detail=WALLET_HAS_BALANCE)
    wallet.is_active = False
    clear_wallet_assignments(db, wallet.id)
    return old_active
