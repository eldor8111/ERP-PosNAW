import logging
from types import SimpleNamespace
from datetime import date
from decimal import Decimal
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, aliased, object_session

from app.core.branch_context import BranchContext, apply_branch_scope, get_branch_context
from app.core.dependencies import get_current_user, require_roles
from app.config import settings
from app.database import get_db
from app.models.company import Company
from app.models.customer import Customer
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.sale import SaleCreate, SaleItemOut, SaleListOut, SaleOut, SaleUpdate, SaleReturnRequest, SaleBulkCreate, SaleFiscalUpdate, SalePage, SaleAssignCustomer, SalePrescriptionOut
from app.models.prescription import SalePrescription  # D2.5
from app.services.sale_service import create_sale, create_return_sale, delete_sale, update_sale, create_pending_sale, reassign_sale_customer
from app.services.sale_partial_return import process_partial_return
from app.services.sale_helpers import apply_sale_branch_filter
from app.services.hippo_fiscalize import fiscalize_sale
from app.routers.fiscal_devices import company_has_active_devices, device_allowed_for_branch
from app.routers.payment_terminals import attach_payment_references, validate_sale_payment_terminals
from app.admin_tg_bot.notifications import notify_new_sale
from app.utils.telegram_text import esc

router = APIRouter(prefix="/sales", tags=["Sales (POS)"])

POS_ROLES = (UserRole.admin, UserRole.director, UserRole.cashier, UserRole.manager)
# Sotuv detali/cheki/ro'yxatini ko'ra oladigan rollar (mobil rollar — courier/agent/marketplace_agent — chiqarilgan)
SALE_VIEW_ROLES = (
    UserRole.admin, UserRole.director, UserRole.manager,
    UserRole.accountant, UserRole.cashier, UserRole.warehouse,
)


def _load_sale(db: Session, sale_id: int, user: Optional[User] = None) -> Sale:
    q = (
        db.query(Sale)
        .options(
            joinedload(Sale.items).joinedload(SaleItem.product),
            joinedload(Sale.items).joinedload(SaleItem.warehouse),
            joinedload(Sale.payments),
            joinedload(Sale.cashier),
            joinedload(Sale.customer),
            joinedload(Sale.branch),
            joinedload(Sale.warehouse).joinedload(Warehouse.branch),  # T3.7: chek rekvizitlari
        )
        .filter(Sale.id == sale_id)
    )
    if user and user.role != UserRole.super_admin:
        q = q.filter(Sale.company_id == user.company_id)
        # Filial ruxsati (admin/director/super_admin cheklanmaydi)
        q = apply_sale_branch_filter(q, db, user)
    return q.first()


def _sale_branch(sale: Sale):
    """Sotuv filiali: `sale.branch_id` snapshoti (T1.9), bo'lmasa ombor filiali (eski sotuvlar)."""
    if sale.branch is not None:
        return sale.branch
    wh = sale.warehouse
    return wh.branch if wh is not None else None


def _presale_branch_id(db: Session, user: User, ctx: BranchContext, data) -> Optional[int]:
    """Sotuv yaratilishidan oldin filialni taxminan aniqlaydi (T3.18, terminal tekshiruvi uchun):
    ombor filiali -> joriy filial konteksti. Aniqlanmasa None (terminal tekshiruvi butun korxona terminallari bilan)."""
    if getattr(data, "warehouse_id", None):
        bid = db.query(Warehouse.branch_id).filter(
            Warehouse.id == data.warehouse_id, Warehouse.company_id == user.company_id,
        ).scalar()
        if bid:
            return bid
    return ctx.branch_id


def _sale_receipt_meta(sale: Sale) -> dict:
    """Chek rekvizitlari (T3.7): filial nomi/manzili/telefoni, ombor va korxona nomi. Aniqlanmasa — None."""
    br = _sale_branch(sale)
    db = object_session(sale)
    company_name = None
    if db is not None and sale.company_id is not None:
        company_name = db.query(Company.name).filter(Company.id == sale.company_id).scalar()
    return {
        "branch_name": br.name if br else None,
        "branch_address": br.address if br else None,
        "branch_phone": br.phone if br else None,
        # T4.2: filial yuridik nomi va STIR (chek sarlavhasi; bo'sh bo'lsa frontend korxona shablonini ishlatadi)
        "branch_legal_name": br.legal_name if br else None,
        "branch_stir": br.stir if br else None,
        "warehouse_name": sale.warehouse.name if sale.warehouse else None,
        "company_name": company_name,
    }


