"""
Tariff Guard Service:
Kompaniyalarning obuna tariflaridagi limitlarini (tovar/shtrix-kod, agentlar,
kuryerlar, ishlab chiqarish, buyurtmalar) tekshirish va narx kalkulyatsiyasi.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import Tariff
from app.models.company import Company
from app.models.courier import Courier
from app.models.product import Product
from app.models.production_order import ProductionOrder
from app.models.user import User, UserRole, UserStatus


def get_company_tariff(db: Session, company_id: int) -> Optional[Tariff]:
    """Kompaniyaning joriy tarifini oladi"""
    if not company_id:
        return None
    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp or not comp.tariff_id:
        return None
    return db.query(Tariff).filter(Tariff.id == comp.tariff_id).first()


def check_product_limit(db: Session, company_id: int, count_to_add: int = 1) -> None:
    """Tovar (shtrix-kod) limitini tekshiradi (masalan: Mini tarifda 700 ta)"""
    tariff = get_company_tariff(db, company_id)
    if not tariff or tariff.max_products is None:
        return

    current_count = db.query(Product).filter(
        Product.company_id == company_id,
        Product.is_deleted == False
    ).count()

    if current_count + count_to_add > tariff.max_products:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Sizning tarifingizda mahsulotlar (shtrix-kodlar) limiti "
                f"({tariff.max_products} dona) to'ldi. Hozirda {current_count} ta mahsulot mavjud. "
                f"Yangi mahsulot qo'shish uchun tarifingizni yuqoriroq paketga yangilang."
            )
        )


def check_agent_limit(db: Session, company_id: int) -> None:
    """Savdo agentlari (role=agent) limitini tekshiradi"""
    tariff = get_company_tariff(db, company_id)
    if not tariff:
        return

    # Agar max_agents 0 bo'lsa yoki distribution o'chiq bo'lsa
    if tariff.max_agents == 0 or not tariff.has_distribution:
        raise HTTPException(
            status_code=403,
            detail="Savdo agentlari (SFA) moduli sizning tarifingizda mavjud emas. Distribyutor tarifiga o'ting."
        )

    if tariff.max_agents is not None:
        current_agents = db.query(User).filter(
            User.company_id == company_id,
            User.role == UserRole.agent,
            User.status != UserStatus.blocked
        ).count()

        if current_agents >= tariff.max_agents:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Sizning tarifingizda savdo agentlari limiti ({tariff.max_agents} ta) to'lgan. "
                    f"Yangi agent qo'shish uchun yuqoriroq tarifga o'ting yoki qo'shimcha agent litsenziyasi oling."
                )
            )


def check_courier_limit(db: Session, company_id: int) -> None:
    """Yetkazib beruvchilar (kuryerlar) limitini tekshiradi"""
    tariff = get_company_tariff(db, company_id)
    if not tariff:
        return

    if tariff.max_couriers == 0 or not tariff.has_distribution:
        raise HTTPException(
            status_code=403,
            detail="Yetkazib berish (kuryerlar) moduli sizning tarifingizda mavjud emas. Distribyutor tarifiga o'ting."
        )

    if tariff.max_couriers is not None:
        current_couriers = db.query(Courier).filter(
            Courier.company_id == company_id,
            Courier.is_active == True
        ).count()

        if current_couriers >= tariff.max_couriers:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Sizning tarifingizda dastavchiklar (kuryerlar) limiti ({tariff.max_couriers} ta) to'lgan. "
                    f"Yangi kuryer qo'shish uchun tarifingizni oshiring."
                )
            )


def check_production_limit(db: Session, company_id: int) -> None:
    """Ishlab chiqarish (BOM / Partiyalar) ruxsati va oylik kvotasini tekshiradi"""
    tariff = get_company_tariff(db, company_id)
    if not tariff:
        return

    if not tariff.has_manufacturing:
        raise HTTPException(
            status_code=403,
            detail="Ishlab chiqarish moduli sizning tarifingizda mavjud emas. Ushbu moduldan foydalanish uchun Distribyutor tarifiga o'ting."
        )

    if tariff.max_production_orders is not None:
        now = datetime.now(timezone.utc)
        first_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        orders_this_month = db.query(ProductionOrder).filter(
            ProductionOrder.company_id == company_id,
            ProductionOrder.created_at >= first_of_month
        ).count()

        if orders_this_month >= tariff.max_production_orders:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Shu oy uchun ishlab chiqarish buyurtmalari kvotasi ({tariff.max_production_orders} ta) to'lgan. "
                    f"Keyingi oy boshlanishini kuting yoki yuqori tarifga o'ting."
                )
            )


def calculate_subscription_price(tariff: Tariff, months: int) -> Dict[str, Any]:
    """
    Obuna narxi va chegirmasini hisoblaydi.
    Mini: oyma-oy (1 oy).
    Distribyutorlar: kamida min_duration_months (masalan 3 oy).
    Chegirmalar: 3 oy - 0%, 6 oy - 10%, 12 oy - 20%.
    """
    min_months = tariff.min_duration_months or 1
    if months < min_months:
        raise HTTPException(
            status_code=400,
            detail=f"'{tariff.name}' tarifi kamida {min_months} oylik paket bilan faollashtiriladi."
        )

    monthly_price = float(tariff.price_per_month or 0)
    original_total = monthly_price * months

    # Chegirma foizini aniqlash
    discount_pct = 0
    if tariff.period_discounts and isinstance(tariff.period_discounts, dict):
        discount_pct = float(tariff.period_discounts.get(str(months), 0))
    else:
        if months >= 12:
            discount_pct = 20.0
        elif months >= 6:
            discount_pct = 10.0
        elif months >= 3:
            discount_pct = 0.0

    discount_amount = round(original_total * (discount_pct / 100.0), 2)
    final_price = round(original_total - discount_amount, 2)

    return {
        "tariff_id": tariff.id,
        "tariff_name": tariff.name,
        "months": months,
        "price_per_month": monthly_price,
        "original_total": original_total,
        "discount_percent": discount_pct,
        "discount_amount": discount_amount,
        "total_price": final_price,
    }
