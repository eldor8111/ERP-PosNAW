from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, aliased

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.customer import Customer
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.user import User, UserRole
from app.schemas.sale import SaleCreate, SaleItemOut, SaleListOut, SaleOut, SaleUpdate, SaleReturnRequest, SaleBulkCreate, SaleFiscalUpdate, SalePage
from app.services.sale_service import create_sale, create_return_sale, delete_sale, update_sale, create_pending_sale
from app.services.sale_partial_return import process_partial_return
from app.services.hippo_fiscalize import fiscalize_sale
from app.admin_tg_bot.notifications import trigger_instant_notification

router = APIRouter(prefix="/sales", tags=["Sales (POS)"])

POS_ROLES = (UserRole.admin, UserRole.director, UserRole.cashier, UserRole.manager)


def _load_sale(db: Session, sale_id: int, user: Optional[User] = None) -> Sale:
    q = (
        db.query(Sale)
        .options(
            joinedload(Sale.items).joinedload(SaleItem.product),
            joinedload(Sale.items).joinedload(SaleItem.warehouse),
            joinedload(Sale.payments),
            joinedload(Sale.cashier),
            joinedload(Sale.customer),
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
            sku=i.product.sku if i.product else None,
            quantity=i.quantity,
            unit_price=i.unit_price,
            cost_price=i.cost_price,
            discount=i.discount,
            subtotal=i.subtotal,
            returned_quantity=getattr(i, 'returned_quantity', None) or Decimal("0"),
            unit=getattr(i, 'unit', None) or (i.product.unit if i.product else 'dona') or 'dona',
            warehouse_id=getattr(i, 'warehouse_id', None),
            warehouse_name=(
                i.warehouse.name
                if getattr(i, 'warehouse', None)
                else None
            ),
            currency_code=getattr(i, 'currency_code', 'UZS'),
            exchange_rate=getattr(i, 'exchange_rate', Decimal("1.0")),
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
        id=sale.id,  # type: ignore
        number=sale.number,  # type: ignore
        cashier_id=sale.cashier_id,  # type: ignore
        cashier_name=sale.cashier.name if sale.cashier else f"ID={sale.cashier_id}",
        customer_id=sale.customer_id,  # type: ignore
        customer_name=sale.customer.name if getattr(sale, 'customer', None) else None,
        warehouse_id=sale.warehouse_id,  # type: ignore
        total_amount=sale.total_amount,  # type: ignore
        discount_amount=sale.discount_amount,  # type: ignore
        paid_amount=sale.paid_amount,  # type: ignore
        paid_cash=sale.paid_cash,  # type: ignore
        paid_card=sale.paid_card,  # type: ignore
        paid_cashback=getattr(sale, 'paid_cashback', 0) or 0,
        payment_type=sale.payment_type,
        status=sale.status,
        note=sale.note,  # type: ignore
        items=items,
        payments=payments,
        created_at=sale.created_at,  # type: ignore
        debt_due_date=getattr(sale, 'debt_due_date', None),
        currency_code=sale.currency.code if getattr(sale, 'currency', None) else "UZS",
        exchange_rate=getattr(sale, 'exchange_rate', 1.0) or 1.0,
        debt_amounts=getattr(sale, 'debt_amounts', None),
        before_debt_balances=getattr(sale, 'before_debt_balances', None),
        fiscal_sign=getattr(sale, 'fiscal_sign', None),
        fiscal_qr_url=getattr(sale, 'fiscal_qr_url', None),
        fiscal_receipt_seq=getattr(sale, 'fiscal_receipt_seq', None),
        fiscal_transaction_id=getattr(sale, 'fiscal_transaction_id', None),
        fiscal_at=getattr(sale, 'fiscal_at', None),
    )


def _build_sale_list_out(sale: Sale) -> SaleListOut:
    """Sale ORM obyektidan SaleListOut qurish (idempotent takror javob uchun)."""
    return SaleListOut(
        id=sale.id,  # type: ignore
        number=sale.number,  # type: ignore
        cashier_name=sale.cashier.name if sale.cashier else f"ID={sale.cashier_id}",
        total_amount=sale.total_amount,  # type: ignore
        discount_amount=sale.discount_amount,  # type: ignore
        paid_amount=sale.paid_amount,  # type: ignore
        paid_cash=sale.paid_cash,  # type: ignore
        paid_card=sale.paid_card,  # type: ignore
        paid_cashback=getattr(sale, 'paid_cashback', 0) or 0,
        payment_type=sale.payment_type,
        status=sale.status,
        customer_id=sale.customer_id,  # type: ignore
        customer_name=sale.customer.name if getattr(sale, 'customer', None) else None,
        items_count=len(sale.items),  # type: ignore
        created_at=sale.created_at,  # type: ignore
        currency_code=sale.currency.code if getattr(sale, 'currency', None) else "UZS",
        debt_amounts=getattr(sale, 'debt_amounts', None),
        before_debt_balances=getattr(sale, 'before_debt_balances', None),
    )


@router.get("/debug-log")
def get_debug_log():
    import os
    if os.path.exists("pos_sale_debug.log"):
        with open("pos_sale_debug.log", "r", encoding="utf-8") as f:
            return {"log": f.read()}
    return {"log": "Log fayl topilmadi yoki bo'sh"}


@router.post("/", response_model=SaleListOut)
def make_sale(
        data: SaleCreate,
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """POS — yangi sotuv amalga oshirish"""
    with open("pos_sale_debug.log", "a", encoding="utf-8") as f:
        f.write(f"\\n--- NEW SALE FROM POS (user {current_user.name}) ---\\n")
        f.write(data.model_dump_json(indent=2) + "\\n")

    ip = request.client.host if request.client else None

    # Takroriy sotuvdan himoya: POS Idempotency-Key: <uuid> yuboradi
    # (oflayn navbatdan qayta yuborilganda ham xuddi shu kalit). Shu kalit
    # bilan sotuv allaqachon yaratilgan bo'lsa — yangisini yaratmasdan
    # mavjudini qaytaramiz.
    idem_key = (request.headers.get("Idempotency-Key") or "").strip() or None
    if idem_key and len(idem_key) > 64:
        raise HTTPException(status_code=400, detail="Idempotency-Key 64 belgidan oshmasligi kerak")
    if idem_key:
        existing = db.query(Sale).filter(
            Sale.idempotency_key == idem_key,
            Sale.company_id == current_user.company_id,
        ).first()
        if existing:
            return _build_sale_list_out(existing)

    try:
        sale = create_sale(db=db, data=data, current_user=current_user, ip=ip, background_tasks=background_tasks, idempotency_key=idem_key)
    except IntegrityError:
        # Poyga holati: xuddi shu Idempotency-Key bilan parallel so'rov
        # allaqachon sotuv yaratib ulgurgan — mavjudini qaytaramiz.
        db.rollback()
        if idem_key:
            dup = db.query(Sale).filter(
                Sale.idempotency_key == idem_key,
                Sale.company_id == current_user.company_id,
            ).first()
            if dup:
                return _build_sale_list_out(dup)
        raise
    cust_name = sale.customer.name if getattr(sale, 'customer', None) else (db.query(Customer.name).filter(Customer.id == sale.customer_id).scalar() if sale.customer_id else None)

    # ── Hippo fiskalizatsiya (background) ────────────────────────────────────
    # Kassir X-Hippo-Factory-Id headerini yuborsa — chek fiskallashtiriladi.
    # Header bo'lmasa — xato ko'tarilmaydi, sotuv normal saqlanadi.
    _factory_id = request.headers.get("X-Hippo-Factory-Id", "").strip()
    if _factory_id:
        background_tasks.add_task(fiscalize_sale, db, sale.id, _factory_id)  # type: ignore[arg-type]
    # ─────────────────────────────────────────────────────────────────────────

    # ── Telegram bildirishnoma ──
    try:
        msg = f"🛒 <b>Yangi Sotuv!</b>\n🧾 Chek: #{sale.number}\n👤 Kassir: {current_user.name}\n"
        if cust_name:
            msg += f"🤝 Mijoz: {cust_name}\n"
        msg += f"💰 Summa: {float(sale.total_amount):,.0f} UZS"
        trigger_instant_notification(current_user.company_id, msg, "sale")
    except Exception as e:
        print(f"Telegram notification error: {e}")

    return SaleListOut(
        id=sale.id,  # type: ignore
        number=sale.number,  # type: ignore
        cashier_name=current_user.name,  # type: ignore
        total_amount=sale.total_amount,  # type: ignore
        discount_amount=sale.discount_amount,  # type: ignore
        paid_amount=sale.paid_amount,  # type: ignore
        paid_cash=sale.paid_cash,  # type: ignore
        paid_card=sale.paid_card,  # type: ignore
        paid_cashback=getattr(sale, 'paid_cashback', 0) or 0,
        payment_type=sale.payment_type,
        status=sale.status,
        customer_id=sale.customer_id,  # type: ignore
        customer_name=cust_name,
        items_count=len(data.items),
        created_at=sale.created_at,  # type: ignore
        currency_code=sale.currency.code if getattr(sale, 'currency', None) else "UZS",
        debt_amounts=getattr(sale, 'debt_amounts', None),
        before_debt_balances=getattr(sale, 'before_debt_balances', None),
    )



@router.post("/bulk")
def make_bulk_sales(
        data: SaleBulkCreate,
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """POS — Oflayn rejimdagi to'plangan sotuvlarni bir vaqtda jo'natish"""
    ip = request.client.host if request.client else None
    successful = []
    errors = []

    for idx, sale_data in enumerate(data.sales):
        try:
            # Har bir sotuvni yangi savepoint ichida yaratamiz (birortasi xato qilsa hammasi to'xtamasligi uchun)
            with db.begin_nested():
                sale = create_sale(db=db, data=sale_data, current_user=current_user, ip=ip, background_tasks=background_tasks)
                
                cust_name = sale.customer.name if getattr(sale, 'customer', None) else (db.query(Customer.name).filter(Customer.id == sale.customer_id).scalar() if sale.customer_id else None)
                
                successful.append(SaleListOut(
                    id=sale.id,  # type: ignore
                    number=sale.number,  # type: ignore
                    cashier_name=current_user.name,  # type: ignore
                    total_amount=sale.total_amount,  # type: ignore
                    discount_amount=sale.discount_amount,  # type: ignore
                    paid_amount=sale.paid_amount,  # type: ignore
                    paid_cash=sale.paid_cash,  # type: ignore
                    paid_card=sale.paid_card,  # type: ignore
                    paid_cashback=getattr(sale, 'paid_cashback', 0) or 0,
                    payment_type=sale.payment_type,
                    status=sale.status,
                    customer_id=sale.customer_id,  # type: ignore
                    customer_name=cust_name,
                    items_count=len(sale_data.items),
                    created_at=sale.created_at,  # type: ignore
                    currency_code=sale.currency.code if getattr(sale, 'currency', None) else "UZS",
                    debt_amounts=getattr(sale, 'debt_amounts', None),
                    before_debt_balances=getattr(sale, 'before_debt_balances', None),
                ))
        except Exception as e:
            # Qaysi sotuvda xato bo'lganini bilish uchun
            local_id = getattr(sale_data, 'local_id', str(idx))
            errors.append({"local_id": local_id, "error": str(e)})

    # Barchasini saqlash
    db.commit()

    return {
        "success_count": len(successful),
        "error_count": len(errors),
        "successful": successful,
        "errors": errors
    }


@router.post("/pending", response_model=SaleListOut)
def make_pending_sale(
        data: SaleCreate,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """Ulgurji sotuv — to'lovsiz (pending) holatda saqlash. Stock tegilmaydi."""
    ip = request.client.host if request.client else None
    sale = create_pending_sale(db=db, data=data, current_user=current_user, ip=ip)
    cust_name = sale.customer.name if getattr(sale, 'customer', None) else (db.query(Customer.name).filter(Customer.id == sale.customer_id).scalar() if sale.customer_id else None)
    return SaleListOut(
        id=sale.id,  # type: ignore
        number=sale.number,  # type: ignore
        cashier_name=current_user.name,  # type: ignore
        total_amount=sale.total_amount,  # type: ignore
        discount_amount=sale.discount_amount,  # type: ignore
        paid_amount=sale.paid_amount,  # type: ignore
        paid_cash=sale.paid_cash,  # type: ignore
        paid_card=sale.paid_card,  # type: ignore
        payment_type=sale.payment_type,
        status=sale.status,
        customer_id=sale.customer_id,  # type: ignore
        customer_name=cust_name,
        items_count=len(data.items),
        created_at=sale.created_at,  # type: ignore
        currency_code=sale.currency.code if getattr(sale, 'currency', None) else "UZS",
        debt_amounts=getattr(sale, 'debt_amounts', None),
        before_debt_balances=getattr(sale, 'before_debt_balances', None),
    )


@router.post("/{sale_id}/return-items", response_model=SaleOut)
def partial_return(
    sale_id: int,
    data: SaleReturnRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*POS_ROLES)),
):
    ip = request.client.host if request.client else None
    updated_sale = process_partial_return(
        db=db,
        sale_id=sale_id,
        data=data,
        current_user=current_user,
        ip=ip
    )
    return _build_sale_out(updated_sale)



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
    cust_name = sale.customer.name if getattr(sale, 'customer', None) else (db.query(Customer.name).filter(Customer.id == sale.customer_id).scalar() if sale.customer_id else None)
    return SaleListOut(
        id=sale.id,  # type: ignore
        number=sale.number,  # type: ignore
        cashier_name=current_user.name,  # type: ignore
        total_amount=sale.total_amount,  # type: ignore
        discount_amount=sale.discount_amount,  # type: ignore
        paid_amount=sale.paid_amount,  # type: ignore
        paid_cash=sale.paid_cash,  # type: ignore
        paid_card=sale.paid_card,  # type: ignore
        payment_type=sale.payment_type,
        status=sale.status,
        customer_id=sale.customer_id,  # type: ignore
        customer_name=cust_name,
        items_count=len(data.items),
        created_at=sale.created_at,  # type: ignore
        currency_code=sale.currency.code if getattr(sale, 'currency', None) else "UZS",
        debt_amounts=getattr(sale, 'debt_amounts', None),
        before_debt_balances=getattr(sale, 'before_debt_balances', None),
    )


@router.get("/", response_model=Union[List[SaleListOut], SalePage])
def list_sales(
        response: Response,
        cashier_id: Optional[int] = Query(None),
        branch_id: Optional[int] = Query(None),
        customer_id: Optional[int] = Query(None),
        date_from: Optional[date] = Query(None),
        date_to: Optional   [date] = Query(None),
        date_today: Optional[bool] = Query(None, description="Faqat bugungi sotuvlar"),
        status: Optional[SaleStatus] = Query(None),
        search: Optional[str] = Query(None, description="Sotuv raqami yoki mijoz nomi bo'yicha qidiruv"),
        with_total: bool = Query(False, description="true bo'lsa {items, total} shaklida qaytaradi"),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*POS_ROLES, UserRole.accountant)),
):
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
        .options(joinedload(Sale.cashier), joinedload(Sale.customer), joinedload(Sale.currency))
    )
    q = q.filter(Sale.company_id == current_user.company_id)

    # Branch isolation: admin/director hammani ko'radi, qolganlari faqat o'z filialini
    ADMIN_ROLES_S = (UserRole.admin, UserRole.director)
    if current_user.role not in ADMIN_ROLES_S:
        if not current_user.branch_id:
            # Filialsiz non-admin foydalanuvchi hech qanday sotuvni ko'ra olmaydi
            return {"items": [], "total": 0} if with_total else []
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
    else:
        # Default: vazvratlarni (refunded) ro'yxatdan chiqarib tashlash
        q = q.filter(Sale.status != SaleStatus.refunded)
    if search:
        CustomerQ = aliased(Customer, name='customer_q')
        q = q.outerjoin(CustomerQ, Sale.customer_id == CustomerQ.id)
        q = q.filter(
            or_(
                Sale.number.ilike(f"%{search}%"),
                CustomerQ.name.ilike(f"%{search}%"),
            )
        )
    total = q.count()
    response.headers["X-Total-Count"] = str(total)
    rows = q.order_by(Sale.created_at.desc()).offset(skip).limit(limit).all()

    items = [
        SaleListOut(
            id=s.id,
            number=s.number,
            cashier_name=s.cashier.name if s.cashier else f"ID={s.cashier_id}",
            total_amount=s.total_amount,
            discount_amount=s.discount_amount,
            paid_amount=s.paid_amount,
            paid_cash=s.paid_cash,
            paid_card=s.paid_card,
            paid_cashback=getattr(s, 'paid_cashback', 0) or 0,
            payment_type=s.payment_type,
            status=s.status,
            customer_id=s.customer_id,
            customer_name=s.customer.name if s.customer else None,
            items_count=cnt,
            created_at=s.created_at,
            currency_code=s.currency.code if getattr(s, 'currency', None) else "UZS",
            debt_amounts=getattr(s, 'debt_amounts', None),
        )
        for s, cnt in rows
    ]
    if with_total:
        return {"items": items, "total": total}
    return items


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