def _delivery_dict(d) -> Optional[dict]:
    if d is None:
        return None
    return {
        "status": d.status.value,
        "address": d.address,
        "lat": float(d.lat) if d.lat is not None else None,
        "lng": float(d.lng) if d.lng is not None else None,
        "contact_phone": d.contact_phone,
        "delivery_fee": float(d.delivery_fee or 0),
        "planned_date": d.planned_date.isoformat() if d.planned_date else None,
        "note": d.note,
        "courier_name": d.courier.name if d.courier else None,
    }


def _pharma_item_details(sale: Sale):
    """CD.1: dorixona rejimida qatorlar bo'yicha partiyalar va sotuv birligi — ikkita IN so'rov (N+1 yo'q).
    Oddiy korxonada ({}, {}) qaytadi va qo'shimcha so'rov faqat modul tekshiruvi (bitta) bo'ladi."""
    db = object_session(sale)
    ids = [i.id for i in sale.items]
    if db is None or not ids:
        return {}, {}
    from app.services.pharmacy import pharmacy_enabled
    if not pharmacy_enabled(db, sale.company_id):
        return {}, {}
    from app.models.batch import Batch
    from app.models.product_units import SaleItemUnit
    from app.models.sale import SaleItemBatch
    from app.schemas.sale import SaleItemBatchOut, SaleItemUnitOut
    batches: dict = {}
    for sib, b in (
        db.query(SaleItemBatch, Batch).join(Batch, Batch.id == SaleItemBatch.batch_id)
        .filter(SaleItemBatch.sale_item_id.in_(ids)).order_by(SaleItemBatch.id).all()
    ):
        exp = b.expiry_date
        batches.setdefault(sib.sale_item_id, []).append(SaleItemBatchOut(
            batch_id=b.id, lot_number=b.lot_number,
            expiry_date=exp.date() if hasattr(exp, "date") else exp, quantity=sib.quantity,
        ))
    units = {
        u.sale_item_id: SaleItemUnitOut(
            unit_id=u.unit_id, unit_name=u.unit_name, unit_ratio=u.unit_ratio, unit_qty=u.unit_qty, unit_price=u.unit_price,
        )
        for u in db.query(SaleItemUnit).filter(SaleItemUnit.sale_item_id.in_(ids)).all()
    }
    return batches, units


def _build_sale_out(sale: Sale, hide_cost: bool = False) -> SaleOut:
    pharma_batches, pharma_units = _pharma_item_details(sale)
    items = [
        SaleItemOut(
            id=i.id,
            product_id=i.product_id,
            product_name=i.product.name if i.product else f"ID={i.product_id}",
            sku=i.product.sku if i.product else None,
            quantity=i.quantity,
            unit_price=i.unit_price,
            cost_price=None if hide_cost else i.cost_price,
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
            promotion_id=getattr(i, 'promotion_id', None),  # C4.1 (T4.3)
            promotion_discount=getattr(i, 'promotion_discount', None),
            batches=pharma_batches.get(i.id, []),
            unit_info=pharma_units.get(i.id),
        )
        for i in sale.items
    ]
    from app.schemas.sale import SalePaymentOut
    payments = [
        SalePaymentOut(
            id=p.id,
            payment_type=p.payment_type,
            amount=p.amount,
            reference=getattr(p, 'reference', None),
            terminal_id=getattr(p, 'terminal_id', None),
        )
        for p in sale.payments
    ] if hasattr(sale, 'payments') else []

    return SaleOut(
        id=sale.id,  # type: ignore
        number=sale.number,  # type: ignore
        cashier_id=sale.cashier_id,  # type: ignore
        cashier_name=sale.cashier.name if sale.cashier else f"ID={sale.cashier_id}",
        customer_id=sale.customer_id,  # type: ignore
        customer_name=sale.customer.name if getattr(sale, 'customer', None) and sale.customer.company_id == sale.company_id else None,
        warehouse_id=sale.warehouse_id,  # type: ignore
        branch_id=sale.branch_id,  # type: ignore
        **_sale_receipt_meta(sale),
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
        fiscal_factory_id=getattr(sale, 'fiscal_factory_id', None),
        delivery=_delivery_dict(getattr(sale, "delivery", None)),
        original_sale_id=getattr(sale, 'original_sale_id', None),
    )


