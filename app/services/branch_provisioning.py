"""Filial provisioning va "asosiy" ombor/filial yordamchilari (T1.4).

- `provision_branch` — yangi filial uchun default ombor va kassa yaratadi (chaqiruvchi tranzaksiyasida,
  commit qilmaydi).
- `get_default_warehouse` — filialning asosiy savdo ombori (`is_default`), bo'lmasa main/shop turidagi
  birinchi faol ombor.
- `set_default_warehouse` — filialdagi boshqa `is_default` ni o'chirib, shu omborni asosiy qiladi.
- `get_main_branch` — korxonaning asosiy filiali (`is_main`), bo'lmasa eng kichik id li filial.
"""
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.moliya import Wallet
from app.models.warehouse import Warehouse, WarehouseType

# Asosiy savdo ombori bo'la oladigan ombor turlari
DEFAULT_CANDIDATE_TYPES = (WarehouseType.main, WarehouseType.shop)

DEFAULT_WAREHOUSE_NAME = "Asosiy ombor"
DEFAULT_WALLET_NAME = "Asosiy kassa"


def provision_branch(
    db: Session,
    branch: Branch,
    *,
    create_warehouse: bool = True,
    create_wallet: bool = True,
    warehouse_name: Optional[str] = None,
    wallet_name: Optional[str] = None,
) -> Tuple[Optional[Warehouse], Optional[Wallet]]:
    """Filial uchun default ombor (asosiy, `is_default=True`) va kassa yaratadi.

    `branch` flush qilingan (id va company_id bor) bo'lishi shart. Commit qilmaydi —
    chaqiruvchi bitta tranzaksiyada saqlaydi. Kassa yopiq (`is_open=False`) yaratiladi
    (`kassa.create_wallet` bilan bir xil).
    """
    wh = None
    wallet = None
    if create_warehouse:
        wh = Warehouse(
            name=(warehouse_name or "").strip() or DEFAULT_WAREHOUSE_NAME,
            type=WarehouseType.main,
            company_id=branch.company_id,
            branch_id=branch.id,
            is_active=True,
            is_default=True,
        )
        db.add(wh)
    if create_wallet:
        wallet = Wallet(
            name=(wallet_name or "").strip() or DEFAULT_WALLET_NAME,
            type="cash",
            company_id=branch.company_id,
            branch_id=branch.id,
            is_active=True,
            is_open=False,
        )
        db.add(wallet)
    db.flush()
    return wh, wallet


def get_default_warehouse(db: Session, company_id: Optional[int], branch_id: Optional[int]) -> Optional[Warehouse]:
    """Filialning asosiy savdo ombori: avval `is_default AND is_active`, bo'lmasa
    `type IN (main, shop)` bo'yicha `ORDER BY id`. Topilmasa `None`."""
    if branch_id is None:
        return None
    base = db.query(Warehouse).filter(
        Warehouse.company_id == company_id,
        Warehouse.branch_id == branch_id,
        Warehouse.is_active == True,  # noqa: E712
    )
    wh = base.filter(Warehouse.is_default == True).order_by(Warehouse.id).first()  # noqa: E712
    if wh:
        return wh
    return base.filter(Warehouse.type.in_(DEFAULT_CANDIDATE_TYPES)).order_by(Warehouse.id).first()


def set_default_warehouse(db: Session, wh: Warehouse) -> Warehouse:
    """`wh` ni filialining asosiy ombori qiladi, shu filialdagi boshqalarning belgisini o'chiradi.
    Filialsiz ombor uchun hech narsa qilmaydi (indeks faqat filialli omborlarga)."""
    if wh.branch_id is None:
        return wh
    db.query(Warehouse).filter(
        Warehouse.branch_id == wh.branch_id,
        Warehouse.id != wh.id,
        Warehouse.is_default == True,  # noqa: E712
    ).update({Warehouse.is_default: False}, synchronize_session="fetch")
    db.flush()
    wh.is_default = True
    db.flush()
    return wh


def reassign_default_warehouse(db: Session, branch_id: Optional[int], *, exclude_id: Optional[int] = None) -> Optional[Warehouse]:
    """Filialda faol asosiy ombor qolmagan bo'lsa, boshqa faol main/shop omborni asosiy qiladi.
    Filialda faol `is_default` ombor bor bo'lsa, o'zgartirmaydi. Yangi asosiy ombor yoki `None`."""
    if branch_id is None:
        return None
    base = db.query(Warehouse).filter(
        Warehouse.branch_id == branch_id,
        Warehouse.is_active == True,  # noqa: E712
    )
    if exclude_id is not None:
        base = base.filter(Warehouse.id != exclude_id)
    if base.filter(Warehouse.is_default == True).first():  # noqa: E712
        return None
    cand = base.filter(Warehouse.type.in_(DEFAULT_CANDIDATE_TYPES)).order_by(Warehouse.id).first()
    if cand:
        set_default_warehouse(db, cand)
    return cand


def get_main_branch(db: Session, company_id: Optional[int]) -> Optional[Branch]:
    """Korxonaning asosiy filiali: faol `is_main`, bo'lmasa eng kichik id li faol filial,
    faol yo'q bo'lsa har qanday eng kichik id li filial. Topilmasa `None`."""
    if company_id is None:
        return None
    base = db.query(Branch).filter(Branch.company_id == company_id)
    br = base.filter(Branch.is_main == True, Branch.is_active == True).first()  # noqa: E712
    if br:
        return br
    br = base.filter(Branch.is_active == True).order_by(Branch.id).first()  # noqa: E712
    if br:
        return br
    return base.order_by(Branch.id).first()


NO_BRANCH_COMPANY = "Korxonada filial yo'q. Avval Sozlamalar → Filiallar bo'limida filial yarating"


def fallback_branch_id(db: Session, user, *, wallet=None, warehouse_id: Optional[int] = None) -> Optional[int]:
    """Joriy filial aniqlanmagan holda tranzaksiya filiali: kassa filiali → ombor filiali →
    korxonaning ASOSIY filiali (`get_main_branch`, "birinchi filial" o'rniga). Hammasi faqat
    `user.company_id` doirasida. Topilmasa `None`."""
    company_id = getattr(user, "company_id", None)

    def _own(branch_id) -> Optional[int]:
        if not branch_id:
            return None
        row = db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
        return row[0] if row else None

    found = _own(getattr(wallet, "branch_id", None)) if wallet is not None else None
    if found:
        return found
    if warehouse_id:
        wh = db.query(Warehouse.branch_id).filter(
            Warehouse.id == warehouse_id, Warehouse.company_id == company_id,
        ).first()
        found = _own(wh[0] if wh else None)
        if found:
            return found
    main = get_main_branch(db, company_id)
    return main.id if main else None


def fallback_branch_id_or_400(db: Session, user, *, wallet=None, warehouse_id: Optional[int] = None) -> int:
    """`fallback_branch_id`; filial topilmasa 400."""
    from fastapi import HTTPException
    branch_id = fallback_branch_id(db, user, wallet=wallet, warehouse_id=warehouse_id)
    if branch_id is None:
        raise HTTPException(status_code=400, detail=NO_BRANCH_COMPANY)
    return branch_id