@router.patch("/{sale_id}/fiscal", response_model=SaleOut)
def update_sale_fiscal(
        sale_id: int,
        data: SaleFiscalUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """POS fiskalizatsiya natijasini (fiskal belgi, QR va h.k.) sotuvga yozadi.

    FAQAT fiskal maydonlarni yangilaydi — sotuvning boshqa maydonlariga
    tegmaydi (summalar, qoldiq, qarz va h.k. o'zgarmaydi).
    """
    sale = _load_sale(db, sale_id, current_user)
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")

    # None qiymatlar mavjud fiskal yozuvni O'CHIRib yubormasin
    update_data = data.model_dump(exclude_unset=True, exclude_none=True)

    # Mavjud fiskal belgini BOSHQA qiymat bilan almashtirish faqat
    # admin/direktorga — oddiy kassir fiskal yozuvni qayta yoza olmaydi
    # (xuddi shu qiymat bilan takror PATCH esa idempotent, ruxsat etiladi).
    new_sign = update_data.get("fiscal_sign")
    if (
        sale.fiscal_sign
        and new_sign
        and str(new_sign) != str(sale.fiscal_sign)
        and current_user.role not in (UserRole.admin, UserRole.director, UserRole.super_admin)
    ):
        raise HTTPException(
            status_code=409,
            detail="Sotuvda fiskal belgi allaqachon mavjud — uni faqat admin/direktor almashtira oladi",
        )

    ALLOWED = {"fiscal_sign", "fiscal_qr_url", "fiscal_receipt_seq", "fiscal_transaction_id", "fiscal_at"}
    old_values = {k: getattr(sale, k, None) for k in ALLOWED}
    for k, v in update_data.items():
        if k in ALLOWED:
            setattr(sale, k, v)

    from app.core.audit import log_action
    log_action(
        db, "SALE_FISCAL_UPDATE", "sale", sale.id, current_user.id,
        {"old": {k: str(v) for k, v in old_values.items() if v is not None},
         "new": {k: str(v) for k, v in update_data.items()}},
    )
    db.commit()
    db.refresh(sale)
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
    sale = _load_sale(db, sale.id, current_user)  # type: ignore
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