def _build_sale_list_out(sale: Sale) -> SaleListOut:
    """Sale ORM obyektidan SaleListOut qurish (idempotent takror javob uchun)."""
    return SaleListOut(
        id=sale.id,  # type: ignore
        number=sale.number,  # type: ignore
        branch_id=sale.branch_id,  # type: ignore
        **_sale_receipt_meta(sale),
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
        customer_name=sale.customer.name if getattr(sale, 'customer', None) and sale.customer.company_id == sale.company_id else None,
        items_count=len(sale.items),  # type: ignore
        created_at=sale.created_at,  # type: ignore
        currency_code=sale.currency.code if getattr(sale, 'currency', None) else "UZS",
        debt_amounts=getattr(sale, 'debt_amounts', None),
        before_debt_balances=getattr(sale, 'before_debt_balances', None),
        original_sale_id=getattr(sale, 'original_sale_id', None),
    )


@router.post("/", response_model=SaleListOut)
def make_sale(
        data: SaleCreate,
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*POS_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),  # T1.5: X-Branch-Id -> sotuv filiali/ombori (db.info)
):
    """POS — yangi sotuv amalga oshirish"""
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

    # T3.18: terminal korxona/filialga tegishliligi va majburiy tranzaksiya raqami (sotuv yaratilishidan oldin)
    validate_sale_payment_terminals(db, current_user, data, _presale_branch_id(db, current_user, ctx, data))
    _apply_header_approval(request, data)  # C4.1 (T4.6): X-Approval-Id -> data.approval_id

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
        # Kutilmagan unique to'qnashuv (raqam hisoblagichi bilan nazariy) — 500 emas, 409 (T1.14)
        logging.getLogger(__name__).exception("Sotuvni saqlashda IntegrityError")
        raise HTTPException(status_code=409, detail="Sotuvni saqlashda ziddiyat, qayta urinib ko'ring")
    attach_payment_references(db, sale, data)  # T3.18: payments[].reference/terminal_id -> SalePayment
    cust_name = db.query(Customer.name).filter(Customer.id == sale.customer_id, Customer.company_id == sale.company_id).scalar() if sale.customer_id else None

    # ── Hippo fiskalizatsiya (background) ────────────────────────────────────
    # T3.18: faqat HIPPO_SERVER_ENABLED=true bo'lsa (standart o'chiq): lokal ko'prik o'zi fiskallaydi va natijani
    # PATCH /sales/{id}/fiscal bilan yozadi — server ham fiskallasa chek ikki marta fiskallanardi.
    # Header bo'lmasa — xato ko'tarilmaydi, sotuv normal saqlanadi.
    _factory_id = request.headers.get("X-Hippo-Factory-Id", "").strip() if settings.HIPPO_SERVER_ENABLED else ""
    if _factory_id and (
        not company_has_active_devices(db, sale.company_id)
        or device_allowed_for_branch(db, sale.company_id, _factory_id, sale.branch_id)
    ):
        background_tasks.add_task(fiscalize_sale, db, sale.id, _factory_id)  # type: ignore[arg-type]
    # ─────────────────────────────────────────────────────────────────────────

    # ── Telegram bildirishnoma ──
    # Javobdan KEYIN event loop'da yuboriladi (Telegram kechikishi chekni ushlab turmaydi, T3.16);
    # xabar matni (filial/ombor/kassir/mijoz) fon vazifasida o'z sessiyasida tuziladi
    try:
        background_tasks.add_task(notify_new_sale, sale.id)
    except Exception as e:
        print(f"Telegram notification error: {e}")

    return SaleListOut(
        id=sale.id,  # type: ignore
        number=sale.number,  # type: ignore
        branch_id=sale.branch_id,  # type: ignore
        **_sale_receipt_meta(sale),
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
        warnings=getattr(sale, 'rx_warnings', None) or [],   # D2.5: masalan, eski retsept
    )



