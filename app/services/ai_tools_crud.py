"""
ai_tools_crud.py
─────────────────
AI Copilot orqali mahsulot va mijozlarni yaratish/tahrirlash uchun tool'lar.
"""
import random
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.product import Product, ProductStatus
from app.models.customer import Customer
from app.services.ai_tools_registry import AITool, AIToolRegistry, _find_customer


def _sf(val) -> float:
    try:
        return float(val or 0)
    except Exception:
        return 0.0


def _fmt(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ") + " so'm"


def _gen_barcode(db: Session) -> str:
    """8 xonali noyob shtrix kod generatsiya qiladi."""
    for _ in range(30):
        code = str(random.randint(10000000, 99999999))
        if not db.query(Product).filter(Product.barcode == code).first():
            return code
    raise ValueError("Shtrix kod generatsiya qilib bo'lmadi, qayta urinib ko'ring")


def _find_product(db: Session, company_id: int, name: str):
    name = (name or "").strip()
    products = db.query(Product).filter(
        Product.company_id == company_id,
        Product.is_deleted == False,
        Product.name.ilike(f"%{name}%"),
    ).limit(6).all()
    if not products:
        return None, f"❌ '{name}' nomli mahsulot topilmadi."
    if len(products) > 1:
        names = ", ".join(p.name for p in products[:5])
        return None, f"⚠️ '{name}' so'ziga mos {len(products)} ta mahsulot topildi ({names}...). Iltimos, nomni to'liqroq yozing."
    return products[0], None


@AIToolRegistry.register
class CreateProductTool(AITool):
    name = "create_product"
    description = "Yangi mahsulot yaratish (nomi va narxi bilan). Shtrix kod berilmasa avtomatik generatsiya qilinadi."
    required_permission = "products.create"
    risk_level = "MEDIUM"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Mahsulot nomi"},
            "sale_price": {"type": "number", "description": "Sotuv (chakana) narxi, so'mda"},
            "cost_price": {"type": "number", "description": "Tan narxi, so'mda. Berilmasa 0."},
            "unit": {"type": "string", "description": "O'lchov birligi: dona, kg, litr va h.k. Standart: dona"},
            "barcode": {"type": "string", "description": "Shtrix kod. Berilmasa avtomatik generatsiya qilinadi."},
        },
        "required": ["name", "sale_price"],
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        name = (kwargs.get("name") or "").strip()
        if not name:
            return {"reply": "❌ Mahsulot nomini kiriting."}

        sale_price = _sf(kwargs.get("sale_price", 0))
        if sale_price <= 0:
            return {"reply": "❌ Sotuv narxi musbat bo'lishi kerak."}

        cost_price = _sf(kwargs.get("cost_price", 0))
        unit = (kwargs.get("unit") or "dona").strip() or "dona"
        barcode = (kwargs.get("barcode") or "").strip()

        if barcode:
            existing = db.query(Product).filter(
                Product.barcode == barcode,
                Product.company_id == company_id,
                Product.is_deleted == False,
            ).first()
            if existing:
                return {"reply": f"❌ '{barcode}' shtrix kodli mahsulot allaqachon mavjud: {existing.name}."}
        else:
            barcode = _gen_barcode(db)

        product = Product(
            name=name,
            sku=f"SKU-{barcode[-6:]}",
            barcode=barcode,
            company_id=company_id,
            unit=unit,
            cost_price=Decimal(str(cost_price)),
            sale_price=Decimal(str(sale_price)),
            status=ProductStatus.active,
            product_type="simple",
        )
        db.add(product)
        db.commit()
        db.refresh(product)

        return {
            "reply": f"✅ '{name}' mahsuloti yaratildi. Shtrix kod: {barcode}, narx: {_fmt(sale_price)}.",
            "action": {"type": "product_created", "product_id": product.id},
        }


