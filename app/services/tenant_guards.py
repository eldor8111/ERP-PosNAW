"""Korxona (tenant) chegarasini tekshirib resurs olish — umumiy yordamchilar.

`db.get(Model, id)` o'rniga ishlatiladi: ombor, mijoz, mahsulot, variant va kassa
faqat `id` emas, `id` VA `company_id` bo'yicha olinadi, shuning uchun boshqa
korxona resursiga tegib bo'lmaydi (IDOR). Topilmasa `HTTPException(404)`.

Kassa uchun `app.services.wallet_access.get_company_wallet` (T0.3) qayta
ishlatiladi; bu yerdagi `get_company_wallet` unga `require_open` (kassa ochiqligi)
tekshiruvini qo'shadi. DIQQAT: argument tartibi `(db, company_id, wallet_id)`.
"""
# pyright: reportMissingImports=false
from typing import Dict, Iterable, Optional

from fastapi import HTTPException  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.models.user import UserRole
from app.services.wallet_access import get_company_wallet as _get_company_wallet

# Filialga bog'lanmagan rollar — korxonaning istalgan ombori bilan ishlay oladi
BRANCH_FREE_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)

WAREHOUSE_NOT_FOUND = "Ombor topilmadi"
WAREHOUSE_OTHER_BRANCH = "Bu ombor sizning filialingizga tegishli emas"
CUSTOMER_NOT_FOUND = "Mijoz topilmadi"
PRODUCT_NOT_FOUND = "Mahsulot topilmadi"
VARIANT_NOT_OF_PRODUCT = "Variant mahsulotga tegishli emas"
WALLET_CLOSED = "Kassa yopiq"
WALLET_SELECT = "Kassa tanlang"
BRANCH_INVALID = "Filial topilmadi yoki boshqa korxonaga tegishli"
ROLE_INVALID = "Rol topilmadi yoki boshqa korxonaga tegishli"


def get_company_warehouse(
    db: Session,
    user,
    warehouse_id: Optional[int],
    *,
    enforce_branch: bool = True,
    require_active: bool = True,
):
    """Omborni foydalanuvchi korxonasi bo'yicha oladi.

    - Topilmasa yoki (`require_active=True` da) nofaol bo'lsa 404.
    - `enforce_branch=True` va rol admin/director/super_admin bo'lmasa, filialli
      foydalanuvchi uchun `Warehouse.branch_id == user.branch_id` talab qilinadi (403).
      Filialsiz foydalanuvchida faqat korxona va faollik tekshiriladi.
    """
    from app.models.warehouse import Warehouse
    if not warehouse_id:
        raise HTTPException(status_code=404, detail=WAREHOUSE_NOT_FOUND)
    wh = db.query(Warehouse).filter(
        Warehouse.id == warehouse_id,
        Warehouse.company_id == user.company_id,
    ).first()
    if not wh or (require_active and wh.is_active is False):
        raise HTTPException(status_code=404, detail=WAREHOUSE_NOT_FOUND)
    if enforce_branch and user.role not in BRANCH_FREE_ROLES and user.branch_id:
        if wh.branch_id != user.branch_id:
            raise HTTPException(status_code=403, detail=WAREHOUSE_OTHER_BRANCH)
    return wh


def get_company_customer(db: Session, company_id: Optional[int], customer_id: Optional[int], *, for_update: bool = False):
    """Mijozni korxona bo'yicha oladi; topilmasa 404. `for_update=True` — qarz o'zgaradigan joylarda qulf."""
    from app.models.customer import Customer
    if not customer_id:
        raise HTTPException(status_code=404, detail=CUSTOMER_NOT_FOUND)
    q = db.query(Customer).filter(Customer.id == customer_id, Customer.company_id == company_id)
    if for_update:
        q = q.with_for_update()
    customer = q.first()
    if not customer:
        raise HTTPException(status_code=404, detail=CUSTOMER_NOT_FOUND)
    return customer


