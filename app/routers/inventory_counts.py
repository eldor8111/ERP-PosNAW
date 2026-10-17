from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.audit import log_action_for
from app.core.dependencies import require_roles
from app.database import get_db
from app.models.inventory_count import CountStatus, InventoryCount, InventoryCountItem
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.inventory_count import (
    CountCreate, CountItemUpdate, InventoryCountListOut, InventoryCountOut, CountItemOut
)
from app.services.inventory_count_service import (
    create_inventory_count, finalize_inventory_count, find_open_count,
    open_count_conflict, revert_inventory_count, start_inventory_count, update_count_items,
)

router = APIRouter(prefix="/inventory-counts", tags=["Inventory Counts"])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


def _write_cid(user: User) -> Optional[int]:
    """Yozuvchi amallar uchun korxona: None faqat super_admin'da; korxonasiz oddiy foydalanuvchiga ruxsat yo'q."""
    if user.role == UserRole.super_admin:
        return None
    if user.company_id is None:
        raise HTTPException(status_code=403, detail="Korxona aniqlanmadi")
    return user.company_id


def _load_count(db: Session, count_id: int, company_id: Optional[int] = None) -> Optional[InventoryCount]:
    q = (
        db.query(InventoryCount)
        .options(
            joinedload(InventoryCount.warehouse),
            joinedload(InventoryCount.creator),
            joinedload(InventoryCount.items).joinedload(InventoryCountItem.product),
            joinedload(InventoryCount.items).joinedload(InventoryCountItem.variant),
        )
        .filter(InventoryCount.id == count_id)
    )
    if company_id is not None:
        company_wh_ids = [
            wh.id for wh in db.query(Warehouse.id).filter(Warehouse.company_id == company_id).all()
        ]
        q = q.filter(InventoryCount.warehouse_id.in_(company_wh_ids))
    return q.first()


def _build_count_out(c: InventoryCount) -> InventoryCountOut:
    return InventoryCountOut(
        id=c.id,
        number=c.number,
        warehouse_id=c.warehouse_id,
        warehouse_name=c.warehouse.name,
        status=c.status,
        note=c.note,
        created_by=c.created_by,
        creator_name=c.creator.name,
        started_at=c.started_at,
        finished_at=c.finished_at,
        created_at=c.created_at,
        items=[
            CountItemOut(
                id=item.id,
                product_id=item.product_id,
                variant_id=item.variant_id,
                variant_name=item.variant.name if item.variant else None,
                product_name=item.product.name,
                product_sku=item.product.sku,
                product_unit=item.product.unit,
                product_category_id=item.product.category_id,
                system_qty=item.system_qty,
                counted_qty=item.counted_qty,
                variance=item.variance,
                variance_reason=item.variance_reason,
            )
            for item in c.items
        ],
    )


