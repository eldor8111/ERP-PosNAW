import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from decimal import Decimal
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Header  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from pydantic import BaseModel  # type: ignore

from app.database import get_db  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.product import Product, ProductStatus  # type: ignore
from app.models.category import Category  # type: ignore
from app.models.warehouse import Warehouse, WarehouseType  # type: ignore
from app.models.inventory import StockLevel  # type: ignore
from app.models.order import Order, OrderStatus  # type: ignore
from app.models.branch import Branch  # type: ignore
from app.models.sale import Sale, PaymentType  # type: ignore

router = APIRouter(prefix="/shop", tags=["shop"])


def _verify_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """Telegram WebApp initData'ni HMAC-SHA256 orqali tekshiradi."""
    try:
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if calculated_hash != received_hash:
            return None

        user_raw = parsed.get("user")
        if not user_raw:
            return None
        return json.loads(user_raw)
    except Exception:
        return None


def _generate_card_number_for_shop(db: Session, company_id: int) -> str:
    """13 xonali unique loyallik karta raqami (telegram.py bilan bir xil mantiq)."""
    import random
    existing = {
        r[0] for r in db.query(Customer.card_number).filter(
            Customer.company_id == company_id,
            Customer.card_number.isnot(None),
        ).all()
    }
    while True:
        num = "2" + "".join(str(random.randint(0, 9)) for _ in range(12))
        if num not in existing:
            return num


def _shop_warehouse_ids(db: Session, company_id: int) -> List[int]:
    """Mijozlarga ko'rsatiladigan omborlar.

    Amaliyotda WarehouseType.shop deyarli ishlatilmaydi — foydalanuvchilar
    ombor turini "main" holida qoldirib, faqat nomini "Do'kon" deb qo'yishadi.
    Shuning uchun avval type=shop, topilmasa nomi "do'kon"/"dokon"/"shop"
    so'zini o'z ichiga olgan faol omborlarni ishlatamiz.
    """
    typed = db.query(Warehouse).filter(
        Warehouse.company_id == company_id,
        Warehouse.type == WarehouseType.shop,
        Warehouse.is_active == True,  # noqa: E712
    ).all()
    if typed:
        return [w.id for w in typed]

    all_active = db.query(Warehouse).filter(
        Warehouse.company_id == company_id,
        Warehouse.is_active == True,  # noqa: E712
    ).all()

    def _looks_like_shop(name: str) -> bool:
        n = (name or "").lower()
        for ch in ("'", "ʼ", "’", "`"):
            n = n.replace(ch, "")
        return "dokon" in n or "shop" in n or "магазин" in n

    return [w.id for w in all_active if _looks_like_shop(w.name)]


def _verify_shop_token(chat_id: str, token: str, bot_token: str) -> bool:
    """Bot yaratgan shaxsiy havola imzosini tekshiradi (initData'ga muqobil)."""
    expected = hmac.new(bot_token.encode(), chat_id.encode(), hashlib.sha256).hexdigest()[:24]
    return hmac.compare_digest(expected, token or "")