@router.post("/bulk")
def make_bulk_sales(
        data: SaleBulkCreate,
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*POS_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),  # T1.5: X-Branch-Id -> sotuv filiali/ombori (db.info)
):
    """POS — Oflayn rejimdagi to'plangan sotuvlarni bir vaqtda jo'natish"""
    # C4.1 (T4.6): bulk uchun yagona X-Approval-Id sarlavhasi QO'LLANMAYDI (bitta tasdiq bir marta ishlatiladi, to'plam
    # esa ko'p sotuv). `block` qoidasi va tanadagi `sales[].approval_id` har sotuvda alohida ishlaydi; tasdiq talab
    # qilinadigan (`require_approval`) sotuv butun to'plamni emas, faqat o'zini `errors` ga tushiradi.
    ip = request.client.host if request.client else None
    successful = []
    errors = []

    for idx, sale_data in enumerate(data.sales):
        try:
            # Har bir sotuvni yangi savepoint ichida yaratamiz (birortasi xato qilsa hammasi to'xtamasligi uchun)
            with db.begin_nested():
                validate_sale_payment_terminals(db, current_user, sale_data, _presale_branch_id(db, current_user, ctx, sale_data))
                sale = create_sale(db=db, data=sale_data, current_user=current_user, ip=ip, background_tasks=background_tasks)
                # C4.1: reference/terminal_id create_sale ichida SalePayment ga yoziladi (attach_payment_references kerak emas)
                
                cust_name = db.query(Customer.name).filter(Customer.id == sale.customer_id, Customer.company_id == sale.company_id).scalar() if sale.customer_id else None
                
                successful.append(SaleListOut(
                    id=sale.id,  # type: ignore
                    number=sale.number,  # type: ignore
                    branch_id=sale.branch_id,  # type: ignore
                    **_sale_receipt_meta(sale),
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
                    warnings=getattr(sale, 'rx_warnings', None) or [],   # D2.5
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
        ctx: BranchContext = Depends(get_branch_context),  # T1.5: X-Branch-Id -> sotuv filiali/ombori (db.info)
):
    """Ulgurji sotuv — to'lovsiz (pending) holatda saqlash. Stock tegilmaydi."""
    ip = request.client.host if request.client else None
    sale = create_pending_sale(db=db, data=data, current_user=current_user, ip=ip)
    cust_name = db.query(Customer.name).filter(Customer.id == sale.customer_id, Customer.company_id == sale.company_id).scalar() if sale.customer_id else None
    return SaleListOut(
        id=sale.id,  # type: ignore
        number=sale.number,  # type: ignore
        branch_id=sale.branch_id,  # type: ignore
        **_sale_receipt_meta(sale),
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


def _approval_id_from_header(request: Request) -> Optional[int]:
    """C4.1 (T4.6): `X-Approval-Id` sarlavhasi (tasdiqlangan so'rov id si); noto'g'ri qiymat e'tiborsiz."""
    raw = (request.headers.get("X-Approval-Id") or "").strip()
    return int(raw) if raw.isdigit() else None


def _apply_header_approval(request: Request, data) -> None:
    """Tanada `approval_id` bo'lmasa `X-Approval-Id` sarlavhasidan qo'yadi (tana ustuvor)."""
    if getattr(data, "approval_id", None) is None:
        hdr = _approval_id_from_header(request)
        if hdr is not None:
            data.approval_id = hdr


def _read_idempotency_key(request: Request) -> Optional[str]:
    """Idempotency-Key sarlavhasi (bo'sh bo'lsa None); 64 belgidan uzun bo'lsa 400."""
    idem_key = (request.headers.get("Idempotency-Key") or "").strip() or None
    if idem_key and len(idem_key) > 64:
        raise HTTPException(status_code=400, detail="Idempotency-Key 64 belgidan oshmasligi kerak")
    return idem_key


def _find_by_idempotency_key(db: Session, user: User, idem_key: Optional[str]) -> Optional[Sale]:
    if not idem_key:
        return None
    return db.query(Sale).filter(
        Sale.idempotency_key == idem_key,
        Sale.company_id == user.company_id,
    ).first()


def _partial_return_out(db: Session, return_doc: Sale, user: User) -> SaleOut:
    """Takror kalit: birinchi javobdagi kabi asl sotuvning hozirgi holati qaytariladi."""
    target = None
    if return_doc.original_sale_id:
        target = _load_sale(db, return_doc.original_sale_id, user)
    return _build_sale_out(target or return_doc, hide_cost=user.role == UserRole.cashier)


@router.post("/{sale_id}/return-items", response_model=SaleOut)
def partial_return(
    sale_id: int,
    data: SaleReturnRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*POS_ROLES)),
):
    ip = request.client.host if request.client else None

    # Takroriy qaytarishdan himoya (make_sale dagi kabi): shu kalit bilan hujjat bor bo'lsa — mavjudini qaytaramiz
    idem_key = _read_idempotency_key(request)
    existing = _find_by_idempotency_key(db, current_user, idem_key)
    if existing:
        return _partial_return_out(db, existing, current_user)
    _apply_header_approval(request, data)  # C4.1 (T4.6)

    try:
        updated_sale = process_partial_return(
            db=db,
            sale_id=sale_id,
            data=data,
            current_user=current_user,
            ip=ip,
            idempotency_key=idem_key,
        )
    except IntegrityError:
        # Poyga holati: xuddi shu kalit bilan parallel so'rov allaqachon yaratib ulgurgan
        db.rollback()
        dup = _find_by_idempotency_key(db, current_user, idem_key)
        if dup:
            return _partial_return_out(db, dup, current_user)
        raise
    return _build_sale_out(updated_sale, hide_cost=current_user.role == UserRole.cashier)



