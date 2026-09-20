"""
Buyurtma "yetkazildi" bo'lganda avtomatik Sale (sotuv) yaratish.

Company.orders_auto_create_sale = True bo'lsa ishlaydi. create_sale
servisi qayta ishlatiladi — shu tufayli ombor (FIFO batch), kassa
harakati, wallet balansi, qarz (payment_type=debt bo'lsa) va boshqa
barcha sotuv mantig'i bir xil ishlaydi.

Idempotentlik: guruhdagi qatorlarga Order.sale_id yoziladi — bir guruh
uchun faqat bitta Sale yaratiladi.

Eslatma: delivery_fee hozircha Sale'ga KIRMAYDI (alohida "yetkazish
xizmati" mahsuloti mavjud emas) — u sotuv izohida ko'rsatiladi.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.order import Order
from app.models.user import User, UserRole


def maybe_create_sale_for_delivered_group(db: Session, orders: list) -> None:
    """Background task: guruh yetkazilganda (sozlama yoqiq bo'lsa) Sale yaratadi.

    Xato yuz bersa yetkazish statusiga ta'sir qilmaydi — log + admin botga
    ogohlantirish yuboriladi.
    """
    try:
        if not orders:
            return
        first = orders[0]

        # Idempotentlik — allaqachon Sale yaratilgan bo'lsa chiqamiz
        if any(getattr(o, "sale_id", None) for o in orders):
            return

        customer_company_id = None
        if first.customer:
            customer_company_id = first.customer.company_id
        if not customer_company_id:
            from app.models.customer import Customer
            cust = db.query(Customer).filter(Customer.id == first.customer_id).first()
            customer_company_id = cust.company_id if cust else None
        if not customer_company_id:
            return

        company = db.query(Company).filter(Company.id == customer_company_id).first()
        if not company or company.orders_auto_create_sale is not True:
            return

        # Sotuvni kim nomidan yozamiz: kompaniyaning birinchi admin/direktori
        acting_user = db.query(User).filter(
            User.company_id == company.id,
            User.role.in_([UserRole.admin, UserRole.director]),
        ).order_by(User.id.asc()).first()
        if not acting_user:
            acting_user = db.query(User).filter(User.company_id == company.id).order_by(User.id.asc()).first()
        if not acting_user:
            return

        from app.schemas.sale import SaleCreate, SaleItemCreate

        items = [
            SaleItemCreate(
                product_id=o.product_id,
                quantity=Decimal(str(o.quantity)),
                unit_price=Decimal(str(o.unit_price or 0)),
                discount=Decimal("0"),
            )
            for o in orders
        ]
        total = sum(Decimal(str(o.total_amount or 0)) for o in orders)
        payment_type = (first.payment_type or "cash").strip().lower()
        if payment_type not in ("cash", "card", "debt"):
            payment_type = "cash"

        fee = Decimal(str(getattr(first, "delivery_fee", 0) or 0))
        note_parts = [f"Buyurtma yetkazildi (#{first.order_group_id or first.id})"]
        if fee > 0:
            note_parts.append(f"Yetkazish haqi: {fee:,.0f} so'm (sotuvga kirmagan)")

        data = SaleCreate(
            items=items,
            payment_type=payment_type,
            paid_amount=Decimal("0") if payment_type == "debt" else total,
            paid_cash=total if payment_type == "cash" else Decimal("0"),
            paid_card=total if payment_type == "card" else Decimal("0"),
            discount_amount=Decimal("0"),
            customer_id=first.customer_id,
            note=" | ".join(note_parts),
        )

        from app.services.sale_create import create_sale
        sale = create_sale(db=db, data=data, current_user=acting_user)

        for o in orders:
            o.sale_id = sale.id
        db.commit()

        # Admin botga xabar
        try:
            from app.admin_tg_bot.notifications import trigger_instant_notification
            trigger_instant_notification(
                company.id,
                f"📦➡️🧾 Buyurtma yetkazildi va sotuvga aylantirildi\n"
                f"Chek: #{sale.number}\n💰 {float(total):,.0f} so'm",
                "sale",
            )
        except Exception:
            pass

    except Exception as e:
        print(f"[order_to_sale] Avto-sotuv yaratishda xato: {e}")
        try:
            from app.admin_tg_bot.notifications import trigger_instant_notification
            first = orders[0] if orders else None
            comp_id = first.customer.company_id if (first and first.customer) else None
            if comp_id:
                trigger_instant_notification(
                    comp_id,
                    f"⚠️ Buyurtma yetkazildi, lekin avto-sotuv yaratilmadi: {e}\n"
                    f"Guruh: {getattr(first, 'order_group_id', '?')} — POS orqali qo'lda kiriting.",
                    "sale",
                )
        except Exception:
            pass