@router.get("", response_model=List[InventoryCountListOut])
def list_counts(
    status: Optional[CountStatus] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    from sqlalchemy import func

    q = (
        db.query(
            InventoryCount.id,
            InventoryCount.number,
            InventoryCount.status,
            InventoryCount.created_at,
            Warehouse.name.label("warehouse_name"),
            func.count(InventoryCountItem.id).label("item_count"),
        )
        .outerjoin(InventoryCountItem, InventoryCount.id == InventoryCountItem.count_id)
        .outerjoin(Warehouse, Warehouse.id == InventoryCount.warehouse_id)
        .group_by(InventoryCount.id, InventoryCount.number, InventoryCount.status,
                  InventoryCount.created_at, Warehouse.name)
        .order_by(InventoryCount.created_at.desc())
    )
    if current_user.role != UserRole.super_admin:
        q = q.filter(Warehouse.company_id == current_user.company_id)
    if status:
        q = q.filter(InventoryCount.status == status)

    rows = q.offset(skip).limit(limit).all()

    return [
        InventoryCountListOut(
            id=r.id,
            number=r.number,
            warehouse_name=r.warehouse_name or "",
            status=r.status,
            created_at=r.created_at,
            item_count=r.item_count,
        )
        for r in rows
    ]


@router.post("", response_model=InventoryCountListOut)
def create_count(
    data: CountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    cid = _write_cid(current_user)
    count = create_inventory_count(db, data, current_user.id, cid)
    items_created = getattr(count, "_items_created", 0)
    db.commit()
    # T3.8: faqat ombor kerak — qatorlarni (items) qayta yuklamaymiz, item_count yaratilgan qatorlar soni
    c = (
        db.query(InventoryCount)
        .options(joinedload(InventoryCount.warehouse))
        .filter(InventoryCount.id == count.id)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    return InventoryCountListOut(
        id=c.id,
        number=c.number,
        warehouse_name=c.warehouse.name,
        status=c.status,
        created_at=c.created_at,
        item_count=items_created,
    )


@router.get("/{count_id}", response_model=InventoryCountOut)
def get_count(
    count_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    cid = None if current_user.role == UserRole.super_admin else current_user.company_id
    c = _load_count(db, count_id, cid)
    if not c:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    return _build_count_out(c)


@router.post("/{count_id}/start", response_model=InventoryCountListOut)
def start_count(
    count_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    cid = _write_cid(current_user)
    start_inventory_count(db, count_id, cid)
    db.commit()
    c = _load_count(db, count_id, cid)
    if not c:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    return InventoryCountListOut(
        id=c.id,
        number=c.number,
        warehouse_name=c.warehouse.name,
        status=c.status,
        created_at=c.created_at,
        item_count=len(c.items),
    )


@router.post("/{count_id}/items", response_model=InventoryCountListOut)
def update_items(
    count_id: int,
    items: List[CountItemUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    cid = _write_cid(current_user)
    update_count_items(db, count_id, items, current_user.id, cid)
    db.commit()
    c = _load_count(db, count_id, cid)
    if not c:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    return InventoryCountListOut(
        id=c.id,
        number=c.number,
        warehouse_name=c.warehouse.name,
        status=c.status,
        created_at=c.created_at,
        item_count=len(c.items),
    )


@router.post("/{count_id}/finalize", response_model=InventoryCountListOut)
def finalize_count(
    count_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    cid = _write_cid(current_user)
    finalize_inventory_count(db, count_id, current_user.id, cid)
    db.commit()
    c = _load_count(db, count_id, cid)
    if not c:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    return InventoryCountListOut(
        id=c.id,
        number=c.number,
        warehouse_name=c.warehouse.name,
        status=c.status,
        created_at=c.created_at,
        item_count=len(c.items),
    )


@router.post("/{count_id}/revert", response_model=InventoryCountListOut)
def revert_count(
    count_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    cid = None if current_user.role == UserRole.super_admin else current_user.company_id
    c = _load_count(db, count_id, cid)
    if not c:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")

    if c.status == CountStatus.completed:
        # Qaytarilgach revizya yana ochiq bo'ladi — shu omborda boshqa ochiq revizya bo'lmasligi shart
        other = find_open_count(db, c.warehouse_id, exclude_id=c.id)
        if other:
            raise open_count_conflict(other)

        # T1.19: harakatlar o'chirilmaydi — storno (revision_revert) yoziladi
        revert_inventory_count(db, c, current_user.id)
        db.commit()
    
    return InventoryCountListOut(
        id=c.id,
        number=c.number,
        warehouse_name=c.warehouse.name,
        status=c.status,
        created_at=c.created_at,
        item_count=len(c.items),
    )

@router.delete("/{count_id}")
def delete_count(
    count_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    """Revizyani o'chirish."""
    cid = None if current_user.role == UserRole.super_admin else current_user.company_id
    c = _load_count(db, count_id, cid)
    if not c:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")

    # T1.19: yakunlangan revizyani o'chirib bo'lmaydi (kamomad yashiriladi) — avval qaytarish (revert) kerak
    if c.status == CountStatus.completed:
        raise HTTPException(
            status_code=400,
            detail="Yakunlangan revizyani o'chirib bo'lmaydi, avval bekor qiling (revert)",
        )

    snapshot = {"number": c.number, "warehouse_id": c.warehouse_id, "status": c.status.value
                if hasattr(c.status, "value") else c.status}
    log_action_for(
        db, current_user, "COUNT_DELETE", "inventory_count", count_id,
        old_values=snapshot, branch_id=c.warehouse.branch_id if c.warehouse else None,
        company_id=c.warehouse.company_id if c.warehouse else None,
    )

    # Items ni o'chirish
    db.query(InventoryCountItem).filter(InventoryCountItem.count_id == count_id).delete()

    db.delete(c)
    db.commit()
    return {"status": "deleted", "id": count_id}
