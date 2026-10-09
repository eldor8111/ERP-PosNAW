"""Marketplace (mir-maza.uz) integratsiyasi: kategoriyalar sinxronizatsiyasi.

Manba URL .env dagi MARKETPLACE_CATEGORIES_URL orqali beriladi. Javob
[{id, name, parent_id}, ...] yoki {"results"|"data"|"categories": [...]}
ko'rinishida bo'lishi mumkin. Manba ishlamasa — oxirgi muvaffaqiyatli kesh
qaytariladi (marketplace vaqtincha o'chiq bo'lsa ham agentlar ishlayveradi).
"""
import logging
import threading
import time
from typing import Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: Dict[str, object] = {"items": [], "ts": 0.0}


def _normalize(raw) -> List[dict]:
    if isinstance(raw, dict):
        for key in ("results", "data", "categories", "items"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        return []
    out = []
    for c in raw:
        if not isinstance(c, dict) or c.get("id") is None:
            continue
        try:
            cid = int(c["id"])
        except (TypeError, ValueError):
            continue
        parent = c.get("parent_id", c.get("parent"))
        if isinstance(parent, dict):
            parent = parent.get("id")
        try:
            parent = int(parent) if parent not in (None, "", 0) else None
        except (TypeError, ValueError):
            parent = None
        name = c.get("name") or c.get("title") or c.get("name_uz") or f"#{cid}"
        out.append({"id": cid, "name": str(name)[:200], "parent_id": parent})
    return out


def fetch_categories(force: bool = False) -> List[dict]:
    """Kategoriyalar ro'yxati (kesh TTL — MARKETPLACE_CATEGORIES_TTL)."""
    now = time.time()
    with _lock:
        fresh = _cache["items"] and (now - float(_cache["ts"])) < settings.MARKETPLACE_CATEGORIES_TTL
        if fresh and not force:
            return list(_cache["items"])  # type: ignore[arg-type]

    url = settings.MARKETPLACE_CATEGORIES_URL
    if not url:
        return list(_cache["items"])  # type: ignore[arg-type]
    headers = {"Accept": "application/json"}
    if settings.MARKETPLACE_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.MARKETPLACE_API_TOKEN}"
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        items = _normalize(resp.json())
        if items:
            with _lock:
                _cache["items"], _cache["ts"] = items, now
            return list(items)
    except Exception as e:  # noqa: BLE001 — tashqi tizim xatosi agentlarni to'xtatmasin
        logger.warning("mir-maza kategoriyalarini olib bo'lmadi: %s", e)
    return list(_cache["items"])  # type: ignore[arg-type]


def category_ids() -> set:
    return {c["id"] for c in fetch_categories()}


def category_name_map() -> Dict[int, str]:
    return {c["id"]: c["name"] for c in fetch_categories()}


def normalize_phone(phone: str) -> str:
    return phone.strip().replace("+", "").replace(" ", "").replace("-", "")


def clamp_images(images: Optional[list], limit: int = 8) -> list:
    return [str(i)[:500] for i in (images or []) if i][:limit]


def push_product_to_mirmaza(p, category_name: str = "") -> bool:
    """Mir-maza API (v1/integration/products) orqali mahsulotni sinxronlash."""
    url = "https://mir-maza.uz/api/v1/integration/products"
    headers = {
        "Content-Type": "application/json",
        "X-Integration-Key": "ecode_secret_key_mirmaza_2026",
    }
    # Agar maxsus env o'zgaruvchi berilgan bo'lsa
    if settings.MARKETPLACE_API_TOKEN:
        headers["X-Integration-Key"] = settings.MARKETPLACE_API_TOKEN

    payload = {
        "externalId": f"ECODE-PROD-{p.id}",
        "barcode": p.barcode or "",
        "name": p.name,
        "description": p.description or "",
        "price": float(p.price),
        "stock": float(p.qty),
        "categoryExternalId": str(p.category_id),
        "categoryName": category_name,
        "image": p.images[0] if p.images else "",
        "isActive": p.status.value == "approved"
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=15.0)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error("Mir-maza ga mahsulot yuborishda xatolik: %s", e)
        return False