@router.post("/return", response_model=SaleListOut)
def make_return_sale(
        data: SaleCreate,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """POS — qaytarish (vazvrat) amalga oshirish"""
    ip = request.client.host if request.client else None

    # Takroriy qaytarishdan himoya (make_sale dagi kabi): shu kalit bilan hujjat bor bo'lsa — mavjudini qaytaramiz
    idem_key = _read_idempotency_key(request)
    existing = _find_by_idempotency_key(db, current_user, idem_key)
    if existing:
        return _build_sale_list_out(existing)
    _apply_header_approval(request, data)  # C4.1 (T4.6)

    try:
        sale = create_return_sale(db=db, data=data, current_user=current_user, ip=ip, idempotency_key=idem_key)
    except IntegrityError:
        db.rollback()
        dup = _find_by_idempotency_key(db, current_user, idem_key)
        if dup:
            return _build_sale_list_out(dup)
        raise
    cust_name = db.query(Customer.name).filter(Customer.id == sale.customer_id, Customer.company_id == sale.company_id).scalar() if sale.customer_id else None
    return SaleListOut(
        id=sale.id,  # type: ignore
        number=sale.number,  # type: ignore
        branch_id=sale.branch_id,  # type: ignore
        **_sale_receipt_meta(sale),
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
        current_user: User = Depends(require_roles(*SALE_VIEW_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    from sqlalchemy import case, func
    # T3.8: items_count butun sale_items jadvalini guruhlamaydi — sahifadagi sale_id'lar uchun
    # alohida (IN) so'rov bilan hisoblanadi; asosiy so'rov oddiy Sale so'rovi (count() ham tez).
    # Eager load faqat sahifa qatorlariga (jamilar so'rovi with_entities bilan ishlaydi)
    q = db.query(Sale)
    q = q.filter(Sale.company_id == current_user.company_id)

    # T1.1: yagona filial konteksti (X-Branch-Id / users.branch_id). Filial biriktirilmagan
    # operatsion xodim (2+ filialli korxona) hech narsa ko'rmaydi; aniq `?branch_id=`
    # parametri header'dan ustun (faqat ruxsat doirasida).
    if ctx.needs_assignment:
        return {"items": [], "total": 0} if with_total else []
    # T1.9: filial — sotuv snapshot'i (Sale.branch_id); ombori yo'q (NULL) sotuv ham o'z filialida ko'rinadi
    q = apply_branch_scope(q, ctx, Sale.branch_id, explicit_branch_id=branch_id)

    if cashier_id:
        q = q.filter(Sale.cashier_id == cashier_id)
    if customer_id:
        q = q.filter(Sale.customer_id == customer_id)
    q = _sale_date_filter(q, date_from, date_to, date_today)
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
    rows = (
        q.options(joinedload(Sale.cashier), joinedload(Sale.customer), joinedload(Sale.currency), joinedload(Sale.branch))
        .order_by(Sale.created_at.desc()).offset(skip).limit(limit).all()
    )

    from app.models.sale_delivery import SaleDelivery
    _ids = [s.id for s in rows]
    items_counts = {
        sid: cnt
        for sid, cnt in db.query(SaleItem.sale_id, func.count(SaleItem.id))
        .filter(SaleItem.sale_id.in_(_ids)).group_by(SaleItem.sale_id).all()
    } if _ids else {}
    delivery_status = {
        sid: st.value if hasattr(st, "value") else st
        for sid, st in db.query(SaleDelivery.sale_id, SaleDelivery.status).filter(SaleDelivery.sale_id.in_(_ids)).all()
    } if _ids else {}

    items = [
        SaleListOut(
            id=s.id,
            number=s.number,
            branch_id=s.branch_id,
            branch_name=s.branch.name if s.branch else None,
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
            customer_name=s.customer.name if s.customer and s.customer.company_id == s.company_id else None,
            items_count=items_counts.get(s.id, 0),
            created_at=s.created_at,
            currency_code=s.currency.code if getattr(s, 'currency', None) else "UZS",
            debt_amounts=getattr(s, 'debt_amounts', None),
            delivery_status=delivery_status.get(s.id),
        )
        for s in rows
    ]
    if with_total:
        # Jamilar butun filtr bo'yicha (ro'yxat ostidagi "N ta sotuv" faqat sahifadagini ko'rsatmasin)
        s_total, s_paid, s_debt = q.with_entities(
            func.coalesce(func.sum(Sale.total_amount), 0),
            func.coalesce(func.sum(Sale.paid_amount), 0),
            func.coalesce(func.sum(case((Sale.total_amount > Sale.paid_amount, Sale.total_amount - Sale.paid_amount), else_=0)), 0),
        ).one()
        return {"items": items, "total": total,
                "sum_total": float(s_total or 0), "sum_paid": float(s_paid or 0), "sum_debt": float(s_debt or 0)}
    return items


def _sale_date_filter(q, date_from, date_to, date_today):
    """Sotuv sanasi filtri Toshkent vaqtida (T2.8 date_bounds): kun 00:00 da boshlanadi.
    Avval UTC yarim tuni (Toshkent 05:00) edi — tungi sotuvlar oldingi kunga tushardi."""
    from app.utils.report_utils import date_bounds, local_day_start, local_today
    if date_today:
        q = q.filter(Sale.created_at >= local_day_start(local_today()))
    if date_from or date_to:
        start, end = date_bounds(date_from, date_to)
        q = q.filter(Sale.created_at >= start, Sale.created_at < end)
    return q


@router.get("/export/pdf")
def export_sales_pdf(
        cashier_id: Optional[int] = Query(None),
        branch_id: Optional[int] = Query(None),
        customer_id: Optional[int] = Query(None),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        date_today: Optional[bool] = Query(None),
        status: Optional[SaleStatus] = Query(None),
        search: Optional[str] = Query(None),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*SALE_VIEW_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    from app.utils.sale_pdf import generate_sales_list_pdf_bytes, content_disposition

    q = (
        db.query(Sale)
        .options(joinedload(Sale.cashier), joinedload(Sale.customer), joinedload(Sale.currency), joinedload(Sale.branch))
        .filter(Sale.company_id == current_user.company_id)
    )

    if ctx.needs_assignment:
        sales = []
    else:
        q = apply_branch_scope(q, ctx, Sale.branch_id, explicit_branch_id=branch_id)
        if cashier_id:
            q = q.filter(Sale.cashier_id == cashier_id)
        if customer_id:
            q = q.filter(Sale.customer_id == customer_id)
        q = _sale_date_filter(q, date_from, date_to, date_today)
        if status:
            q = q.filter(Sale.status == status)
        else:
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
        sales = q.order_by(Sale.created_at.desc()).limit(1000).all()

    company_name = None
    if current_user.company_id:
        comp = db.query(Company).filter(Company.id == current_user.company_id).first()
        company_name = getattr(comp, "name", None)
    if not company_name:
        company_name = "E-Code ERP"

    pdf_bytes = generate_sales_list_pdf_bytes(
        sales=sales,
        date_from=str(date_from) if date_from else "",
        date_to=str(date_to) if date_to else "",
        company_name=company_name,
    )
    filename = f"Sotuvlar_hisoboti_{date_from or 'barcha'}_{date_to or 'hozirgacha'}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(filename),
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(
        sale_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*SALE_VIEW_ROLES)),
):
    sale = _load_sale(db, sale_id, current_user)
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")
    out = _build_sale_out(sale, hide_cost=current_user.role == UserRole.cashier)
    # D2.5: retseptlar (oddiy korxonada jadval bo'sh — javob avvalgidek, prescriptions=[])
    out.prescriptions = [
        SalePrescriptionOut.model_validate(p) for p in
        db.query(SalePrescription).filter(
            SalePrescription.sale_id == sale.id, SalePrescription.company_id == sale.company_id,
        ).order_by(SalePrescription.id).all()
    ]
    return out


@router.get("/{sale_id}/pdf")
def get_sale_pdf(
        sale_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*SALE_VIEW_ROLES)),
):
    from app.utils.sale_pdf import generate_sale_pdf_bytes, get_sale_pdf_filename, content_disposition

    sale = _load_sale(db, sale_id, current_user)
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")

    pdf_bytes = generate_sale_pdf_bytes(sale)
    filename = get_sale_pdf_filename(sale)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(filename),
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


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

    # T3.18: korxonada fiskal qurilmalar ro'yxati bo'lsa, factory_id sotuv filialidagi qurilmalardan biri bo'lishi shart.
    # Ro'yxat bo'sh korxonalarda tekshiruv o'tkazib yuboriladi (orqaga moslik).
    new_factory = update_data.get("fiscal_factory_id")
    if new_factory and sale.company_id is not None and company_has_active_devices(db, sale.company_id):
        _br = _sale_branch(sale)
        if not device_allowed_for_branch(db, sale.company_id, new_factory, _br.id if _br is not None else None):
            raise HTTPException(status_code=409, detail="Fiskal modul bu filialga biriktirilmagan")

    ALLOWED = {"fiscal_sign", "fiscal_qr_url", "fiscal_receipt_seq", "fiscal_transaction_id", "fiscal_at", "fiscal_factory_id"}
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
    return _build_sale_out(sale, hide_cost=current_user.role == UserRole.cashier)


@router.get("/{sale_id}/receipt")
def get_receipt(
        sale_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*SALE_VIEW_ROLES)),
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
        # T3.7: chek rekvizitlari
        "branch_id": sale.branch_id,
        **_sale_receipt_meta(sale),
    }


