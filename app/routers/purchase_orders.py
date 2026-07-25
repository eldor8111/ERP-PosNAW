from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.purchase_order import POItem, POStatus, PurchaseOrder
from app.models.user import User, UserRole
from app.schemas.purchase_order import POCreate, POListOut, POOut, POItemOut, POReceiveRequest, POUpdate  # type: ignore
from app.services.purchase_order_service import create_purchase_order, receive_purchase_order, delete_purchase_order, update_purchase_order  # type: ignore

router = APIRouter(prefix="/purchase-orders", tags=["Purchase Orders"])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.warehouse)


def _build_po_out(po: PurchaseOrder) -> POOut:
    return POOut(
        id=po.id,
        number=po.number,
        supplier_id=po.supplier_id,
        supplier_name=po.supplier.name,
        warehouse_id=po.warehouse_id,
        warehouse_name=po.warehouse.name,
        status=po.status,
        total_amount=po.total_amount,
        paid_amount=po.paid_amount,
        discount_amount=po.discount_amount,
        note=po.note,
        expected_date=po.expected_date,
        created_by=po.created_by,
        creator_name=po.creator.name,
        created_at=po.created_at,
        currency=getattr(po, 'currency', None) or 'UZS',
        items=[
            POItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else "",
                qty_ordered=item.qty_ordered,
                qty_received=item.qty_received,
                unit_cost=item.unit_cost,
                cost_currency=getattr(item, 'cost_currency', None) or 'UZS',
                original_unit_cost=getattr(item, 'original_unit_cost', None) or item.unit_cost,
            )
            for item in po.items
        ],
    )


from datetime import date, datetime, timedelta

@router.get("", response_model=List[POListOut])
def list_purchase_orders(
    status: Optional[POStatus] = Query(None),
    supplier_id: Optional[int] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = (
        db.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.supplier),
            joinedload(PurchaseOrder.warehouse),
            joinedload(PurchaseOrder.items),
        )
        .order_by(PurchaseOrder.created_at.desc())
    )
    q = q.filter(PurchaseOrder.company_id == current_user.company_id)
    if status:
        q = q.filter(PurchaseOrder.status == status)
    if supplier_id:
        q = q.filter(PurchaseOrder.supplier_id == supplier_id)
    if warehouse_id:
        q = q.filter(PurchaseOrder.warehouse_id == warehouse_id)
    if user_id:
        q = q.filter(PurchaseOrder.created_by == user_id)
    if date_from:
        q = q.filter(PurchaseOrder.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(PurchaseOrder.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))

    pos = q.offset(skip).limit(limit).all()
    res = []
    for po in pos:
        # Use stored currency first; fallback to checking items
        c_code = getattr(po, 'currency', None) or 'UZS'
        if c_code == 'UZS':
            for item in po.items:
                item_cur = getattr(item, 'cost_currency', None)
                if item_cur and item_cur != 'UZS':
                    c_code = item_cur
                    break

        # Compute original total from items (in original currency)
        orig_total = None
        orig_paid = None
        if c_code != 'UZS':
            from decimal import Decimal as D
            orig_total = sum(
                (getattr(item, 'original_unit_cost', None) or item.unit_cost) * item.qty_ordered
                for item in po.items
            )
            # Compute original paid amount using exchange rate ratio
            # orig_total / total_amount gives the rate: 1 UZS = X original_currency
            if orig_total and po.total_amount and float(po.total_amount) > 0:
                rate_ratio = float(orig_total) / float(po.total_amount)  # original / UZS
                orig_paid = float(po.paid_amount or 0) * rate_ratio
            else:
                orig_paid = None

        res.append(
            POListOut(
                id=po.id,
                number=po.number,
                supplier_name=po.supplier.name,
                warehouse_name=po.warehouse.name,
                status=po.status,
                total_amount=po.total_amount,
                paid_amount=po.paid_amount,
                discount_amount=po.discount_amount,
                created_at=po.created_at,
                currency=c_code,
                original_total_amount=orig_total,
                original_paid_amount=orig_paid,
            )
        )
    return res


@router.post("", response_model=POOut)
def create_po(
    data: POCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant)),
):
    po = create_purchase_order(db, data, current_user)
    db.commit()
    db.refresh(po)
    return _build_po_out(po)


@router.get("/{po_id}", response_model=POOut)
def get_po(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = (
        db.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.supplier),
            joinedload(PurchaseOrder.warehouse),
            joinedload(PurchaseOrder.creator),
            joinedload(PurchaseOrder.items).joinedload(POItem.product),
        )
        .filter(PurchaseOrder.id == po_id)
    )
    q = q.filter(PurchaseOrder.company_id == current_user.company_id)
    po = q.first()
    if not po:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    return _build_po_out(po)


@router.post("/{po_id}/receive", response_model=POOut)
def receive_po(
    po_id: int,
    data: POReceiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)),
):
    po = receive_purchase_order(db, po_id, data, current_user)
    db.commit()
    db.refresh(po)
    # Reload with joins
    q = (
        db.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.supplier),
            joinedload(PurchaseOrder.warehouse),
            joinedload(PurchaseOrder.creator),
            joinedload(PurchaseOrder.items).joinedload(POItem.product),
        )
        .filter(PurchaseOrder.id == po_id)
    )
    q = q.filter(PurchaseOrder.company_id == current_user.company_id)
    po = q.first()
    return _build_po_out(po)


@router.post("/{po_id}/cancel")
def cancel_po(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    q = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id)
    q = q.filter(PurchaseOrder.company_id == current_user.company_id)
    po = q.first()
    if not po:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if po.status in (POStatus.received, POStatus.cancelled):
        raise HTTPException(status_code=400, detail=f"'{po.status}' holatdagi buyurtmani bekor qilib bo'lmaydi")
    po.status = POStatus.cancelled
    db.commit()
    return {"message": "Buyurtma bekor qilindi", "number": po.number}


@router.delete("/{po_id}")
def delete_po(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """Xarid buyurtmasini o'chirish va mahsulot qoldiqlarini qaytarish"""
    delete_purchase_order(db=db, po_id=po_id, current_user=current_user)
    return {"message": "Buyurtma o'chirildi va qoldiqlar qaytarildi"}


@router.patch("/{po_id}", response_model=POOut)
def edit_po(
    po_id: int,
    data: POUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant)),
):
    """Draft yoki sent statusdagi buyurtmani tahrirlash"""
    po = update_purchase_order(db, po_id, data, current_user)
    db.commit()
    # Joins bilan qayta yuklash
    from sqlalchemy.orm import joinedload as jl
    po = (
        db.query(PurchaseOrder)
        .options(
            jl(PurchaseOrder.supplier),
            jl(PurchaseOrder.warehouse),
            jl(PurchaseOrder.creator),
            jl(PurchaseOrder.items).joinedload(POItem.product),
        )
        .filter(PurchaseOrder.id == po_id)
        .filter(PurchaseOrder.company_id == current_user.company_id)
        .first()
    )
    return _build_po_out(po)