def _resolve_shop_context(
    db: Session,
    company_id: int,
    x_init_data: Optional[str],
    u: Optional[str] = None,
    t: Optional[str] = None,
):
    """company va customer'ni initData yoki shaxsiy havola tokeni orqali aniqlaydi."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")
    if not company.tg_bot_token:
        raise HTTPException(status_code=404, detail="Bot ulanmagan")

    chat_id = None

    if x_init_data:
        tg_user = _verify_init_data(x_init_data, company.tg_bot_token)
        if tg_user:
            chat_id = str(tg_user.get("id"))

    if not chat_id and u and t:
        if _verify_shop_token(str(u), t, company.tg_bot_token):
            chat_id = str(u)

    if not chat_id:
        raise HTTPException(status_code=401, detail="Autentifikatsiya xato")

    customer = db.query(Customer).filter(
        Customer.company_id == company.id,
        Customer.tg_chat_id == chat_id,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi. /start bosing.")

    return company, customer


class ProductOut(BaseModel):
    id: int
    name: str
    price: float
    available: int
    category: Optional[str] = None
    image_url: Optional[str] = None


class CartItemIn(BaseModel):
    product_id: int
    quantity: int


class OrderIn(BaseModel):
    items: List[CartItemIn]
    payment_type: Optional[str] = "cash"
    notes: Optional[str] = None


@router.get("/{company_id}/info")
def shop_info(company_id: int, db: Session = Depends(get_db)):
    """Do'kon nomi va ma'lumotlarini ochiq (auth'siz) qaytaradi — UI sarlavhasi uchun."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Do'kon topilmadi")
    return {"id": company.id, "name": company.name}


@router.get("/{company_id}/products", response_model=List[ProductOut])
def shop_products(
    company_id: int,
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    u: Optional[str] = None,
    t: Optional[str] = None,
    db: Session = Depends(get_db),
    x_init_data: Optional[str] = Header(None, alias="X-Init-Data"),
):
    company, customer = _resolve_shop_context(db, company_id, x_init_data, u, t)

    wh_ids = _shop_warehouse_ids(db, company.id)
    if not wh_ids:
        return []

    stock_query = db.query(StockLevel).filter(StockLevel.warehouse_id.in_(wh_ids))
    stock_by_product = {}
    for stock in stock_query.all():
        stock_by_product[stock.product_id] = stock_by_product.get(stock.product_id, 0) + float(stock.quantity or 0)

    products_query = db.query(Product).filter(
        Product.company_id == company.id,
        Product.is_deleted == False,  # noqa: E712
        Product.status == ProductStatus.active,
    )
    if category_id:
        products_query = products_query.filter(Product.category_id == category_id)
    if q:
        products_query = products_query.filter(Product.name.ilike(f"%{q}%"))

    result = []
    for prod in products_query.all():
        available = max(0, int(stock_by_product.get(prod.id, 0)))
        cat = db.query(Category).filter(Category.id == prod.category_id).first() if prod.category_id else None
        result.append(ProductOut(
            id=prod.id,
            name=prod.name,
            price=float(prod.sale_price or 0),
            available=available,
            category=cat.name if cat else None,
            image_url=getattr(prod, "image_url", None),
        ))

    return result


@router.get("/{company_id}/categories")
def shop_categories(
    company_id: int,
    u: Optional[str] = None,
    t: Optional[str] = None,
    db: Session = Depends(get_db),
    x_init_data: Optional[str] = Header(None, alias="X-Init-Data"),
):
    company, customer = _resolve_shop_context(db, company_id, x_init_data, u, t)
    cats = db.query(Category).filter(Category.company_id == company.id).all()
    return [{"id": c.id, "name": c.name} for c in cats]


@router.get("/{company_id}/my-orders")
def shop_my_orders(
    company_id: int,
    u: Optional[str] = None,
    t: Optional[str] = None,
    db: Session = Depends(get_db),
    x_init_data: Optional[str] = Header(None, alias="X-Init-Data"),
):
    company, customer = _resolve_shop_context(db, company_id, x_init_data, u, t)

    orders = db.query(Order).filter(
        Order.customer_id == customer.id,
    ).order_by(Order.created_at.desc()).limit(50).all()

    result = []
    for order in orders:
        product = db.query(Product).filter(Product.id == order.product_id).first()
        result.append({
            "id": order.id,
            "product_name": product.name if product else "—",
            "quantity": order.quantity,
            "unit_price": float(order.unit_price),
            "total_amount": float(order.total_amount),
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
        })

    return result


@router.get("/{company_id}/me")
def shop_me(
    company_id: int,
    u: Optional[str] = None,
    t: Optional[str] = None,
    db: Session = Depends(get_db),
    x_init_data: Optional[str] = Header(None, alias="X-Init-Data"),
):
    company, customer = _resolve_shop_context(db, company_id, x_init_data, u, t)

    if not customer.card_number:
        customer.card_number = _generate_card_number_for_shop(db, company.id)
        db.commit()
        db.refresh(customer)

    today = datetime.now(timezone.utc).date()
    debt_sales = (
        db.query(Sale)
        .filter(
            Sale.customer_id == customer.id,
            Sale.payment_type == PaymentType.debt,
            Sale.status == "completed",
            Sale.debt_due_date.isnot(None),
        )
        .order_by(Sale.debt_due_date)
        .limit(10)
        .all()
    )
    debt_schedule = []
    for s in debt_sales:
        delta = (s.debt_due_date - today).days
        debt_schedule.append({
            "due_date": s.debt_due_date.isoformat(),
            "days_left": delta,
            "amount": float(s.total_amount or 0),
        })

    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "card_number": customer.card_number,
        "loyalty_points": float(customer.loyalty_points or 0),
        "tier": customer.tier,
        "debt_balance": float(customer.debt_balance or 0),
        "debt_limit": float(customer.debt_limit or 0),
        "bonus_balance": float(customer.bonus_balance or 0),
        "discount_percent": float(customer.discount_percent or 0),
        "cashback_percent": float(customer.cashback_percent or 0),
        "debt_schedule": debt_schedule,
    }


