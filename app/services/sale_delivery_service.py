"""
Ulgurji sotuvni yetkazib berish (SaleDelivery) — sotuv yaratish/tahrirlash
servislaridan chaqiriladi, Logistika marshrutlari va kuryer boti bilan
ishlaydi. Status o'zgarishlari Order bilan bir xil mantiqqa ega, lekin
"yetkazildi" yangi sotuv yaratmaydi (sotuv allaqachon bor).
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.sale import Sale
from app.models.sale_delivery import SaleDelivery, SaleDeliveryStatus

FINAL = (SaleDeliveryStatus.delivered, SaleDeliveryStatus.cancelled)


def upsert_sale_delivery(db: Session, sale: Sale, data, company_id: int) -> Optional[SaleDelivery]:
    """data (DeliveryIn) berilmasa — hech narsa qilinmaydi. enabled=False —
    yakunlanmagan yetkazma bekor qilinadi."""
    if data is None:
        return None
    existing = db.query(SaleDelivery).filter(SaleDelivery.sale_id == sale.id).first()

    if not data.enabled:
        if existing and existing.status not in FINAL:
            existing.status = SaleDeliveryStatus.cancelled
            existing.cancel_reason = "Sotuvda yetkazish o'chirildi"
        return existing

    from app.core.features import company_has_feature
    if not existing and not company_has_feature(db, company_id, "distribution"):
        return None  # modul o'chiq — yangi yetkazma yaratilmaydi

    customer = db.query(Customer).filter(Customer.id == sale.customer_id).first() if sale.customer_id else None
    address = (data.address or "").strip() or None
    lat, lng = data.lat, data.lng
    if lat is None or lng is None:
        lat = lng = None
    # Manzil qo'lda boshqacha yozilgan bo'lsa, mijozning eski nuqtasini olmaymiz —
    # aks holda kuryer noto'g'ri joyga boradi
    if customer and not address:
        address = ", ".join(x for x in (customer.district, customer.address) if x) or None
        if lat is None and customer.lat is not None:
            lat, lng = customer.lat, customer.lng
    phone = (data.contact_phone or "").strip() or (customer.phone if customer else None)

    d = existing or SaleDelivery(sale_id=sale.id, company_id=company_id)
    if existing and existing.status == SaleDeliveryStatus.delivered:
        return existing  # yetkazilgan yetkazmani o'zgartirmaymiz
    if existing and existing.status == SaleDeliveryStatus.cancelled:
        d.status = SaleDeliveryStatus.pending
        d.courier_id = None
        d.cancel_reason = None
    d.address = address
    d.lat, d.lng = lat, lng
    d.contact_phone = phone
    d.delivery_fee = data.delivery_fee or Decimal("0")
    d.planned_date = data.planned_date
    d.note = (data.note or "").strip() or None
    if not existing:
        d.status = SaleDeliveryStatus.pending
        db.add(d)
    db.flush()
    return d


def cancel_sale_delivery(db: Session, sale_id: int, reason: str) -> None:
    """Sotuv bekor qilinsa/to'liq qaytarilsa — yetkazma ham bekor."""
    d = db.query(SaleDelivery).filter(SaleDelivery.sale_id == sale_id).first()
    if d and d.status not in FINAL:
        d.status = SaleDeliveryStatus.cancelled
        d.cancel_reason = reason


def set_status(d: SaleDelivery, status: SaleDeliveryStatus, courier_id: Optional[int] = None) -> None:
    now = datetime.now(timezone.utc)
    d.status = status
    if status == SaleDeliveryStatus.assigned:
        d.courier_id = courier_id
        d.assigned_at = now
    elif status == SaleDeliveryStatus.loaded:
        d.loaded_at = now
    elif status == SaleDeliveryStatus.on_way:
        d.on_way_at = now
    elif status == SaleDeliveryStatus.delivered:
        d.delivered_at = now


def release(d: SaleDelivery) -> None:
    """Marshrutdan chiqarilgan yetkazmani qayta rejalashtirishga qaytarish."""
    if d.status not in FINAL:
        d.status = SaleDeliveryStatus.pending
        d.courier_id = None
        d.assigned_at = None
        d.loaded_at = None
        d.on_way_at = None


def _fee_goes_to_debt(sale: Sale) -> bool:
    pt = sale.payment_type.value if hasattr(sale.payment_type, "value") else str(sale.payment_type)
    unpaid = str(getattr(sale.status, "value", sale.status)) == "pending"
    return bool(sale.customer_id) and (unpaid or pt in ("debt", "mixed"))


def collect_amount(d: SaleDelivery) -> float:
    """Kuryer mijozdan yig'adigan summa. Tovar puli sotuvda hisoblangan
    (to'langan yoki qarzga yozilgan) — kuryer faqat to'langan sotuvning
    yetkazish haqini naqd oladi; qarz/to'lanmagan sotuvda hech narsa."""
    fee = float(d.delivery_fee or 0)
    return 0.0 if _fee_goes_to_debt(d.sale) else fee


def acting_user(db: Session, company_id: int):
    """Kuryer boti kabi foydalanuvchisiz kontekst uchun: moliya yozuvlari
    kompaniyaning birinchi admin/direktori nomidan (order_to_sale naqshi)."""
    from app.models.user import User, UserRole
    u = db.query(User).filter(
        User.company_id == company_id, User.role.in_([UserRole.admin, UserRole.director]),
    ).order_by(User.id.asc()).first()
    return u or db.query(User).filter(User.company_id == company_id).order_by(User.id.asc()).first()