@AIToolRegistry.register
class UpdateProductTool(AITool):
    name = "update_product"
    description = "Mavjud mahsulotning nomi yoki narxini (sotuv/tan narxi) o'zgartirish."
    required_permission = "products.edit"
    risk_level = "HIGH"  # Narxni o'zgartirish sotuvlarga bevosita ta'sir qiladi
    parameters = {
        "type": "object",
        "properties": {
            "product_name": {"type": "string", "description": "O'zgartiriladigan mahsulotning joriy nomi"},
            "new_name": {"type": "string", "description": "Yangi nom (ixtiyoriy)"},
            "new_sale_price": {"type": "number", "description": "Yangi sotuv narxi, so'mda (ixtiyoriy)"},
            "new_cost_price": {"type": "number", "description": "Yangi tan narxi, so'mda (ixtiyoriy)"},
        },
        "required": ["product_name"],
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        product, err = _find_product(db, company_id, kwargs.get("product_name", ""))
        if err:
            return {"reply": err}

        changes = []
        new_name = (kwargs.get("new_name") or "").strip()
        if new_name:
            changes.append(f"nomi '{product.name}' → '{new_name}'")
            product.name = new_name

        if kwargs.get("new_sale_price") is not None:
            new_price = _sf(kwargs.get("new_sale_price"))
            if new_price <= 0:
                return {"reply": "❌ Yangi sotuv narxi musbat bo'lishi kerak."}
            changes.append(f"sotuv narxi {_fmt(_sf(product.sale_price))} → {_fmt(new_price)}")
            product.sale_price = Decimal(str(new_price))

        if kwargs.get("new_cost_price") is not None:
            new_cost = _sf(kwargs.get("new_cost_price"))
            if new_cost < 0:
                return {"reply": "❌ Tan narxi manfiy bo'lishi mumkin emas."}
            changes.append(f"tan narxi {_fmt(_sf(product.cost_price))} → {_fmt(new_cost)}")
            product.cost_price = Decimal(str(new_cost))

        if not changes:
            return {"reply": "❌ Hech qanday o'zgarish ko'rsatilmadi (yangi nom yoki narx kiriting)."}

        db.commit()

        return {
            "reply": f"✅ '{product.name}' mahsuloti yangilandi: " + "; ".join(changes) + ".",
            "action": {"type": "product_updated", "product_id": product.id},
        }


@AIToolRegistry.register
class CreateCustomerTool(AITool):
    name = "create_customer"
    description = "Yangi mijoz qo'shish (ism va, ixtiyoriy, telefon raqami bilan)."
    required_permission = "customers.create"
    risk_level = "MEDIUM"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Mijozning ismi"},
            "phone": {"type": "string", "description": "Telefon raqami (ixtiyoriy)"},
        },
        "required": ["name"],
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        name = (kwargs.get("name") or "").strip()
        if not name:
            return {"reply": "❌ Mijoz ismini kiriting."}

        phone = (kwargs.get("phone") or "").strip() or None

        customer = Customer(name=name, phone=phone, company_id=company_id)
        db.add(customer)
        db.commit()
        db.refresh(customer)

        return {
            "reply": f"✅ Yangi mijoz qo'shildi: {name}" + (f" ({phone})" if phone else "") + ".",
            "action": {"type": "customer_created", "customer_id": customer.id},
        }


@AIToolRegistry.register
class UpdateCustomerTool(AITool):
    name = "update_customer"
    description = "Mavjud mijozning ismi yoki telefon raqamini o'zgartirish (qarzga tegishli emas)."
    required_permission = "customers.edit"
    risk_level = "MEDIUM"
    parameters = {
        "type": "object",
        "properties": {
            "customer_name": {"type": "string", "description": "O'zgartiriladigan mijozning joriy ismi"},
            "new_name": {"type": "string", "description": "Yangi ism (ixtiyoriy)"},
            "new_phone": {"type": "string", "description": "Yangi telefon raqami (ixtiyoriy)"},
        },
        "required": ["customer_name"],
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        customer, err = _find_customer(db, company_id, kwargs.get("customer_name", ""))
        if err:
            return {"reply": err}

        changes = []
        new_name = (kwargs.get("new_name") or "").strip()
        if new_name:
            changes.append(f"ismi '{customer.name}' → '{new_name}'")
            customer.name = new_name

        new_phone = (kwargs.get("new_phone") or "").strip()
        if new_phone:
            changes.append(f"telefon raqami → {new_phone}")
            customer.phone = new_phone

        if not changes:
            return {"reply": "❌ Hech qanday o'zgarish ko'rsatilmadi (yangi ism yoki telefon kiriting)."}

        db.commit()

        return {
            "reply": f"✅ Mijoz ma'lumotlari yangilandi: " + "; ".join(changes) + ".",
            "action": {"type": "customer_updated", "customer_id": customer.id},
        }