def get_company_product(db: Session, company_id: Optional[int], product_id: Optional[int]):
    """Mahsulotni korxona bo'yicha oladi (o'chirilmagan); topilmasa 404."""
    from app.models.product import Product
    if not product_id:
        raise HTTPException(status_code=404, detail=f"{PRODUCT_NOT_FOUND}: {product_id}")
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.company_id == company_id,
        Product.is_deleted == False,  # noqa: E712
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"{PRODUCT_NOT_FOUND}: {product_id}")
    return product


def get_company_products(db: Session, company_id: Optional[int], product_ids: Iterable[int]) -> Dict[int, object]:
    """Bir nechta mahsulotni bitta so'rovda oladi: {id: Product}. Birortasi topilmasa 404 (qaysi ID ekani bilan)."""
    from app.models.product import Product
    ids = {int(i) for i in product_ids if i}
    if not ids:
        return {}
    rows = db.query(Product).filter(
        Product.id.in_(ids),
        Product.company_id == company_id,
        Product.is_deleted == False,  # noqa: E712
    ).all()
    found = {p.id: p for p in rows}
    for pid in sorted(ids):
        if pid not in found:
            raise HTTPException(status_code=404, detail=f"{PRODUCT_NOT_FOUND}: {pid}")
    return found


def get_company_variant(db: Session, product_id: int, variant_id: Optional[int]):
    """Variant aynan shu mahsulotga tegishli ekanini tekshiradi; aks holda 400.
    Mahsulot allaqachon korxonaga tekshirilgan bo'lishi kerak."""
    from app.models.product_variant import ProductVariant
    if not variant_id:
        return None
    variant = db.query(ProductVariant).filter(
        ProductVariant.id == variant_id,
        ProductVariant.product_id == product_id,
    ).first()
    if not variant:
        raise HTTPException(status_code=400, detail=VARIANT_NOT_OF_PRODUCT)
    return variant


def get_company_wallet(
    db: Session,
    company_id: Optional[int],
    wallet_id: Optional[int],
    *,
    for_update: bool = True,
    require_open: bool = True,
):
    """Kassani korxona bo'yicha oladi (faol bo'lishi shart, 404);
    `require_open=True` da yopiq kassa 400 "Kassa yopiq". `wallet_id` bo'sh bo'lsa `None`."""
    wallet = _get_company_wallet(db, wallet_id, company_id, for_update=for_update, require_active=True)
    if wallet is not None and require_open and wallet.is_open is False:
        raise HTTPException(status_code=400, detail=WALLET_CLOSED)
    return wallet


def find_default_wallet(db: Session, user, *, for_update: bool = True):
    """Foydalanuvchining default kassasi (`user_wallets`), bo'lmasa korxonaning birinchi
    ochiq va faol kassasi (sale_create mantiqi). Topilmasa `None`."""
    from app.models.moliya import Wallet
    from app.models.user import UserWallet
    uw = (
        db.query(UserWallet)
        .filter(UserWallet.user_id == user.id)
        .order_by(UserWallet.is_default.desc())
        .first()
    )
    if uw and uw.wallet_id:
        q = db.query(Wallet).filter(
            Wallet.id == uw.wallet_id,
            Wallet.company_id == user.company_id,
            Wallet.is_open == True,  # noqa: E712
            Wallet.is_active == True,  # noqa: E712
        )
        if for_update:
            q = q.with_for_update()
        w = q.first()
        if w:
            return w
    q = db.query(Wallet).filter(
        Wallet.company_id == user.company_id,
        Wallet.is_open == True,  # noqa: E712
        Wallet.is_active == True,  # noqa: E712
    ).order_by(Wallet.id.asc())
    if for_update:
        q = q.with_for_update()
    return q.first()