@router.get("/{company_id}/purchases")
def shop_purchases(
    company_id: int,
    u: Optional[str] = None,
    t: Optional[str] = None,
    db: Session = Depends(get_db),
    x_init_data: Optional[str] = Header(None, alias="X-Init-Data"),
):
    company, customer = _resolve_shop_context(db, company_id, x_init_data, u, t)

    sales = (
        db.query(Sale)
        .filter(Sale.customer_id == customer.id)
        .order_by(Sale.created_at.desc())
        .limit(30)
        .all()
    )
    result = []
    for s in sales:
        result.append({
            "id": s.id,
            "total_amount": float(s.total_amount or 0),
            "payment_type": s.payment_type.value if hasattr(s.payment_type, "value") else str(s.payment_type),
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "debt_due_date": s.debt_due_date.isoformat() if getattr(s, "debt_due_date", None) else None,
        })
    return result


@router.post("/{company_id}/order")
def shop_create_order(
    company_id: int,
    data: OrderIn,
    u: Optional[str] = None,
    t: Optional[str] = None,
    db: Session = Depends(get_db),
    x_init_data: Optional[str] = Header(None, alias="X-Init-Data"),
):
    company, customer = _resolve_shop_context(db, company_id, x_init_data, u, t)

    if not data.items:
        raise HTTPException(status_code=400, detail="Savat bo'sh")

    wh_ids = _shop_warehouse_ids(db, company.id)
    if not wh_ids:
        raise HTTPException(status_code=400, detail="Do'konda sotuvga qo'yilgan ombor topilmadi")
    shop_warehouses = db.query(Warehouse).filter(Warehouse.id.in_(wh_ids)).all()

    default_branch_id = customer.branch_id
    if not default_branch_id:
        wh_with_branch = next((w for w in shop_warehouses if w.branch_id), None)
        default_branch_id = wh_with_branch.branch_id if wh_with_branch else None
    if not default_branch_id:
        first_branch = db.query(Branch).filter(Branch.company_id == company.id).first()
        default_branch_id = first_branch.id if first_branch else None
    if not default_branch_id:
        raise HTTPException(status_code=400, detail="Kompaniyada filial topilmadi")

    # Bitta checkout'dagi barcha mahsulotlarni bitta buyurtma sifatida
    # guruhlash uchun — CRM'da alohida qatorlarga bo'linib ketmasin.
    order_group_id = str(uuid.uuid4())

    created_orders = []
    for item in data.items:
        if item.quantity <= 0:
            continue
        product = db.query(Product).filter(
            Product.id == item.product_id,
            Product.company_id == company.id,
        ).first()
        if not product:
            continue

        # Buyurtma — so'rov: qoldiq yetarli bo'lmasa ham qabul qilinadi,
        # do'kon xodimi keyinroq tasdiqlash/rad etish orqali hal qiladi.
        unit_price = Decimal(str(product.sale_price or 0))
        total_amount = unit_price * item.quantity

        order = Order(
            order_group_id=order_group_id,
            customer_id=customer.id,
            branch_id=default_branch_id,
            product_id=product.id,
            quantity=item.quantity,
            unit_price=unit_price,
            total_amount=total_amount,
            status=OrderStatus.pending,
            payment_type=data.payment_type,
            notes=data.notes,
        )
        db.add(order)
        created_orders.append(order)

    if not created_orders:
        raise HTTPException(status_code=400, detail="Savatdagi mahsulotlar topilmadi")

    try:
        db.commit()
    except Exception as ex:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Buyurtmani saqlashda xatolik: {ex}")

    for order in created_orders:
        db.refresh(order)

    return {
        "message": "Buyurtma qabul qilindi",
        "orders_count": len(created_orders),
        "order_ids": [o.id for o in created_orders],
    }
