from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.inventory_count import CountStatus, InventoryCount, InventoryCountItem
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.inventory_count import (
    CountCreate, CountItemUpdate, InventoryCountListOut, InventoryCountOut, CountItemOut
)
from app.services.inventory_count_service import (
    create_inventory_count, finalize_inventory_count,
    start_inventory_count, update_count_items,
)

router = APIRouter(prefix="/inventory-counts", tags=["Inventory Counts"])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


def _load_count(db: Session, count_id: int, company_id: Optional[int] = None) -> Optional[InventoryCount]:
    q = (
        db.query(InventoryCount)
        .options(
            joinedload(InventoryCount.warehouse),
            joinedload(InventoryCount.creator),
            joinedload(InventoryCount.items).joinedload(InventoryCountItem.product),
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
    limit: int = Query(50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    from sqlalchemy import func
    
    q = (
        db.query(
            InventoryCount,
            func.count(InventoryCountItem.id).label("item_count")
        )
        .outerjoin(InventoryCountItem, InventoryCount.id == InventoryCountItem.count_id)
        .options(joinedload(InventoryCount.warehouse))
        .group_by(InventoryCount.id)
        .order_by(InventoryCount.created_at.desc())
    )
    if current_user.role != UserRole.super_admin:
        company_wh_ids = [
            wh.id for wh in db.query(Warehouse.id).filter(Warehouse.company_id == current_user.company_id).all()
        ]
        q = q.filter(InventoryCount.warehouse_id.in_(company_wh_ids))
    if status:
        q = q.filter(InventoryCount.status == status)
    
    counts_with_len = q.offset(skip).limit(limit).all()
    
    return [
        InventoryCountListOut(
            id=c.InventoryCount.id,
            number=c.InventoryCount.number,
            warehouse_name=c.InventoryCount.warehouse.name,
            status=c.InventoryCount.status,
            created_at=c.InventoryCount.created_at,
            item_count=c.item_count,
        )
        for c in counts_with_len
    ]


@router.post("", response_model=InventoryCountListOut)
def create_count(
    data: CountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    count = create_inventory_count(db, data, current_user.id)
    db.commit()
    cid = None if current_user.role == UserRole.super_admin else current_user.company_id
    c = _load_count(db, count.id, cid)
    return InventoryCountListOut(
        id=c.id,
        number=c.number,
        warehouse_name=c.warehouse.name,
        status=c.status,
        created_at=c.created_at,
        item_count=len(c.items),
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
    start_inventory_count(db, count_id)
    db.commit()
    cid = None if current_user.role == UserRole.super_admin else current_user.company_id
    c = _load_count(db, count_id, cid)
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
    update_count_items(db, count_id, items, current_user.id)
    db.commit()
    cid = None if current_user.role == UserRole.super_admin else current_user.company_id
    c = _load_count(db, count_id, cid)
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
    finalize_inventory_count(db, count_id, current_user.id)
    db.commit()
    cid = None if current_user.role == UserRole.super_admin else current_user.company_id
    c = _load_count(db, count_id, cid)
    return InventoryCountListOut(
        id=c.id,
        number=c.number,
        warehouse_name=c.warehouse.name,
        status=c.status,
        created_at=c.created_at,
        item_count=len(c.items),
    )
