"""
Dostavchik (kuryer) boti: webhook + kuryer Mini App API.

Oqim:
  1. CRM'da kuryer qo'shiladi (ism + telefon) — couriers.py
  2. Kuryer botga /start yozadi -> telefon ulashish so'raladi
  3. Kontakt kelganda telefon bo'yicha Courier topiladi, tg_chat_id bog'lanadi
  4. Reply-klaviaturada "📦 Buyurtmalarim" web_app tugmasi paydo bo'ladi
  5. Mini App auth: mijoz do'konidagi kabi HMAC imzoli u/t query paramlar
     (courier_bot_token kalit sifatida) — initData'ga muqobil.
"""
import hashlib
import hmac
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.models.courier import Courier
from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.product import Product

router = APIRouter(prefix="/courier-bot", tags=["courier-bot"])

COURIER_APP_BASE_URL = "https://savdo.e-code.uz/courier-app"


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _send_message(token: str, chat_id: str, text: str, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception as e:
        print("Courier bot xato:", e)


def _norm_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _courier_token(chat_id: str, bot_token: str) -> str:
    """Kuryerga xos shaxsiy havola imzosi (initData'ga muqobil)."""
    return hmac.new(bot_token.encode(), chat_id.encode(), hashlib.sha256).hexdigest()[:24]


def _verify_courier_token(chat_id: str, token: str, bot_token: str) -> bool:
    return hmac.compare_digest(_courier_token(chat_id, bot_token), token or "")


def _build_courier_keyboard(company: Company, chat_id: str) -> dict:
    btn = {"text": "📦 Buyurtmalarim"}
    if company and company.courier_bot_token:
        t = _courier_token(str(chat_id), company.courier_bot_token)
        url = f"{COURIER_APP_BASE_URL}?c={company.id}&u={chat_id}&t={t}"
        btn = {"text": "📦 Buyurtmalarim", "web_app": {"url": url}}
    return {"keyboard": [[btn]], "resize_keyboard": True}


def _build_phone_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "📞 Telefon raqamni yuborish", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def _find_courier_by_chat(db: Session, company: Company, chat_id: str) -> Optional[Courier]:
    return db.query(Courier).filter(
        Courier.company_id == company.id,
        Courier.tg_chat_id == str(chat_id),
        Courier.is_active == True,  # noqa: E712
    ).first()


# ── Webhook ──────────────────────────────────────────────────────────────────

@router.post("/webhook/{token}")
async def courier_bot_webhook(
    token: str,
    request: Request,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.courier_bot_token == token).first()
    if not company:
        return {"ok": True}

    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = str(message.get("chat", {}).get("id", ""))
    if not chat_id:
        return {"ok": True}

    contact = message.get("contact")
    text = (message.get("text") or "").strip()

    courier = _find_courier_by_chat(db, company, chat_id)

    # ── Kontakt: telefon orqali ro'yxatdan o'tish ────────────────────────
    if contact:
        phone_norm = _norm_phone(contact.get("phone_number", ""))
        if not phone_norm:
            bg.add_task(_send_message, token, chat_id,
                        "❌ Telefon raqamni aniqlab bo'lmadi. Qayta urinib ko'ring.",
                        _build_phone_keyboard())
            return {"ok": True}

        # Kompaniyaning faol kuryerlari ichidan raqami mos kelganini topamiz
        # (formatlar farq qilishi mumkin — faqat raqamlar solishtiriladi).
        match = None
        for c in db.query(Courier).filter(
            Courier.company_id == company.id,
            Courier.is_active == True,  # noqa: E712
        ).all():
            cn = _norm_phone(c.phone)
            if cn and (cn == phone_norm or cn[-9:] == phone_norm[-9:]):
                match = c
                break

        if not match:
            bg.add_task(_send_message, token, chat_id,
                        "❌ Bu raqam dostavchiklar ro'yxatida topilmadi.\n"
                        "Administrator sizni CRM'da ro'yxatga olganiga ishonch hosil qiling.")
            return {"ok": True}

        match.tg_chat_id = chat_id
        db.commit()
        bg.add_task(_send_message, token, chat_id,
                    f"✅ Xush kelibsiz, <b>{match.name}</b>!\n\n"
                    "Endi sizga biriktirilgan buyurtmalar shu botga keladi.\n"
                    "📦 <b>Buyurtmalarim</b> tugmasi orqali buyurtmalarni ko'ring va boshqaring.",
                    _build_courier_keyboard(company, chat_id))
        return {"ok": True}

    # ── /start va boshqa matnlar ─────────────────────────────────────────
    if courier:
        bg.add_task(_send_message, token, chat_id,
                    f"🛵 Salom, <b>{courier.name}</b>!\n"
                    "📦 <b>Buyurtmalarim</b> tugmasi orqali buyurtmalaringizni ko'ring.",
                    _build_courier_keyboard(company, chat_id))
    else:
        bg.add_task(_send_message, token, chat_id,
                    f"🛵 <b>{company.name}</b> — dostavchik boti.\n\n"
                    "Ro'yxatdan o'tish uchun telefon raqamingizni yuboring "
                    "(CRM'da kiritilgan raqam bilan bir xil bo'lishi kerak):",
                    _build_phone_keyboard())
    return {"ok": True}


# ── Kuryer Mini App API ──────────────────────────────────────────────────────

def _resolve_courier_context(db: Session, company_id: int, u: Optional[str], t: Optional[str]):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")
    if not company.courier_bot_token:
        raise HTTPException(status_code=404, detail="Dostavchik boti ulanmagan")
    if not (u and t and _verify_courier_token(str(u), t, company.courier_bot_token)):
        raise HTTPException(status_code=401, detail="Autentifikatsiya xato")
    courier = _find_courier_by_chat(db, company, str(u))
    if not courier:
        raise HTTPException(status_code=403, detail="Dostavchik topilmadi yoki nofaol")
    return company, courier


@router.get("/{company_id}/my-orders")
def courier_my_orders(
    company_id: int,
    u: Optional[str] = None,
    t: Optional[str] = None,
    db: Session = Depends(get_db),
):
    company, courier = _resolve_courier_context(db, company_id, u, t)

    orders = db.query(Order).filter(
        Order.courier_id == courier.id,
        Order.status.in_([OrderStatus.assigned, OrderStatus.on_way]),
    ).order_by(Order.assigned_at.desc().nullslast(), Order.created_at.desc()).all()

    customer_ids = {o.customer_id for o in orders}
    product_ids = {o.product_id for o in orders}
    customers_by_id = {}
    if customer_ids:
        for c in db.query(Customer.id, Customer.name, Customer.phone).filter(Customer.id.in_(customer_ids)).all():
            customers_by_id[c.id] = c
    products_by_id = {}
    if product_ids:
        for p in db.query(Product.id, Product.name).filter(Product.id.in_(product_ids)).all():
            products_by_id[p.id] = p.name

    groups: dict = {}
    for o in orders:
        key = o.order_group_id or f"single-{o.id}"
        if key not in groups:
            cust = customers_by_id.get(o.customer_id)
            groups[key] = {
                "group_id": key,
                "status": o.status.value if hasattr(o.status, "value") else str(o.status),
                "customer_name": cust.name if cust else "—",
                "customer_phone": (getattr(o, "contact_phone", None) or (cust.phone if cust else None)),
                "delivery_address": getattr(o, "delivery_address", None),
                "delivery_lat": float(o.delivery_lat) if getattr(o, "delivery_lat", None) else None,
                "delivery_lng": float(o.delivery_lng) if getattr(o, "delivery_lng", None) else None,
                "payment_type": o.payment_type,
                "notes": o.notes,
                "delivery_fee": float(getattr(o, "delivery_fee", 0) or 0),
                "total_amount": 0.0,
                "assigned_at": o.assigned_at.isoformat() if getattr(o, "assigned_at", None) else None,
                "items": [],
            }
        groups[key]["items"].append({
            "product_name": products_by_id.get(o.product_id, "—"),
            "quantity": o.quantity,
            "total_amount": float(o.total_amount),
        })
        groups[key]["total_amount"] += float(o.total_amount)

    # Bugungi statistika
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    delivered_today = db.query(Order.order_group_id).filter(
        Order.courier_id == courier.id,
        Order.status == OrderStatus.delivered,
        Order.delivered_at >= today_start,
    ).distinct().count()

    # Ulgurji sotuv yetkazmalari (Logistika marshrutidan biriktirilgan)
    from app.models.sale_delivery import SaleDelivery, SaleDeliveryStatus
    from app.models.sale import SaleItem
    from app.services import sale_delivery_service as sd_service
    deliveries = db.query(SaleDelivery).filter(
        SaleDelivery.courier_id == courier.id,
        SaleDelivery.status.in_([SaleDeliveryStatus.assigned, SaleDeliveryStatus.on_way]),
    ).order_by(SaleDelivery.assigned_at.desc().nullslast()).all()
    for d in deliveries:
        sale = d.sale
        cust = db.query(Customer.name, Customer.phone).filter(Customer.id == sale.customer_id).first() if sale.customer_id else None
        items = db.query(SaleItem, Product.name).join(Product, Product.id == SaleItem.product_id).filter(SaleItem.sale_id == sale.id).all()
        groups[f"sale-{sale.id}"] = {
            "group_id": f"sale-{sale.id}",
            "source": "sale",
            "sale_number": sale.number,
            "status": d.status.value,
            "customer_name": cust.name if cust else "—",
            "customer_phone": d.contact_phone or (cust.phone if cust else None),
            "delivery_address": d.address,
            "delivery_lat": float(d.lat) if d.lat is not None else None,
            "delivery_lng": float(d.lng) if d.lng is not None else None,
            "payment_type": sale.payment_type.value if hasattr(sale.payment_type, "value") else str(sale.payment_type),
            "notes": d.note,
            "delivery_fee": float(d.delivery_fee or 0),
            "total_amount": float(sale.total_amount or 0),
            # Tovar puli sotuvda hisoblangan — kuryer faqat shuni yig'adi
            "collect_amount": sd_service.collect_amount(d),
            "assigned_at": d.assigned_at.isoformat() if d.assigned_at else None,
            "items": [
                {"product_name": name, "quantity": float(si.quantity), "total_amount": float(si.subtotal or 0)}
                for si, name in items
            ],
        }
    delivered_today += db.query(SaleDelivery.id).filter(
        SaleDelivery.courier_id == courier.id,
        SaleDelivery.status == SaleDeliveryStatus.delivered,
        SaleDelivery.delivered_at >= today_start,
    ).count()

    return {
        "courier": {"id": courier.id, "name": courier.name},
        "delivered_today": delivered_today,
        "orders": list(groups.values()),
    }


class CourierStatusIn(BaseModel):
    status: str  # 'on_way' | 'delivered'


@router.put("/{company_id}/orders/{group_id}/status")
def courier_update_order_status(
    company_id: int,
    group_id: str,
    data: CourierStatusIn,
    bg: BackgroundTasks,
    u: Optional[str] = None,
    t: Optional[str] = None,
    db: Session = Depends(get_db),
):
    company, courier = _resolve_courier_context(db, company_id, u, t)

    if data.status not in ("on_way", "delivered"):
        raise HTTPException(status_code=400, detail="Faqat 'on_way' yoki 'delivered' mumkin")
    new_status = OrderStatus.on_way if data.status == "on_way" else OrderStatus.delivered

    if group_id.startswith("sale-"):
        return _courier_update_sale_delivery(db, company, courier, group_id, data.status)

    if group_id.startswith("single-"):
        orders = db.query(Order).filter(
            Order.id == int(group_id.split("-", 1)[1]),
            Order.courier_id == courier.id,
        ).all()
    else:
        orders = db.query(Order).filter(
            Order.order_group_id == group_id,
            Order.courier_id == courier.id,
        ).all()

    if not orders:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi yoki sizga biriktirilmagan")
    if any(o.status in (OrderStatus.delivered, OrderStatus.cancelled) for o in orders):
        raise HTTPException(status_code=400, detail="Buyurtma allaqachon yakunlangan")

    now = datetime.now(timezone.utc)
    for o in orders:
        o.status = new_status
        if new_status == OrderStatus.on_way:
            o.on_way_at = now
        else:
            o.delivered_at = now
    db.commit()

    # Mijozga xabar (mijoz boti orqali) — orders.py dagi tayyor helper
    from app.routers.orders import _notify_customer_status
    bg.add_task(_notify_customer_status, db, orders, new_status)

    # Yetkazilganda (sozlama yoqiq bo'lsa) avtomatik Sale yaratish
    if new_status == OrderStatus.delivered:
        from app.services.order_to_sale import maybe_create_sale_for_delivered_group
        bg.add_task(maybe_create_sale_for_delivered_group, db, orders)

    return {"message": "Status yangilandi", "status": data.status}


def _courier_update_sale_delivery(db: Session, company, courier, group_id: str, status: str) -> dict:
    """Ulgurji sotuv yetkazmasi — "yetkazildi" yangi sotuv yaratmaydi,
    faqat yetkazish haqi moliyaga (bir marta) yoziladi."""
    from app.models.sale_delivery import SaleDelivery, SaleDeliveryStatus
    from app.services import sale_delivery_service as sd_service
    try:
        sale_id = int(group_id[len("sale-"):])
    except ValueError:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    d = db.query(SaleDelivery).filter(
        SaleDelivery.sale_id == sale_id,
        SaleDelivery.company_id == company.id,
        SaleDelivery.courier_id == courier.id,
    ).with_for_update().first()
    if not d:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi yoki sizga biriktirilmagan")
    if d.status in sd_service.FINAL:
        raise HTTPException(status_code=400, detail="Buyurtma allaqachon yakunlangan")
    if status == "on_way":
        sd_service.set_status(d, SaleDeliveryStatus.on_way)
    else:
        sd_service.set_status(d, SaleDeliveryStatus.delivered)
        acting = sd_service.acting_user(db, company.id)
        if acting:
            sd_service.record_fee_once(db, d, acting)
    db.commit()
    return {"message": "Status yangilandi", "status": status}
