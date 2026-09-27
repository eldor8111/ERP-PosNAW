from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.purchase_order import POItem, POStatus, PurchaseOrder
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.purchase_order import POCreate, POListOut, POOut, POItemOut, POReceiveRequest, POUpdate  # type: ignore
from app.services.purchase_order_service import (  # type: ignore
    cancel_purchase_order, create_purchase_order, delete_purchase_order, display_amounts,
    receive_purchase_order, update_purchase_order,
)
from app.utils.report_utils import _date_range

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
        creator_name=po.creator.name if po.creator else "",
        created_at=po.created_at,
        currency=po.currency or 'UZS',
        exchange_rate=po.exchange_rate,
        items=[
            POItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else "",
                qty_ordered=item.qty_ordered,
                qty_received=item.qty_received,
                unit_cost=item.unit_cost,
                cost_currency=item.cost_currency or 'UZS',
                original_unit_cost=item.original_unit_cost if item.original_unit_cost is not None else item.unit_cost,
                expiry_date=item.expiry_date,
                new_sale_price=item.new_sale_price,
                new_wholesale_price=item.new_wholesale_price,
            )
            for item in po.items
        ],
    )


def _load_po(db: Session, po_id: int, current_user: User) -> PurchaseOrder:
    po = (
        db.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.supplier),
            joinedload(PurchaseOrder.warehouse),
            joinedload(PurchaseOrder.creator),
            joinedload(PurchaseOrder.items).joinedload(POItem.product),
        )
        .filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id)
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    return po


@router.get("", response_model=List[POListOut])
def list_purchase_orders(
    status: Optional[POStatus] = Query(None),
    supplier_id: Optional[int] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
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
        .filter(PurchaseOrder.company_id == current_user.company_id)
        .order_by(PurchaseOrder.created_at.desc())
    )
    if status:
        q = q.filter(PurchaseOrder.status == status)
    if supplier_id:
        q = q.filter(PurchaseOrder.supplier_id == supplier_id)
    if warehouse_id:
        q = q.filter(PurchaseOrder.warehouse_id == warehouse_id)
    if branch_id:
        # Filial filtri avval e'tiborsiz qolardi — filial omborlari bo'yicha
        wh_ids = db.query(Warehouse.id).filter(
            Warehouse.company_id == current_user.company_id, Warehouse.branch_id == branch_id,
        )
        q = q.filter(PurchaseOrder.warehouse_id.in_(wh_ids))
    if user_id:
        q = q.filter(PurchaseOrder.created_by == user_id)
    if date_from or date_to:
        start, end = _date_range(date_from, date_to)  # Toshkent kuni chegaralari
        q = q.filter(PurchaseOrder.created_at >= start, PurchaseOrder.created_at < end)

    res = []
    for po in q.offset(skip).limit(limit).all():
        amounts = display_amounts(db, po)
        foreign = amounts["currency"] != "UZS"
        res.append(
            POListOut(
                id=po.id,
                number=po.number,
                supplier_name=po.supplier.name if po.supplier else "",
                warehouse_name=po.warehouse.name if po.warehouse else "",
                status=po.status,
                total_amount=po.total_amount,
                paid_amount=po.paid_amount,
                discount_amount=po.discount_amount,
                created_at=po.created_at,
                currency=amounts["currency"],
                # Valyutali xarid: xarid kursidagi summalar (chegirmadan keyin)
                original_total_amount=amounts["total_cur"] if foreign else None,
                original_paid_amount=amounts["paid_cur"] if foreign else None,
                # Shu xarid bo'yicha hozirgi qarz (xarid valyutasida; manfiy — ortiqcha to'lov)
                debt_amount=amounts["debt_cur"],
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
    return _build_po_out(_load_po(db, po.id, current_user))


@router.get("/{po_id}", response_model=POOut)
def get_po(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    return _build_po_out(_load_po(db, po_id, current_user))


@router.post("/{po_id}/receive", response_model=POOut)
def receive_po(
    po_id: int,
    data: POReceiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)),
):
    receive_purchase_order(db, po_id, data, current_user)
    db.commit()
    return _build_po_out(_load_po(db, po_id, current_user))


@router.post("/{po_id}/cancel")
def cancel_po(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    po = cancel_purchase_order(db, po_id, current_user)
    db.commit()
    return {"message": "Buyurtma bekor qilindi", "number": po.number}


@router.delete("/{po_id}")
def delete_po(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """Xarid buyurtmasini o'chirish: qoldiq, kassa va ta'minotchi qarzi qaytariladi"""
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
    update_purchase_order(db, po_id, data, current_user)
    db.commit()
    return _build_po_out(_load_po(db, po_id, current_user))
