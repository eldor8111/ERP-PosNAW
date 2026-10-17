from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.audit import log_action, log_action_for
from app.core.branch_context import BranchContext, apply_branch_scope, effective_branch_id, get_branch_context
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.services.branch_provisioning import (
    DEFAULT_CANDIDATE_TYPES, reassign_default_warehouse, set_default_warehouse,
)
from app.services.tenant_guards import BRANCH_INVALID, validate_branch
from app.schemas.warehouse import WarehouseCreate, WarehouseOut, WarehouseUpdate
from app.services.tariff_guard import check_warehouse_limit
from app.services.warehouse_access import list_company_warehouses

# T1.1: joriy filial konteksti (X-Branch-Id) barcha ombor endpointlarida db.info ga yoziladi
router = APIRouter(prefix="/warehouses", tags=["Warehouses"], dependencies=[Depends(get_branch_context)])

ADMIN_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)

DEFAULT_WH_REQUIRED = "Filialda kamida bitta asosiy ombor bo'lishi kerak"
DEFAULT_WH_NEEDS_BRANCH = "Asosiy ombor filialga bog'langan bo'lishi kerak"


def _wh_snapshot(wh: Warehouse) -> dict:
    """Audit uchun ombor holati (Enum qiymati matn sifatida)."""
    return {"name": wh.name, "type": getattr(wh.type, "value", wh.type),
            "is_active": wh.is_active, "branch_id": wh.branch_id,
            "is_default": bool(wh.is_default)}


def _auto_branch_id(db: Session, user: User, ctx: BranchContext):
    """Filial berilmagan ombor uchun filial: joriy filial (header / biriktirilgan), bo'lmasa
    korxonadagi yagona faol filial, aks holda `None`."""
    if ctx.branch_id is not None:
        return ctx.branch_id
    eff = effective_branch_id(db, user)
    if eff is not None:
        return eff
    rows = db.query(Branch.id).filter(
        Branch.company_id == user.company_id, Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id).limit(2).all()
    return rows[0][0] if len(rows) == 1 else None


def _assert_warehouse_closable(db: Session, wh: Warehouse) -> None:
    """T1.12: omborni nofaol qilishdan oldin — qoldiq (manfiy ham) yoki ochiq hujjat bo'lsa 409 (matnli detail)."""
    from sqlalchemy import func, or_

    from app.models.inventory import StockLevel
    from app.models.inventory_count import CountStatus, InventoryCount
    from app.models.production_order import ProductionOrder, ProductionOrderStatus
    from app.models.purchase_order import POStatus, PurchaseOrder
    from app.models.transfer import StockTransfer, TransferStatus

    products = db.query(func.count(func.distinct(StockLevel.product_id))).filter(
        StockLevel.warehouse_id == wh.id, StockLevel.quantity != 0,
    ).scalar() or 0
    if products:
        raise HTTPException(status_code=409, detail=f"Omborda qoldiq bor: {int(products)} ta mahsulot")

    docs = []

    def _add(n, label):
        if n:
            docs.append(f"{int(n)} ta {label}")

    _add(db.query(func.count(StockTransfer.id)).filter(
        StockTransfer.status.in_([TransferStatus.pending, TransferStatus.in_transit]),
        or_(StockTransfer.from_warehouse_id == wh.id, StockTransfer.to_warehouse_id == wh.id),
    ).scalar(), "kutilayotgan ko'chirish")
    _add(db.query(func.count(PurchaseOrder.id)).filter(
        PurchaseOrder.warehouse_id == wh.id,
        PurchaseOrder.status.in_([POStatus.draft, POStatus.sent, POStatus.partial]),
    ).scalar(), "ochiq xarid buyurtmasi")
    _add(db.query(func.count(InventoryCount.id)).filter(
        InventoryCount.warehouse_id == wh.id,
        InventoryCount.status.in_([CountStatus.draft, CountStatus.in_progress]),
    ).scalar(), "ochiq inventarizatsiya")
    _add(db.query(func.count(ProductionOrder.id)).filter(
        or_(ProductionOrder.warehouse_id == wh.id, ProductionOrder.target_warehouse_id == wh.id),
        ProductionOrder.status.in_([ProductionOrderStatus.draft, ProductionOrderStatus.in_progress]),
    ).scalar(), "ochiq ishlab chiqarish")
    if docs:
        raise HTTPException(status_code=409, detail="Omborda ochiq hujjatlar bor: " + ", ".join(docs))


