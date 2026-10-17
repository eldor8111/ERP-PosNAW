"""Hamyon (kassa) va filialni korxonaga tekshirib olish — yagona yordamchi.

`db.get(Wallet, id)` o'rniga ishlatiladi: hamyon faqat `Wallet.id` emas,
`Wallet.id` VA `Wallet.company_id` bo'yicha olinadi, shuning uchun boshqa
korxona kassasiga pul yozib/ayirib bo'lmaydi (IDOR).
"""
# pyright: reportMissingImports=false
from typing import Optional

from fastapi import HTTPException  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

WALLET_NOT_FOUND = "Kassa (hamyon) topilmadi"
BRANCH_NOT_FOUND = "Filial topilmadi"
USER_NOT_FOUND = "Foydalanuvchi topilmadi"


def find_company_wallet(db: Session, wallet_id: Optional[int], company_id: Optional[int]):
    """Hamyonni korxona bo'yicha qidiradi; topilmasa xato bermaydi, `None` qaytaradi.
    Eski `tx.wallet_id` bo'yicha teskari amallar (balansni qaytarish) uchun."""
    if not wallet_id:
        return None
    from app.models.moliya import Wallet
    return db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == company_id).first()


def get_company_wallet(
    db: Session,
    wallet_id: Optional[int],
    company_id: Optional[int],
    *,
    for_update: bool = False,
    require_active: bool = True,
):
    """Hamyonni korxona bo'yicha oladi.

    - `wallet_id` bo'sh bo'lsa `None`.
    - Topilmasa yoki (`require_active=True` da) nofaol bo'lsa 404.
    - `for_update=True` — balans o'zgartiriladigan joylarda qator qulflanadi.
    """
    if not wallet_id:
        return None
    from app.models.moliya import Wallet
    q = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == company_id)
    if for_update:
        q = q.with_for_update()
    wallet = q.first()
    if not wallet or (require_active and wallet.is_active is False):
        raise HTTPException(status_code=404, detail=WALLET_NOT_FOUND)
    return wallet


def get_company_user(db: Session, user_id: Optional[int], company_id: Optional[int]):
    """Foydalanuvchini korxona bo'yicha oladi (T0.4).

    `users.company_id == company_id` yoki shu korxonada faol `UserCompany` a'zoligi
    bo'lsa qaytaradi; aks holda 404 "Foydalanuvchi topilmadi" (mavjudligi oshkor qilinmaydi).
    """
    from app.models.user import User
    from app.models.user_company import UserCompany
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if not user:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
    if user.company_id != company_id:
        member = db.query(UserCompany.id).filter(
            UserCompany.user_id == user.id,
            UserCompany.company_id == company_id,
            UserCompany.is_active == True,  # noqa: E712
        ).first()
        if member is None:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
    return user


def get_company_branch(db: Session, branch_id: Optional[int], company_id: Optional[int]):
    """Filialni korxona bo'yicha oladi; `branch_id` bo'sh bo'lsa `None`, topilmasa 400."""
    if not branch_id:
        return None
    from app.models.branch import Branch
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    if not branch:
        raise HTTPException(status_code=400, detail=BRANCH_NOT_FOUND)
    return branch


# Kassa bo'yicha biriktirishsiz ham ishlay oladigan rollar (o'z korxonasida)
WALLET_FREE_ROLES = ("admin", "director", "manager")


def user_can_use_wallet(db: Session, user, wallet) -> bool:
    """Foydalanuvchi shu kassa bilan ishlay oladimi (T0.35: kassalararo o'tkazma).

    - `super_admin` — har doim;
    - `admin/director/manager` — faqat o'z korxonasi kassasida;
    - qolganlar — `user_wallets` da shu kassaga biriktirilgan bo'lsa.
    """
    if user is None or wallet is None:
        return False
    role = getattr(user.role, "value", user.role)
    if role == "super_admin":
        return True
    if wallet.company_id != user.company_id:
        return False
    if role in WALLET_FREE_ROLES:
        return True
    from app.models.user import UserWallet
    return db.query(UserWallet.user_id).filter(
        UserWallet.user_id == user.id,
        UserWallet.wallet_id == wallet.id,
    ).first() is not None
