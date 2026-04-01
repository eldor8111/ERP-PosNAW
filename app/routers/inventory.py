from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.inventory import StockLevel, StockMovement
from app.models.product import Product
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.inventory import (
    StockAdjustRequest,
    StockLevelOut,
    StockMovementOut,
    StockReceiveRequest,
)
from app.services.inventory_service import adjust_stock, receive_stock

router = APIRouter(prefix="/inventory", tags=["Inventory"])

WAREHOUSE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


@router.get("/stock", response_model=List[StockLevelOut])
def get_stock_levels(
    low_stock_only: bool = Query(False, description="Faqat kam qoldiqlilarni ko'rsatish"),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    q = (
        db.query(StockLevel)
        .join(Product)
        .filter(Product.is_deleted == False)
        .options(joinedload(StockLevel.product))
    )
    q = q.filter(Product.company_id == current_user.company_id)

    if search:
        q = q.filter(
            (Product.name.ilike(f"%{search}%"))
            | (Product.sku.ilike(f"%{search}%"))
            | (Product.barcode.ilike(f"%{search}%"))
        )

    stocks = q.offset(skip).limit(limit).all()

    result = []
    for s in stocks:
        is_low = s.quantity <= s.product.min_stock
        if low_stock_only and not is_low:
            continue
        result.append(
            StockLevelOut(
                product_id=s.product_id,
                product_name=s.product.name,
                product_sku=s.product.sku,
                product_barcode=s.product.barcode,
                quantity=s.quantity,
                min_stock=s.product.min_stock,
                is_low_stock=is_low,
                updated_at=s.updated_at,
            )
        )
    return result


@router.get("/movements", response_model=List[StockMovementOut])
def get_movements(
    product_id: Optional[int] = Query(None),
    type: Optional[str] = Query(None, description="Filter by movement type: in, out, adjust"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    q = (
        db.query(StockMovement)
        .join(Product, Product.id == StockMovement.product_id)
        .options(joinedload(StockMovement.product))
        .order_by(StockMovement.created_at.desc())
    )
    q = q.filter(Product.company_id == current_user.company_id)

    if product_id:
        q = q.filter(StockMovement.product_id == product_id)
    if type:
        q = q.filter(StockMovement.type == type)

    movements = q.offset(skip).limit(limit).all()

    return [
        StockMovementOut(
            id=m.id,
            product_id=m.product_id,
            product_name=m.product.name,
            type=m.type,
            qty_before=m.qty_before,
            qty_after=m.qty_after,
            quantity=m.quantity,
            reference_type=m.reference_type,
            reference_id=m.reference_id,
            reason=m.reason,
            created_at=m.created_at,
        )
        for m in movements
    ]


@router.post("/receive")
def receive_goods(
    data: StockReceiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    movements = []
    for item in data.items:
        m = receive_stock(
            db=db,
            product_id=item.product_id,
            quantity=item.quantity,
            user_id=current_user.id,
            reason=item.reason or data.note,
            reference_type="manual_receive",
        )
        movements.append({"product_id": item.product_id, "qty_added": str(item.quantity), "new_qty": str(m.qty_after)})

    db.commit()
    return {"message": f"{len(movements)} ta mahsulot qabul qilindi", "details": movements}


@router.post("/adjust")
def adjust_stock_level(
    data: StockAdjustRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    m = adjust_stock(
        db=db,
        product_id=data.product_id,
        new_quantity=data.new_quantity,
        user_id=current_user.id,
        reason=data.reason,
    )
    db.commit()
    return {
        "message": "Qoldiq yangilandi",
        "product_id": data.product_id,
        "qty_before": str(m.qty_before),
        "qty_after": str(m.qty_after),
    }


@router.get("/warehouses")
def list_warehouses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wq = db.query(Warehouse).filter(Warehouse.is_active == True)
    wq = wq.filter(Warehouse.company_id == current_user.company_id)
    warehouses = wq.order_by(Warehouse.name).all()
    return [{"id": w.id, "name": w.name, "type": w.type} for w in warehouses]
