from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, select

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.user import User, UserRole
from app.schemas.sale import SaleCreate, SaleItemOut, SaleListOut, SaleOut, SaleUpdate
from app.services.sale_service import create_sale, create_return_sale, delete_sale, update_sale

router = APIRouter(prefix="/sales", tags=["Sales (POS)"])

POS_ROLES = (UserRole.admin, UserRole.director, UserRole.cashier, UserRole.manager)


def _load_sale(db: Session, sale_id: int, user: Optional[User] = None) -> Sale:
    q = (
        db.query(Sale)
        .options(
            joinedload(Sale.items).joinedload(SaleItem.product),
            joinedload(Sale.payments),
            joinedload(Sale.cashier),
        )
        .filter(Sale.id == sale_id)
    )
    if user and user.role != UserRole.super_admin:
        q = q.filter(Sale.company_id == user.company_id)
    return q.first()


def _build_sale_out(sale: Sale) -> SaleOut:
    items = [
        SaleItemOut(
            id=i.id,
            product_id=i.product_id,
            product_name=i.product.name if i.product else f"ID={i.product_id}",
            quantity=i.quantity,
            unit_price=i.unit_price,
            cost_price=i.cost_price,
            discount=i.discount,
            subtotal=i.subtotal,
        )
        for i in sale.items
    ]
    from app.schemas.sale import SalePaymentOut
    payments = [
        SalePaymentOut(
            id=p.id,
            payment_type=p.payment_type,
            amount=p.amount
        )
        for p in sale.payments
    ] if hasattr(sale, 'payments') else []

    return SaleOut(
        id=sale.id,
        number=sale.number,
        cashier_id=sale.cashier_id,
        cashier_name=sale.cashier.name if sale.cashier else f"ID={sale.cashier_id}",
        total_amount=sale.total_amount,
        discount_amount=sale.discount_amount,
        paid_amount=sale.paid_amount,
        paid_cash=sale.paid_cash,
        paid_card=sale.paid_card,
        payment_type=sale.payment_type,
        status=sale.status,
        note=sale.note,
        items=items,
        payments=payments,
        created_at=sale.created_at,
    )