def validate_branch(db: Session, branch_id: Optional[int], company_id: Optional[int], *, require_active: bool = True):
    """Mijoz yuborgan `branch_id` shu korxonaga tegishli (va faol) ekanini tekshiradi (T0.9).

    `branch_id is None` bo'lsa `None` qaytaradi (filial ixtiyoriy). Mavjud bo'lmagan,
    begona korxonaniki yoki (`require_active=True` da) nofaol filial uchun 400."""
    if branch_id is None:
        return None
    from app.models.branch import Branch
    q = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id)
    if require_active:
        q = q.filter(Branch.is_active == True)  # noqa: E712
    branch = q.first()
    if not branch:
        raise HTTPException(status_code=400, detail=BRANCH_INVALID)
    return branch


def validate_role(db: Session, role_id: Optional[int], company_id: Optional[int]):
    """Mijoz yuborgan `role_id` shu korxonaniki yoki global (`company_id IS NULL`) tizim roli
    ekanini tekshiradi (T0.9). `role_id is None` bo'lsa `None`; aks holda topilmasa 400."""
    if role_id is None:
        return None
    from sqlalchemy import or_  # type: ignore
    from app.models.role import Role
    role = db.query(Role).filter(
        Role.id == role_id,
        or_(Role.company_id == company_id, Role.company_id.is_(None)),
    ).first()
    if not role:
        raise HTTPException(status_code=400, detail=ROLE_INVALID)
    return role


NO_BRANCH_COMPANY = "Korxonada filial yo'q. Avval Sozlamalar → Filiallar bo'limida filial yarating"


def find_tx_branch(
    db: Session,
    user,
    *,
    explicit_branch_id: Optional[int] = None,
    wallet=None,
    warehouse_id: Optional[int] = None,
) -> Optional[int]:
    """Tranzaksiya uchun filial id sini aniqlaydi (T0.7). Topilmasa `None`.

    Tartib (har bir qadamda filial `user.company_id` ga tegishli va mavjud bo'lishi shart,
    aks holda keyingisiga o'tiladi):
      1. `explicit_branch_id` (`validate_branch` bilan — begona/mavjud emas bo'lsa 400);
      2. `user.branch_id`;
      3. `wallet.branch_id`;
      4. `warehouse_id` omborining filiali (ombor faqat o'z korxonasidan);
      5. korxonaning birinchi FAOL filiali (`order_by(Branch.id)`), faol yo'q bo'lsa har qanday birinchi.
    """
    from app.models.branch import Branch
    from app.models.warehouse import Warehouse

    company_id = getattr(user, "company_id", None)

    if explicit_branch_id:
        return validate_branch(db, explicit_branch_id, company_id).id

    def _own_branch(branch_id: Optional[int]) -> Optional[int]:
        if not branch_id:
            return None
        br = db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
        return br[0] if br else None

    found = _own_branch(getattr(user, "branch_id", None))
    if found:
        return found
    if wallet is not None:
        found = _own_branch(getattr(wallet, "branch_id", None))
        if found:
            return found
    if warehouse_id:
        wh = db.query(Warehouse.branch_id).filter(
            Warehouse.id == warehouse_id,
            Warehouse.company_id == company_id,
        ).first()
        found = _own_branch(wh[0] if wh else None)
        if found:
            return found
    if company_id is None:
        return None
    br = db.query(Branch.id).filter(
        Branch.company_id == company_id,
        Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id.asc()).first()
    if not br:
        br = db.query(Branch.id).filter(Branch.company_id == company_id).order_by(Branch.id.asc()).first()
    return br[0] if br else None


def resolve_tx_branch(
    db: Session,
    user,
    *,
    explicit_branch_id: Optional[int] = None,
    wallet=None,
    warehouse_id: Optional[int] = None,
) -> int:
    """`find_tx_branch` natijasi; filial topilmasa 400 (0/1 fallback yo'q)."""
    branch_id = find_tx_branch(
        db, user, explicit_branch_id=explicit_branch_id, wallet=wallet, warehouse_id=warehouse_id,
    )
    if branch_id is None:
        raise HTTPException(status_code=400, detail=NO_BRANCH_COMPANY)
    return branch_id
