from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.branch_context import (
    BRANCH_FORBIDDEN, BranchContext, apply_warehouse_scope, get_branch_context,
)
from app.core.dependencies import require_roles
from app.core.report_scope import effective_ctx
from app.database import get_db
from app.models.purchase_order import POItem, POStatus, PurchaseOrder
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.purchase_order import POCreate, POListOut, POOut, POItemOut, POReceiveRequest, POUpdate  # type: ignore
from app.services.purchase_order_service import (  # type: ignore
    cancel_purchase_order, create_purchase_order, delete_purchase_order, display_amounts,
    receive_purchase_order, update_purchase_order, is_mixed,
)
from app.services.warehouse_access import resolve_ctx
from app.utils.report_utils import _date_range

# T1.3: joriy filial konteksti (X-Branch-Id) db.info ga yoziladi — servis ichidagi filial tekshiruvi uchun
router = APIRouter(prefix="/purchase-orders", tags=["Purchase Orders"], dependencies=[Depends(get_branch_context)])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.warehouse)


class POListBranchOut(POListOut):
    """Ro'yxat qatori + ombor va filial (UI "Filial" ustuni uchun)."""
    warehouse_id: Optional[int] = None
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    # Aralash valyutali xarid: asosiy valyutadan boshqa valyutalardagi qarz {valyuta: summa}
    debt_extra: Optional[Dict[str, float]] = None
    mixed: bool = False  # qatorlari turli valyutada (so'm + USD)


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
                variant_id=item.variant_id,
                variant_name=item.variant.name if item.variant else None,
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
            joinedload(PurchaseOrder.items).joinedload(POItem.variant),
        )
        .filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id)
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    # T1.16: filialga biriktirilgan xodim boshqa filial omboridagi xaridni ko'ra olmaydi (404)
    ctx = resolve_ctx(db, current_user)
    ids = None if ctx.bypass else ctx.scope_ids()
    if ids is not None:
        wh = po.warehouse
        if wh is None or wh.branch_id not in ids:
            raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    return po


@router.get("", response_model=List[POListBranchOut])
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
    ctx: BranchContext = Depends(get_branch_context),
):
    q = (
        db.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.supplier),
            joinedload(PurchaseOrder.warehouse).joinedload(Warehouse.branch),
            joinedload(PurchaseOrder.items),
        )
        .filter(PurchaseOrder.company_id == current_user.company_id)
        .order_by(PurchaseOrder.created_at.desc())
    )
    if status:
        q = q.filter(PurchaseOrder.status == status)
    if supplier_id:
        q = q.filter(PurchaseOrder.supplier_id == supplier_id)
    # T1.16: filialli xodim boshqa filial (yoki uning ombori) so'ralsa 403
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches huquqi — cheklovsiz
    scope_ids = None if ctx.bypass else ctx.scope_ids()
    if scope_ids is not None:
        if branch_id and branch_id not in scope_ids:
            raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
        if warehouse_id:
            wh_branch = db.query(Warehouse.branch_id).filter(
                Warehouse.id == warehouse_id, Warehouse.company_id == current_user.company_id,
            ).scalar()
            if wh_branch not in scope_ids:
                raise HTTPException(status_code=403, detail="Bu ombor sizning filialingizga tegishli emas")
    if warehouse_id:
        q = q.filter(PurchaseOrder.warehouse_id == warehouse_id)
    # Filial filtri (T1.3): filialga biriktirilgan xodim faqat ruxsat etilgan filial omborlaridagi xaridlarni
    # ko'radi; `branch_id` faqat shu doirada (admin/director — istalgan korxona filiali) ishlaydi
    q = apply_warehouse_scope(q, ctx, PurchaseOrder.warehouse_id, branch_id)
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
            POListBranchOut(
                id=po.id,
                warehouse_id=po.warehouse_id,
                branch_id=po.warehouse.branch_id if po.warehouse else None,
                branch_name=po.warehouse.branch.name if po.warehouse and po.warehouse.branch else None,
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
                debt_extra={c: float(v) for c, v in amounts["debt_extra"].items()} or None,
                mixed=is_mixed(po),
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
