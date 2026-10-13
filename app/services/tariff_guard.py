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


def count_company_barcodes(db: Session, company_id: int) -> int:
    """
    Kompaniyaning barcha ishlatilgan shtrix-kodlarini hisoblaydi:
    - Asosiy shtrix-kodlar (is_deleted == False va barcode mavjud)
    - Qo'shimcha shtrix-kodlar (extra_barcodes JSON ro'yxatidagi har bir kod)
    - Variantlarning shtrix-kodlari (ProductVariant.barcode)
    """
    if not company_id:
        return 0

    import json
    from app.models.product_variant import ProductVariant

    # 1. Asosiy va extra_barcodes
    products = db.query(Product.barcode, Product.extra_barcodes).filter(
        Product.company_id == company_id,
        Product.is_deleted == False
    ).all()

    total = 0
    for p_bc, extra_bc_raw in products:
        if p_bc and str(p_bc).strip():
            total += 1
        if extra_bc_raw:
            try:
                parsed = json.loads(extra_bc_raw) if isinstance(extra_bc_raw, str) else extra_bc_raw
                if isinstance(parsed, list):
                    total += len([b for b in parsed if b and str(b).strip()])
            except Exception:
                pass

    # 2. Variantlar shtrix-kodlari
    variant_bc_count = db.query(ProductVariant.id).join(
        Product, Product.id == ProductVariant.product_id
    ).filter(
        Product.company_id == company_id,
        Product.is_deleted == False,
        ProductVariant.barcode.isnot(None),
        ProductVariant.barcode != ""
    ).count()

    total += variant_bc_count
    return total


def get_company_barcode_stats(db: Session, company_id: int) -> dict:
    """Kompaniya shtrix-kodlari limit va sarf statistikasi"""
    tariff = get_company_tariff(db, company_id)
    limit = tariff.max_products if tariff else None
    used = count_company_barcodes(db, company_id)
    percent = round((used / limit) * 100, 1) if (limit and limit > 0) else None
    return {
        "used": used,
        "limit": limit,
        "percent": percent,
        "is_warning": bool(percent and percent >= 90.0 and percent < 100.0),
        "is_exceeded": bool(limit and used >= limit),
    }


def check_product_limit(db: Session, company_id: int, count_to_add: int = 1) -> None:
    """Shtrix-kod limitini tekshiradi (masalan: Kichik do'konda 500 ta shtrix-kod)"""
    tariff = get_company_tariff(db, company_id)
    if not tariff or tariff.max_products is None:
        return

    current_count = count_company_barcodes(db, company_id)
    if current_count + count_to_add > tariff.max_products:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Sizning tarifingizda shtrix-kodlar limiti ({tariff.max_products} dona) to'ldi. "
                f"Hozirda {current_count} ta shtrix-kod band qilingan (+{count_to_add} qo'shilmoqda). "
                f"Yangi tovar qo'shish uchun tarifingizni yuqoriroq paketga yangilang yoki foydalanilmayotgan tovarlarni o'chiring."
            )
        )


def check_agent_limit(db: Session, company_id: int) -> None:
    """Savdo agentlari (role=agent) limitini tekshiradi"""
    from app.core.features import company_has_feature
    if not company_has_feature(db, company_id, "distribution"):
        raise HTTPException(
            status_code=403,
            detail="Savdo agentlari (SFA) moduli sizning kompaniyangizda yoqilmagan. Distribyutsiya paketini faollashtiring yoki mos tarifga o'ting."
        )

    tariff = get_company_tariff(db, company_id)
    if tariff and tariff.max_agents is not None:
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
    from app.core.features import company_has_feature
    if not company_has_feature(db, company_id, "distribution"):
        raise HTTPException(
            status_code=403,
            detail="Yetkazib berish (kuryerlar) moduli sizning kompaniyangizda yoqilmagan. Distribyutsiya paketini faollashtiring yoki mos tarifga o'ting."
        )

    tariff = get_company_tariff(db, company_id)
    if tariff and tariff.max_couriers is not None:
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
    from app.core.features import company_has_feature
    if not company_has_feature(db, company_id, "manufacturing"):
        raise HTTPException(
            status_code=403,
            detail="Ishlab chiqarish moduli sizning kompaniyangizda yoqilmagan. Ishlab chiqarish paketini faollashtiring yoki mos tarifga o'ting."
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


def calculate_subscription_price(tariff: Tariff, months: int, bhm: Optional[float] = None) -> Dict[str, Any]:
    """
    Obuna narxi va chegirmasini hisoblaydi.
    Mini: oyma-oy (1 oy).
    Distribyutorlar: kamida min_duration_months (masalan 3 oy).
    Chegirmalar: 3 oy - 0%, 6 oy - 10%, 12 oy - 20%.
    BHM foizi (bhm_percent) ko'rsatilgan bo'lsa, narx BHM miqdoridan kelib chiqib hisoblanadi.
    """
    min_months = tariff.min_duration_months or 1
    if months < min_months:
        raise HTTPException(
            status_code=400,
            detail=f"'{tariff.name}' tarifi kamida {min_months} oylik paket bilan faollashtiriladi."
        )

    monthly_price = float(tariff.price_per_month or 0)
    if tariff.bhm_percent and tariff.bhm_percent > 0:
        bhm_val = bhm if bhm is not None else 440000.0
        monthly_price = round(bhm_val * (float(tariff.bhm_percent) / 100.0))

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
