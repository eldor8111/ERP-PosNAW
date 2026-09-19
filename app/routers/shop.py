import hashlib
import hmac
import json
from typing import Optional, List
from decimal import Decimal
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Header  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from pydantic import BaseModel  # type: ignore

from app.database import get_db  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.product import Product  # type: ignore
from app.models.category import Category  # type: ignore
from app.models.warehouse import Warehouse, WarehouseType  # type: ignore
from app.models.inventory import StockLevel  # type: ignore
from app.models.order import Order, OrderStatus  # type: ignore
from app.models.branch import Branch  # type: ignore

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

    products_query = db.query(Product).filter(Product.company_id == company.id)
    if category_id:
        products_query = products_query.filter(Product.category_id == category_id)
    if q:
        products_query = products_query.filter(Product.name.ilike(f"%{q}%"))

    result = []
    for prod in products_query.all():
        available = int(stock_by_product.get(prod.id, 0))
        if available <= 0:
            continue
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


@router.get("/{company_id}/me")
def shop_me(
    company_id: int,
    u: Optional[str] = None,
    t: Optional[str] = None,
    db: Session = Depends(get_db),
    x_init_data: Optional[str] = Header(None, alias="X-Init-Data"),
):
    company, customer = _resolve_shop_context(db, company_id, x_init_data, u, t)
    return {
        "id": customer.id,
        "name": customer.name,
        "card_number": customer.card_number,
        "loyalty_points": float(customer.loyalty_points or 0),
    }


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

        available = db.query(StockLevel).filter(
            StockLevel.product_id == product.id,
            StockLevel.warehouse_id.in_(wh_ids),
        ).all()
        total_available = sum(float(s.quantity or 0) for s in available)
        if total_available < item.quantity:
            raise HTTPException(status_code=400, detail=f"{product.name}: yetarli qoldiq yo'q ({int(total_available)} ta bor)")

        unit_price = Decimal(str(product.sale_price or 0))
        total_amount = unit_price * item.quantity

        order = Order(
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
