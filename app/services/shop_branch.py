"""Telegram Mini App / mijoz bot uchun filial tanlash yordamchilari (T3.13).

Mijoz "olib ketish" filialini tanlaydi; qoldiq va buyurtma shu filialning do'kon (shop)
omborlari bo'yicha hisoblanadi. Buyurtma filiali quyidagi tartibda aniqlanadi (`resolve_order_branch`):
  so'ralgan filial -> mijoz filiali -> korxona standart filiali -> yagona pickup filial
  -> eng kichik id li pickup filial -> 400.
"""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.warehouse import Warehouse, WarehouseType
from app.services.warehouse_scope import NON_SELLABLE_TYPES

BRANCH_NOT_PICKUP = "Tanlangan filial topilmadi yoki do'kon ombori yo'q"
NO_SHOP_BRANCH = "Do'konda faol filial topilmadi"


def _looks_like_shop(name: str) -> bool:
    n = (name or "").lower()
    for ch in ("'", "ʼ", "’", "`"):
        n = n.replace(ch, "")
    return "dokon" in n or "shop" in n or "магазин" in n


def shop_warehouses(db: Session, company_id: int, branch_id: Optional[int] = None) -> List[Warehouse]:
    """Mijozlarga ko'rsatiladigan (do'kon) omborlar, id bo'yicha tartiblangan.

    Amaliyotda WarehouseType.shop deyarli ishlatilmaydi — foydalanuvchilar ombor turini "main"
    holida qoldirib, faqat nomini "Do'kon" deb qo'yishadi. Shuning uchun avval type=shop (korxona
    bo'yicha), topilmasa nomi "do'kon"/"dokon"/"shop" so'zini o'z ichiga olgan faol omborlar olinadi.
    Xom ashyo/WIP/tranzit omborlari hech qachon kirmaydi. `branch_id` berilsa — faqat shu filial
    omborlari (to'plam avval butun korxona bo'yicha aniqlanadi, shuning uchun filiallar o'rtasida
    qoida bir xil bo'ladi).
    """
    typed = db.query(Warehouse).filter(
        Warehouse.company_id == company_id,
        Warehouse.type == WarehouseType.shop,
        Warehouse.is_active == True,  # noqa: E712
    ).order_by(Warehouse.id).all()
    if typed:
        rows = typed
    else:
        all_active = db.query(Warehouse).filter(
            Warehouse.company_id == company_id,
            Warehouse.is_active == True,  # noqa: E712
            Warehouse.type.notin_(NON_SELLABLE_TYPES),
        ).order_by(Warehouse.id).all()
        rows = [w for w in all_active if _looks_like_shop(w.name)]
    if branch_id is not None:
        sole = _sole_active_branch_id(db, company_id)
        rows = [w for w in rows if _warehouse_branch(w, sole) == branch_id]
    return rows


def _sole_active_branch_id(db: Session, company_id: int) -> Optional[int]:
    """Korxonada aynan bitta faol filial bo'lsa uning id si, aks holda `None`."""
    ids = db.query(Branch.id).filter(
        Branch.company_id == company_id,
        Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id).limit(2).all()
    return ids[0][0] if len(ids) == 1 else None


def _warehouse_branch(w: Warehouse, sole_branch_id: Optional[int]) -> Optional[int]:
    """Ombor filiali; filialsiz (eski) do'kon ombori yagona faol filialga tegishli deb hisoblanadi —
    bir filialli korxonada hech narsa o'zgarmasin."""
    return w.branch_id or sole_branch_id


def list_pickup_branches(db: Session, company_id: int) -> List[Branch]:
    """Faol filiallar, kamida bitta do'kon omboriga ega (id bo'yicha)."""
    sole = _sole_active_branch_id(db, company_id)
    branch_ids = {_warehouse_branch(w, sole) for w in shop_warehouses(db, company_id)} - {None}
    if not branch_ids:
        return []
    return db.query(Branch).filter(
        Branch.company_id == company_id,
        Branch.is_active == True,  # noqa: E712
        Branch.id.in_(branch_ids),
    ).order_by(Branch.id).all()


def resolve_order_branch(db: Session, company, customer, requested_branch_id: Optional[int] = None) -> int:
    """Buyurtma filialini aniqlaydi (modul docstring'idagi tartib). Xatolar: 400."""
    pickup_ids = [b.id for b in list_pickup_branches(db, company.id)]

    if requested_branch_id:
        if requested_branch_id not in pickup_ids:
            raise HTTPException(status_code=400, detail=BRANCH_NOT_PICKUP)
        return requested_branch_id

    cust_branch = getattr(customer, "branch_id", None)
    if cust_branch and cust_branch in pickup_ids:
        return cust_branch

    default_branch = getattr(company, "shop_default_branch_id", None)
    if default_branch and default_branch in pickup_ids:
        return default_branch

    if pickup_ids:
        # list_pickup_branches id bo'yicha tartiblangan: yagona yoki eng kichik id
        return pickup_ids[0]

    raise HTTPException(status_code=400, detail=NO_SHOP_BRANCH)


def pick_fulfillment_warehouse(db: Session, company_id: int, branch_id: Optional[int]) -> Optional[Warehouse]:
    """Filialning birinchi faol do'kon ombori (type=shop ustuvor, keyin eng kichik id); yo'q bo'lsa `None`."""
    if not branch_id:
        return None
    rows = shop_warehouses(db, company_id, branch_id)
    if not rows:
        return None
    return min(rows, key=lambda w: (0 if w.type == WarehouseType.shop else 1, w.id))


def default_branch_for_new_customer(db: Session, company) -> Optional[int]:
    """Botdan ro'yxatdan o'tgan yangi mijoz uchun filial: korxona standart filiali (faol bo'lsa),
    aks holda yagona faol filial, aks holda `None`."""
    default_branch = getattr(company, "shop_default_branch_id", None)
    if default_branch:
        row = db.query(Branch.id).filter(
            Branch.id == default_branch,
            Branch.company_id == company.id,
            Branch.is_active == True,  # noqa: E712
        ).first()
        if row:
            return row[0]
    active = db.query(Branch.id).filter(
        Branch.company_id == company.id,
        Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id).limit(2).all()
    return active[0][0] if len(active) == 1 else None


def catalog_branch_id(db: Session, company, customer, requested_branch_id: Optional[int] = None) -> Optional[int]:
    """Mini App katalogi (qoldiq) uchun filial. So'ralgan filial pickup filiali bo'lishi shart (aks holda 400);
    so'ralmasa mijoz filiali, keyin korxona standart filiali (yaroqli bo'lsa). Hech biri bo'lmasa `None` —
    eski xatti-harakat: barcha do'kon omborlari yig'indisi."""
    pickup_ids = {b.id for b in list_pickup_branches(db, company.id)}
    if requested_branch_id:
        if requested_branch_id not in pickup_ids:
            raise HTTPException(status_code=400, detail=BRANCH_NOT_PICKUP)
        return requested_branch_id
    for candidate in (getattr(customer, "branch_id", None), getattr(company, "shop_default_branch_id", None)):
        if candidate and candidate in pickup_ids:
            return candidate
    return None
