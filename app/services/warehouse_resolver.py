"""Sotuv/buyurtma/kirim uchun ombor tanlashning yagona qoidasi (T1.5).

`resolve_warehouse` tartibsiz `.first()` va boshqa filialga jim fallback o'rniga ishlatiladi:

  1. `requested_id` berilsa — korxonaniki va faol bo'lishi shart (aks holda 404); `user` berilgan
     bo'lsa non-bypass xodim uchun ruxsat etilgan filial omborida bo'lishi shart (aks holda 403).
  2. Aks holda filial: `branch_id` -> `customer_branch_id` (buyurtma uchun `Order.branch_id`) ->
     `effective_branch_id(user)`.
  3. Filial aniq bo'lsa — uning asosiy savdo ombori (`is_default`, bo'lmasa shop > main, eng kichik id).
     Topilmasa 409 "Filialda faol savdo ombori yo'q". Boshqa filialga o'tilmaydi.
  4. Filial aniq bo'lmasa — korxonada <=1 faol filial bo'lsa o'sha filial ombori yoki filialsiz
     (`branch_id IS NULL`) main/shop ombor; 2+ filial bo'lsa 400 "Ombor yoki filialni tanlang".
  5. `purpose="sale"`/`"order"` uchun faqat `main`/`shop`; `returns`, `transit`, `raw_material`,
     `wip` hech qachon avto-tanlanmaydi. `purpose="receive"` ham `returns`/`transit` ni tanlamaydi;
     faqat main/shop topilmasa oxirgi chora sifatida `raw_material`/`wip` (kirim uchun) olinadi.
"""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.warehouse import Warehouse, WarehouseType

SALE_TYPES = (WarehouseType.main, WarehouseType.shop)
RECEIVE_EXTRA_TYPES = (WarehouseType.raw_material, WarehouseType.wip)
_TYPE_RANK = {WarehouseType.shop: 0, WarehouseType.main: 1}

NO_BRANCH_WAREHOUSE = "Filialda faol savdo ombori yo'q"
CHOOSE_WAREHOUSE_OR_BRANCH = "Ombor yoki filialni tanlang"
WAREHOUSE_NOT_FOUND = "Ombor topilmadi"
BRANCH_NOT_FOUND = "Filial topilmadi"


def _pick(rows: List[Warehouse]) -> Optional[Warehouse]:
    """Asosiy (`is_default`) ombor, bo'lmasa shop > main, keyin eng kichik id."""
    if not rows:
        return None
    return min(rows, key=lambda w: (0 if w.is_default else 1, _TYPE_RANK.get(w.type, 2), w.id))


def _auto_pick(db: Session, company_id: int, branch_id: Optional[int], purpose: str) -> Optional[Warehouse]:
    """Filial (yoki `None` — filialsiz omborlar) ichidan avto-tanlov; hech qachon boshqa filialga o'tmaydi."""
    base = db.query(Warehouse).filter(
        Warehouse.company_id == company_id,
        Warehouse.is_active == True,  # noqa: E712
    )
    if branch_id is None:
        base = base.filter(Warehouse.branch_id.is_(None))
    else:
        base = base.filter(Warehouse.branch_id == branch_id)
    wh = _pick(base.filter(Warehouse.type.in_(SALE_TYPES)).order_by(Warehouse.id).all())
    if wh is None and purpose == "receive":
        wh = _pick(base.filter(Warehouse.type.in_(RECEIVE_EXTRA_TYPES)).order_by(Warehouse.id).all())
    return wh


def _check_company_branch(db: Session, company_id: int, branch_id: int) -> int:
    row = db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
    return row[0]


def resolve_warehouse(
    db: Session,
    company_id: int,
    *,
    requested_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    customer_branch_id: Optional[int] = None,
    purpose: str = "sale",
    user=None,
) -> int:
    """Ombor id'sini aniqlaydi (yuqoridagi qoidalar). Xatolar: 404/403 (so'ralgan ombor),
    409 (filialda ombor yo'q), 400 (filial ham, ombor ham aniq emas)."""
    # 1. So'ralgan ombor
    if requested_id:
        if user is not None:
            from app.services.sale_helpers import validate_sale_warehouse
            return validate_sale_warehouse(db, user, requested_id, company_id=company_id).id
        wh = db.query(Warehouse).filter(
            Warehouse.id == requested_id, Warehouse.company_id == company_id,
        ).first()
        if not wh or wh.is_active is False:
            raise HTTPException(status_code=404, detail=WAREHOUSE_NOT_FOUND)
        return wh.id

    # 2. Filial
    branch = branch_id or customer_branch_id
    if not branch and user is not None:
        from app.core.branch_context import effective_branch_id
        branch = effective_branch_id(db, user)
    if branch:
        _check_company_branch(db, company_id, branch)

    # 3. Filial aniq: faqat shu filial ombori
    if branch:
        wh = _auto_pick(db, company_id, branch, purpose)
        if wh is None:
            raise HTTPException(status_code=409, detail=NO_BRANCH_WAREHOUSE)
        return wh.id

    # 4. Filial aniq emas
    active_ids = [r[0] for r in db.query(Branch.id).filter(
        Branch.company_id == company_id, Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id).limit(2).all()]
    if len(active_ids) >= 2:
        raise HTTPException(status_code=400, detail=CHOOSE_WAREHOUSE_OR_BRANCH)
    if active_ids:
        wh = _auto_pick(db, company_id, active_ids[0], purpose)
        if wh is not None:
            return wh.id
    wh = _auto_pick(db, company_id, None, purpose)
    if wh is None:
        raise HTTPException(status_code=409, detail=NO_BRANCH_WAREHOUSE)
    return wh.id