def record_fee_once(db: Session, d: SaleDelivery, user) -> None:
    """Yetkazilganda yetkazish haqini moliyaga BIR MARTA yozadi. To'lov turi
    sotuvnikidan: qarzga bo'lsa mijoz qarziga, aks holda kassaga kirim."""
    fee = Decimal(str(d.delivery_fee or 0))
    if fee <= 0 or d.fee_recorded:
        return
    sale = db.query(Sale).filter(Sale.id == d.sale_id).first()
    if not sale:
        return
    # Pending (to'lanmagan) yoki qarz/aralash sotuvda haq mijoz qarziga,
    # aks holda kuryer naqd oladi — collect_amount bilan bir xil qoida
    payment_type = "debt" if _fee_goes_to_debt(sale) else "cash"
    from app.services.order_to_sale import record_delivery_fee
    record_delivery_fee(db, sale, fee, payment_type, user)
    d.fee_recorded = 1


def deduct_delivery_stock(db: Session, d: SaleDelivery, user_id: Optional[int] = None) -> None:
    """Ombordan tovarlarni chiqarish (StockLevel va StockMovement). Idempotent: bir marta ishlaydi."""
    if d.stock_deducted:
        return
    sale = db.query(Sale).filter(Sale.id == d.sale_id).first()
    if not sale:
        return
    from app.services.inventory_service import deduct_stock
    from app.utils.product_conversion import deduct_target_for_sale
    from app.models.company import Company
    company = db.query(Company).filter(Company.id == d.company_id).first()
    allow_negative = getattr(company, "pos_allow_negative_stock", True) if company else True
    u_id = user_id or d.loaded_by or sale.user_id or 1

    for item in sale.items:
        deduct_id, deduct_qty, conv, src = deduct_target_for_sale(db, item.product_id, item.quantity)
        reason = f"Yetkazma orqali chiqim (sotuv #{sale.id}, yetkazma #{d.id})"
        if conv and src:
            reason += f" ({item.product.name} → {src.name} x{conv.ratio})"
        deduct_stock(
            db=db,
            product_id=deduct_id,
            quantity=deduct_qty,
            user_id=u_id,
            reason=reason,
            reference_type="sale_delivery",
            reference_id=d.id,
            warehouse_id=item.warehouse_id or sale.warehouse_id,
            allow_negative=allow_negative,
        )
    d.stock_deducted = True


def restore_delivery_stock(db: Session, d: SaleDelivery, user_id: Optional[int] = None) -> None:
    """Bekor qilingan yetkazma tovarlarini omborga qaytarish."""
    if not d.stock_deducted:
        return
    sale = db.query(Sale).filter(Sale.id == d.sale_id).first()
    if not sale:
        return
    from app.services.inventory_service import receive_stock
    from app.utils.product_conversion import deduct_target_for_sale
    u_id = user_id or sale.user_id or 1

    for item in sale.items:
        deduct_id, deduct_qty, conv, src = deduct_target_for_sale(db, item.product_id, item.quantity)
        reason = f"Bekor qilingan yetkazma tovari qaytdi (sotuv #{sale.id}, yetkazma #{d.id})"
        receive_stock(
            db=db,
            product_id=deduct_id,
            quantity=deduct_qty,
            user_id=u_id,
            reason=reason,
            reference_type="sale_delivery_cancel",
            reference_id=d.id,
            warehouse_id=item.warehouse_id or sale.warehouse_id,
            company_id=d.company_id,
        )
    d.stock_deducted = False


def handle_delivery_stage_stock(db: Session, d: SaleDelivery, new_status: SaleDeliveryStatus, user_id: Optional[int] = None) -> None:
    """Hippo ERP qoldiq boshqaruvi:
    Kompaniya sozlamasiga ko'ra (stock_deduct_stage):
    - 'order_confirmed': sotuv tasdiqlanganda chiqadi. Bekor bo'lsa qaytariladi.
    - 'loaded': omborchi mashinaga yuklaganda chiqadi. Bekor bo'lsa qaytariladi.
    - 'delivered': kuryer mijozga topshirganda chiqadi. Bekor bo'lsa qaytariladi.
    """
    from app.models.company import Company
    company = db.query(Company).filter(Company.id == d.company_id).first()
    stage = getattr(company, "stock_deduct_stage", "order_confirmed") or "order_confirmed"

    if stage == "loaded":
        if new_status in (SaleDeliveryStatus.loaded, SaleDeliveryStatus.on_way):
            deduct_delivery_stock(db, d, user_id)
        elif new_status == SaleDeliveryStatus.cancelled:
            restore_delivery_stock(db, d, user_id)
    elif stage == "delivered":
        if new_status == SaleDeliveryStatus.delivered:
            deduct_delivery_stock(db, d, user_id)
        elif new_status == SaleDeliveryStatus.cancelled:
            restore_delivery_stock(db, d, user_id)
    elif stage == "order_confirmed":
        if new_status == SaleDeliveryStatus.cancelled:
            restore_delivery_stock(db, d, user_id)