@router.put("/{sale_id}", response_model=SaleOut)
def edit_sale(
        sale_id: int,
        data: SaleUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """Sotuvni tahrirlash: holat, izoh, to'lov miqdori"""
    # C4.1: payments[].terminal_id / reference SalePayment ga yoziladi -> yaratishdagi kabi korxona/filial/reference
    # tekshiruvi (begona korxona terminali 404, mos kelmasa 400). Sotuv topilmasa update_sale o'zi 404 beradi.
    if data.payments:
        _row = db.query(Sale.company_id, Sale.branch_id).filter(Sale.id == sale_id).first()
        if _row is not None and (current_user.role == UserRole.super_admin or _row.company_id == current_user.company_id):
            validate_sale_payment_terminals(db, SimpleNamespace(company_id=_row.company_id), data, _row.branch_id)
    sale = update_sale(db=db, sale_id=sale_id, data=data, current_user=current_user)
    sale = _load_sale(db, sale.id, current_user)  # type: ignore
    return _build_sale_out(sale, hide_cost=current_user.role == UserRole.cashier)


@router.put("/{sale_id}/assign-customer", response_model=SaleOut)
def assign_sale_customer_endpoint(
        sale_id: int,
        data: SaleAssignCustomer,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*POS_ROLES)),
):
    """Sotuvga yangi mijoz biriktirish (qarzni yangi mijozga ko'chirish va sotuv sanasini saqlab qolish)."""
    sale = reassign_sale_customer(db=db, sale_id=sale_id, new_customer_id=data.customer_id, current_user=current_user)
    sale = _load_sale(db, sale.id, current_user)  # type: ignore
    return _build_sale_out(sale, hide_cost=current_user.role == UserRole.cashier)


@router.delete("/{sale_id}")
def remove_sale(
        sale_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    """Sotuvni o'chirish va mahsulot qoldiqlarini qaytarish"""
    delete_sale(db=db, sale_id=sale_id, current_user=current_user, approval_id=_approval_id_from_header(request))  # C4.1 (T4.6)
    return {"message": "Sotuv o'chirildi va qoldiqlar qaytarildi"}