def pull_mirmaza_orders(db: Session, company_id: int):
    """Mir-Maza dan yangi buyurtmalarni tortib olish va Orders jadvaliga yozish."""
    url = "https://mir-maza.uz/api/v1/integration/orders?status=PENDING&limit=50"
    headers = {
        "Content-Type": "application/json",
        "X-Integration-Key": settings.MARKETPLACE_API_TOKEN or "ecode_secret_key_mirmaza_2026",
    }
    
    try:
        resp = httpx.get(url, headers=headers, timeout=15.0)
        if resp.status_code != 200:
            return
            
        data = resp.json()
        orders = data.get("orders", [])
        
        from app.models.order import Order, OrderStatus
        from app.models.customer import Customer
        from app.models.product import Product
        from app.models.marketplace import MarketplaceProduct
        
        for mo in orders:
            market_order_id = mo.get("marketOrderId")
            order_group_id = f"mirmaza-{market_order_id}"
            
            # Check if order already exists
            exists = db.query(Order).filter(Order.order_group_id == order_group_id).first()
            if exists:
                continue
                
            # Customer handling
            c_data = mo.get("customer", {})
            phone = normalize_phone(c_data.get("phone", ""))
            if not phone:
                continue
            
            customer = db.query(Customer).filter(Customer.phone == phone, Customer.company_id == company_id).first()
            if not customer:
                customer = Customer(
                    company_id=company_id,
                    name=c_data.get("name", "MirMaza Mijoz"),
                    phone=phone,
                    type="retail"
                )
                db.add(customer)
                db.flush()
                
            delivery = mo.get("deliveryAddress", {})
            address = delivery.get("address", "")
            
            # Branch id (first branch of company)
            from app.models.branch import Branch
            branch = db.query(Branch).filter(Branch.company_id == company_id).first()
            branch_id = branch.id if branch else 1
            
            for item in mo.get("items", []):
                ext_id = item.get("externalId", "")
                prod_id = None
                
                if ext_id.startswith("PROD-"):
                    try:
                        prod_id = int(ext_id.split("-")[1])
                    except:
                        pass
                elif ext_id.startswith("ECODE-PROD-"):
                    # Agent mahsuloti
                    try:
                        mp_id = int(ext_id.split("-")[2])
                        mp_item = db.query(MarketplaceProduct).filter(MarketplaceProduct.id == mp_id).first()
                        if mp_item:
                            # Tizimda to'liq ishlashi uchun Product jadvalidan vaqtincha ID topamiz yoki yaratamiz
                            prod = db.query(Product).filter(Product.barcode == mp_item.barcode, Product.company_id == company_id).first()
                            if not prod:
                                prod = Product(
                                    company_id=company_id,
                                    name=mp_item.name,
                                    sku=f"MP-{mp_id}",
                                    barcode=mp_item.barcode or f"MP-{mp_id}",
                                    sale_price=mp_item.price,
                                    category_id=mp_item.category_id
                                )
                                db.add(prod)
                                db.flush()
                            prod_id = prod.id
                    except:
                        pass
                
                if not prod_id:
                    # Noma'lum mahsulot bo'lsa o'tkazib yuboramiz
                    continue
                    
                order = Order(
                    order_group_id=order_group_id,
                    customer_id=customer.id,
                    branch_id=branch_id,
                    product_id=prod_id,
                    quantity=item.get("quantity", 1),
                    unit_price=item.get("price", 0),
                    total_amount=item.get("total", 0),
                    status=OrderStatus.pending,
                    delivery_type="delivery",
                    delivery_address=address,
                    notes=delivery.get("note", "")
                )
                db.add(order)
                
            db.commit()
            
            # Mir-maza'da statusini CONFIRMED ga o'zgartiramiz
            try:
                httpx.patch(
                    f"https://mir-maza.uz/api/v1/integration/orders/{market_order_id}/status",
                    json={"status": "CONFIRMED", "externalId": order_group_id},
                    headers=headers,
                    timeout=5.0
                )
            except Exception as e:
                logger.warning(f"Mirmaza status update xatoligi: {e}")
                
    except Exception as e:
        logger.error(f"Mirmaza orders pull xatoligi: {e}")

def push_courier_status_to_mirmaza(db: Session, order_group_id: str, courier_id: int, status: str):
    """Kuryer holatini Mir-Maza ga yuborish."""
    if not order_group_id or not order_group_id.startswith("mirmaza-"):
        return
        
    market_order_id = order_group_id.split("-")[1]
    url = f"https://mir-maza.uz/api/v1/integration/orders/{market_order_id}/courier"
    headers = {
        "Content-Type": "application/json",
        "X-Integration-Key": settings.MARKETPLACE_API_TOKEN or "ecode_secret_key_mirmaza_2026",
    }
    
    from app.models.courier import Courier
    from app.models.vehicle import Vehicle
    
    courier = db.query(Courier).filter(Courier.id == courier_id).first() if courier_id else None
    
    c_name = courier.name if courier else "Noma'lum"
    c_phone = courier.phone if courier else ""
    v_type = "CAR"
    v_num = ""
    
    if courier and courier.vehicle_id:
        v = db.query(Vehicle).filter(Vehicle.id == courier.vehicle_id).first()
        if v:
            v_type = v.vehicle_type.upper() if v.vehicle_type else "CAR"
            v_num = v.plate_number or ""
            
    # E-code statuslaridan Mir-Maza statuslariga o'girish
    m_status = "ASSIGNED"
    if status == "on_way":
        m_status = "ON_THE_WAY"
    elif status == "delivered":
        m_status = "DELIVERED"
    elif status == "cancelled":
        m_status = "CANCELLED"
    
    payload = {
        "courierName": c_name,
        "courierPhone": c_phone,
        "vehicle": v_type,
        "vehicleNumber": v_num,
        "deliveryStatus": m_status,
        "externalDeliveryId": f"ECODE-DELIVERY-{courier_id or 0}",
        "lat": 0.0,
        "lng": 0.0
    }
    
    try:
        httpx.patch(url, json=payload, headers=headers, timeout=5.0)
    except Exception as e:
        logger.warning(f"Mirmaza courier sync xatoligi: {e}")