@router.post("/", response_model=SaleListOut)
def make_sale(
    data: SaleCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """POS — yangi sotuv amalga oshirish"""
    ip = request.client.host if request.client else None
    sale = create_sale(db=db, data=data, current_user=current_user, ip=ip, background_tasks=background_tasks)
    # _load_sale chaqirilmaydi — ortiqcha query yo'q, tezroq ishlaydi
    return SaleListOut(
        id=sale.id,
        number=sale.number,
        cashier_name=current_user.name,
        total_amount=sale.total_amount,
        discount_amount=sale.discount_amount,
        paid_amount=sale.paid_amount,
        paid_cash=sale.paid_cash,
        paid_card=sale.paid_card,
        payment_type=sale.payment_type,
        status=sale.status,
        customer_id=sale.customer_id,
        customer_name=None,
        items_count=len(data.items),
        created_at=sale.created_at,
    )


@router.post("/return", response_model=SaleListOut)
def make_return_sale(
    data: SaleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """POS — qaytarish (vazvrat) amalga oshirish"""
    ip = request.client.host if request.client else None
    sale = create_return_sale(db=db, data=data, current_user=current_user, ip=ip)
    return SaleListOut(
        id=sale.id,
        number=sale.number,
        cashier_name=current_user.name,
        total_amount=sale.total_amount,
        discount_amount=sale.discount_amount,
        paid_amount=sale.paid_amount,
        paid_cash=sale.paid_cash,
        paid_card=sale.paid_card,
        payment_type=sale.payment_type,
        status=sale.status,
        customer_id=sale.customer_id,
        customer_name=None,
        items_count=len(data.items),
        created_at=sale.created_at,
    )


@router.get("/", response_model=List[SaleListOut])
def list_sales(
    cashier_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    customer_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    date_today: Optional[bool] = Query(None, description="Faqat bugungi sotuvlar"),
    status: Optional[SaleStatus] = Query(None),
    search: Optional[str] = Query(None, description="Sotuv raqami yoki kassir nomi bo'yicha qidiruv"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*POS_ROLES, UserRole.accountant)),
):
    from app.models.user import User as UserModel
    from app.models.warehouse import Warehouse
    from sqlalchemy import func, select
    # items_count subquery — one SQL COUNT per sale, no joinedloading all items
    items_count_sq = (
        select(SaleItem.sale_id, func.count(SaleItem.id).label("cnt"))
        .group_by(SaleItem.sale_id)
        .subquery()
    )
    q = (
        db.query(Sale, func.coalesce(items_count_sq.c.cnt, 0).label("items_count"))
        .outerjoin(items_count_sq, items_count_sq.c.sale_id == Sale.id)
        .options(joinedload(Sale.cashier), joinedload(Sale.customer))
    )
    q = q.filter(Sale.company_id == current_user.company_id)

    # Branch isolation: admin/director hammani ko'radi, qolganlari faqat o'z filialini
    ADMIN_ROLES_S = (UserRole.admin, UserRole.director)
    if current_user.role not in ADMIN_ROLES_S:
        if not current_user.branch_id:
            # Filialsiz non-admin foydalanuvchi hech qanday sotuvni ko'ra olmaydi
            return []
        branch_wh_ids = [
            wh.id for wh in db.query(Warehouse.id).filter(
                Warehouse.branch_id == current_user.branch_id
            ).all()
        ]
        q = q.filter(Sale.warehouse_id.in_(branch_wh_ids))
    elif branch_id:
        branch_wh_ids = [
            wh.id for wh in db.query(Warehouse.id).filter(
                Warehouse.branch_id == branch_id
            ).all()
        ]
        q = q.filter(Sale.warehouse_id.in_(branch_wh_ids))

    if cashier_id:
        q = q.filter(Sale.cashier_id == cashier_id)
    if customer_id:
        q = q.filter(Sale.customer_id == customer_id)
    if date_today:
        today = date.today()
        q = q.filter(Sale.created_at >= datetime.combine(today, datetime.min.time()))
    if date_from:
        q = q.filter(Sale.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(Sale.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    if status:
        q = q.filter(Sale.status == status)
    if search:
        q = q.filter(Sale.number.ilike(f"%{search}%"))

    rows = q.order_by(Sale.created_at.desc()).offset(skip).limit(limit).all()

    return [
        SaleListOut(
            id=s.id,
            number=s.number,
            cashier_name=s.cashier.name if s.cashier else f"ID={s.cashier_id}",
            total_amount=s.total_amount,
            discount_amount=s.discount_amount,
            paid_amount=s.paid_amount,
            paid_cash=s.paid_cash,
            paid_card=s.paid_card,
            payment_type=s.payment_type,
            status=s.status,
            customer_id=s.customer_id,
            customer_name=s.customer.name if s.customer else None,
            items_count=cnt,
            created_at=s.created_at,
        )
        for s, cnt in rows
    ]


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = _load_sale(db, sale_id, current_user)
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")
    return _build_sale_out(sale)


@router.get("/{sale_id}/receipt")
def get_receipt(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chek ma'lumotlarini olish"""
    sale = _load_sale(db, sale_id, current_user)
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")

    return {
        "receipt_number": sale.number,
        "date": sale.created_at.strftime("%d.%m.%Y %H:%M"),
        "cashier": sale.cashier.name if sale.cashier else "",
        "items": [
            {
                "name": i.product.name if i.product else f"ID={i.product_id}",
                "qty": str(i.quantity),
                "unit_price": str(i.unit_price),
                "discount": str(i.discount),
                "subtotal": str(i.subtotal),
            }
            for i in sale.items
        ],
        "total": str(sale.total_amount),
        "discount": str(sale.discount_amount),
        "paid": str(sale.paid_amount),
        "change": str(max(sale.paid_amount - sale.total_amount, 0)),
        "payment_type": sale.payment_type.value,
    }


@router.put("/{sale_id}", response_model=SaleOut)
def edit_sale(
    sale_id: int,
    data: SaleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """Sotuvni tahrirlash: holat, izoh, to'lov miqdori"""
    sale = update_sale(db=db, sale_id=sale_id, data=data, current_user=current_user)
    sale = _load_sale(db, sale.id, current_user)
    return _build_sale_out(sale)


@router.delete("/{sale_id}")
def remove_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    """Sotuvni o'chirish va mahsulot qoldiqlarini qaytarish"""
    delete_sale(db=db, sale_id=sale_id, current_user=current_user)
    return {"message": "Sotuv o'chirildi va qoldiqlar qaytarildi"}


from pydantic import BaseModel as _BaseModel  # noqa: E402
from app.models.inventory import StockLevel  # noqa: E402


class RefundItemIn(_BaseModel):
    product_id: int
    quantity: float


class RefundIn(_BaseModel):
    items: List[RefundItemIn]
    reason: Optional[str] = "Qaytarish"


@router.post("/{sale_id}/refund")
def refund_sale(
    sale_id: int,
    data: RefundIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """Sotuvdan mahsulotlarni qaytarish va ombor qoldiqlarini tiklash"""
    sale = _load_sale(db, sale_id, current_user)
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")

    refunded = []
    for ri in data.items:
        stock = db.query(StockLevel).filter(
            StockLevel.product_id == ri.product_id,
            StockLevel.warehouse_id == sale.warehouse_id
        ).first()
        qty = Decimal(str(ri.quantity))
        if stock:
            stock.quantity += qty
        else:
            db.add(StockLevel(product_id=ri.product_id, quantity=qty, warehouse_id=sale.warehouse_id))
        refunded.append({"product_id": ri.product_id, "qty_returned": ri.quantity})

    if data.items:
        sale.status = SaleStatus.refunded if hasattr(SaleStatus, 'refunded') else sale.status

    db.commit()
    return {"message": f"{len(refunded)} ta mahsulot qaytarildi", "details": refunded}