def _is_default_candidate(wh: Warehouse) -> bool:
    return wh.type in DEFAULT_CANDIDATE_TYPES and wh.is_active is not False


def _branch_has_default(db: Session, branch_id: int, exclude_id=None) -> bool:
    q = db.query(Warehouse.id).filter(
        Warehouse.branch_id == branch_id,
        Warehouse.is_default == True,  # noqa: E712
        Warehouse.is_active == True,  # noqa: E712
    )
    if exclude_id is not None:
        q = q.filter(Warehouse.id != exclude_id)
    return q.first() is not None


@router.get("", response_model=List[WarehouseOut])
def list_warehouses(
    scope: Literal["context", "all"] = Query("context", description="context — joriy filial konteksti; all — korxonaning barcha omborlari"),
    branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari"),
    include_inactive: bool = Query(False, description="Nofaol omborlar ham qaytarilsin"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    # T3.1: nofaol omborlar faqat admin/director/super_admin uchun; boshqa rollarga majburan faqat faollar
    if current_user.role not in ADMIN_ROLES:
        include_inactive = False
    # T1.1: admin/director header'siz barcha filiallarni, qolganlar o'z filialini ko'radi.
    # T1.3: scope=all — korxonaning barcha omborlari (admin/director/manager/warehouse), filial nomi bilan
    whs = list_company_warehouses(
        db, current_user, ctx, scope=scope, branch_id=branch_id, include_inactive=include_inactive,
    )
    return [
        WarehouseOut.model_validate(w).model_copy(update={"branch_name": w.branch.name if w.branch else None})
        for w in whs
    ]


@router.post("", response_model=WarehouseOut)
def create_warehouse(
    data: WarehouseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    wh = Warehouse(**data.model_dump(exclude={"is_default"}))
    if current_user.role == UserRole.super_admin and data.branch_id is None:
        # T1.12: super admin yaratgan ombor korxonasiz (company_id NULL) qolmasin
        raise HTTPException(status_code=400, detail="Korxonani aniqlash uchun filial ko'rsating")
    if current_user.role != UserRole.super_admin:
        # T0.9: filial shu korxonaniki va faol bo'lishi shart
        validate_branch(db, data.branch_id, current_user.company_id)
        wh.company_id = current_user.company_id
        if data.branch_id is None:
            # T1.4 (MODEL-09): filial berilmasa joriy filial, bo'lmasa korxonadagi yagona faol filial —
            # aks holda ombor filial doirasidagi ro'yxatlardan yo'qoladi
            wh.branch_id = _auto_branch_id(db, current_user, ctx)
    elif data.branch_id is not None:
        # Super admin: korxonasi yo'q — filial mavjudligi tekshiriladi, ombor filial korxonasiga bog'lanadi
        from app.models.branch import Branch
        branch = db.query(Branch).filter(
            Branch.id == data.branch_id,
            Branch.is_active == True,  # noqa: E712
        ).first()
        if not branch:
            raise HTTPException(status_code=400, detail=BRANCH_INVALID)
        wh.company_id = branch.company_id
    # T3.9: tarif ombor limiti (rejim: settings.TARIFF_WAREHOUSE_LIMIT_MODE; super_admin o'tkaziladi)
    check_warehouse_limit(db, wh.company_id, current_user)
    db.add(wh)
    db.flush()
    if wh.branch_id is not None:
        if data.is_default:
            set_default_warehouse(db, wh)
        elif _is_default_candidate(wh) and not _branch_has_default(db, wh.branch_id, exclude_id=wh.id):
            # Filialdagi birinchi faol ombor avtomatik asosiy bo'ladi
            set_default_warehouse(db, wh)
    db.commit()
    db.refresh(wh)
    log_action(db, "CREATE", "warehouse", wh.id, user_id=current_user.id,
               new_values={"name": wh.name, "branch_id": wh.branch_id, "is_default": bool(wh.is_default)},
               company_id=wh.company_id, branch_id=wh.branch_id)
    db.commit()
    return wh


@router.get("/{wh_id}", response_model=WarehouseOut)
def get_warehouse(
    wh_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Warehouse).filter(Warehouse.id == wh_id)
    q = q.filter(Warehouse.company_id == current_user.company_id)
    wh = q.first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    return wh


@router.patch("/{wh_id}", response_model=WarehouseOut)
def update_warehouse(
    wh_id: int,
    data: WarehouseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    # T4.5: name/type/is_active uchun aniq null yuborish rad etiladi (jim e'tiborsiz qoldirilmaydi)
    nulls = [f for f in ("name", "type", "is_active") if f in data.model_fields_set and getattr(data, f) is None]
    if nulls:
        raise HTTPException(status_code=422, detail=f"Maydon bo'sh bo'lishi mumkin emas: {', '.join(nulls)}")
    q = db.query(Warehouse).filter(Warehouse.id == wh_id)
    q = q.filter(Warehouse.company_id == current_user.company_id)
    wh = q.first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    # exclude_unset: faqat yuborilgan maydonlar. branch_id uchun null ruxsat (omborni filialdan ajratish).
    old_values = _wh_snapshot(wh)
    old_branch_id = wh.branch_id
    was_default = bool(wh.is_default)
    want_default = None
    # T1.12: PATCH {is_active:false} ham DELETE bilan bir xil tekshiruvdan o'tadi (qoldiq/ochiq hujjat -> 409)
    if data.is_active is False and wh.is_active is not False:
        _assert_warehouse_closable(db, wh)
    # T3.9: nofaol omborni qayta yoqish ham tarif limitidan o'tadi (omborning o'zi sanalmaydi)
    if data.is_active is True and wh.is_active is False:
        check_warehouse_limit(db, wh.company_id, current_user, exclude_warehouse_id=wh.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "is_default":
            want_default = value  # None e'tiborsiz
            continue
        if value is None and field != "branch_id":
            continue
        if field == "branch_id":
            # T0.9; o'zgarmagan (forma qayta saqlanganda) nofaol filial tahrirlashni to'smasin
            validate_branch(db, value, current_user.company_id, require_active=value != wh.branch_id)
        setattr(wh, field, value)

    # T1.4: asosiy (default) ombor qoidalari
    branch_changed = wh.branch_id != old_branch_id
    if want_default is False and was_default and wh.is_active and not branch_changed \
            and wh.branch_id is not None:
        raise HTTPException(status_code=400, detail=DEFAULT_WH_REQUIRED)
    if was_default and (branch_changed or wh.is_active is False):
        # Boshqa filialga o'tgan / nofaol ombor eski filialning asosiy ombori bo'lib qolmaydi
        wh.is_default = False
        db.flush()
        reassign_default_warehouse(db, old_branch_id, exclude_id=wh.id)
    if want_default is True:
        if wh.branch_id is None:
            raise HTTPException(status_code=400, detail=DEFAULT_WH_NEEDS_BRANCH)
        if wh.is_active is False:
            raise HTTPException(status_code=400, detail="Nofaol omborni asosiy qilib bo'lmaydi")
        set_default_warehouse(db, wh)
    elif branch_changed and wh.branch_id is not None and _is_default_candidate(wh) \
            and not _branch_has_default(db, wh.branch_id, exclude_id=wh.id):
        set_default_warehouse(db, wh)
    log_action_for(
        db, current_user, "WAREHOUSE_UPDATE", "warehouse", wh.id,
        old_values=old_values,
        new_values=_wh_snapshot(wh),
        branch_id=wh.branch_id,
    )
    if branch_changed:
        # T1.9: ombor filiali o'zgarishi alohida audit qilinadi. Eski sotuvlar `sales.branch_id`
        # snapshot'ini saqlagani uchun filial hisobotlaridagi tarix o'zgarmaydi.
        log_action_for(
            db, current_user, "WAREHOUSE_BRANCH_CHANGE", "warehouse", wh.id,
            old_values={"branch_id": old_branch_id},
            new_values={"branch_id": wh.branch_id},
            branch_id=wh.branch_id,
        )
    db.commit()
    db.refresh(wh)
    return wh


@router.delete("/{wh_id}", status_code=204)
def delete_warehouse(
    wh_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    q = db.query(Warehouse).filter(Warehouse.id == wh_id)
    q = q.filter(Warehouse.company_id == current_user.company_id)
    wh = q.first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    old_values = _wh_snapshot(wh)
    if wh.is_active is not False:
        _assert_warehouse_closable(db, wh)   # T1.12: qoldiq/ochiq hujjat bo'lsa 409
    wh.is_active = False
    if wh.is_default:
        # T1.4: o'chirilgan asosiy ombor o'rniga filialning boshqa faol main/shop ombori asosiy bo'ladi
        wh.is_default = False
        db.flush()
        reassign_default_warehouse(db, wh.branch_id, exclude_id=wh.id)
    log_action_for(
        db, current_user, "WAREHOUSE_DELETE", "warehouse", wh.id,
        old_values=old_values,
        new_values={"is_active": False},
        branch_id=wh.branch_id,
    )
    db.commit()
