"""Marketplace (mir-maza.uz) integratsiyasi: kategoriyalar sinxronizatsiyasi.

Manba URL .env dagi MARKETPLACE_CATEGORIES_URL orqali beriladi. Javob
[{id, name, parent_id}, ...] yoki {"results"|"data"|"categories": [...]}
ko'rinishida bo'lishi mumkin. Manba ishlamasa — oxirgi muvaffaqiyatli kesh
qaytariladi (marketplace vaqtincha o'chiq bo'lsa ham agentlar ishlayveradi).
"""
import logging
import re
import threading
import time
from typing import Dict, List, Optional

import httpx

from app.config import settings
from sqlalchemy.orm import Session
logger = logging.getLogger(__name__)


def _integration_key() -> Optional[str]:
    """Mir-maza integratsiya kaliti (X-Integration-Key). .env da MARKETPLACE_API_TOKEN
    bo'sh bo'lsa None — kodda zaxira (fallback) kalit YO'Q, integratsiya o'chiq hisoblanadi."""
    key = (settings.MARKETPLACE_API_TOKEN or "").strip()
    return key or None


def _mirmaza_headers() -> Optional[dict]:
    """Mir-maza integratsiya so'rovlari uchun sarlavhalar. Kalit bo'sh bo'lsa None —
    chaqiruvchi log yozib to'xtaydi (so'rov yuborilmaydi)."""
    key = _integration_key()
    if not key:
        return None
    return {"Content-Type": "application/json", "X-Integration-Key": key}


# order_group_id: "mirmaza-<marketOrderId>" (eski) yoki "mirmaza-<marketOrderId>-c<company_id>" (T0.36)
_MIRMAZA_GROUP_RE = re.compile(r"^mirmaza-(.+?)(?:-c\d+)?$")

_lock = threading.Lock()
_cache: Dict[str, object] = {"items": [], "tree": [], "ts": 0.0}


def _flatten_tree(nodes: list, parent_id: Optional[int] = None, parent_name: Optional[str] = None, level: int = 0) -> List[dict]:
    flat = []
    for n in nodes:
        if not isinstance(n, dict) or n.get("id") is None:
            continue
        try:
            cid = int(n["id"])
        except (TypeError, ValueError):
            continue
        name = n.get("name") or n.get("title") or n.get("name_uz") or f"#{cid}"
        children = n.get("children", [])
        sort_order = n.get("sortOrder", n.get("sort_order", 0))
        try:
            sort_order = int(sort_order)
        except (TypeError, ValueError):
            sort_order = 0
        pid = n.get("parentId")
        effective_parent_id = int(pid) if pid not in (None, "", 0) else parent_id
        flat.append({
            "id": cid,
            "name": str(name)[:200],
            "parent_id": effective_parent_id,
            "parent_name": parent_name,
            "sort_order": sort_order,
            "icon": n.get("icon"),
            "image": n.get("image"),
            "level": level,
            "has_children": len(children) > 0,
            "children_count": len(children),
        })
        if children and isinstance(children, list):
            flat.extend(_flatten_tree(children, parent_id=cid, parent_name=str(name)[:200], level=level + 1))
    return flat


def _normalize(raw) -> List[dict]:
    if isinstance(raw, dict):
        for key in ("results", "data", "categories", "items"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        return []
    
    # Agar tree ko'rinishida kelgan bo'lsa (elementlarda children bo'lsa)
    if any(isinstance(c, dict) and "children" in c for c in raw):
        return _flatten_tree(raw)

    out = []
    for c in raw:
        if not isinstance(c, dict) or c.get("id") is None:
            continue
        try:
            cid = int(c["id"])
        except (TypeError, ValueError):
            continue
        parent = c.get("parentId", c.get("parent_id", c.get("parent")))
        if isinstance(parent, dict):
            parent = parent.get("id")
        try:
            parent = int(parent) if parent not in (None, "", 0) else None
        except (TypeError, ValueError):
            parent = None
        name = c.get("name") or c.get("title") or c.get("name_uz") or f"#{cid}"
        sort_order = c.get("sortOrder", c.get("sort_order", 0))
        try:
            sort_order = int(sort_order)
        except (TypeError, ValueError):
            sort_order = 0
        icon = c.get("icon")
        image = c.get("image")
        out.append({
            "id": cid,
            "name": str(name)[:200],
            "parent_id": parent,
            "parent_name": None,
            "sort_order": sort_order,
            "icon": icon,
            "image": image,
            "level": 0 if parent is None else 1,
            "has_children": False,
            "children_count": 0,
        })
    out.sort(key=lambda x: (x.get("sort_order", 0), x.get("id", 0)))
    return out


def fetch_categories(force: bool = False) -> List[dict]:
    """Kategoriyalar ro'yxati (kesh TTL — MARKETPLACE_CATEGORIES_TTL)."""
    now = time.time()
    with _lock:
        fresh = _cache["items"] and (now - float(_cache["ts"])) < settings.MARKETPLACE_CATEGORIES_TTL
        if fresh and not force:
            return list(_cache["items"])  # type: ignore[arg-type]

    headers = {"Accept": "application/json"}
    if settings.MARKETPLACE_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.MARKETPLACE_API_TOKEN}"

    # 1. Avval daraxt (tree) API'dan to'liq 500+ kategoriyalarni olishga harakat qilamiz
    tree_url = "https://mir-maza.uz/api/v1/categories/tree"
    try:
        resp = httpx.get(tree_url, headers=headers, timeout=12.0, follow_redirects=True)
        if resp.status_code == 200:
            tree_raw = resp.json()
            if isinstance(tree_raw, list) and len(tree_raw) > 0:
                items = _flatten_tree(tree_raw)
                if items:
                    with _lock:
                        _cache["items"], _cache["tree"], _cache["ts"] = items, tree_raw, now
                    return list(items)
    except Exception as e:
        logger.warning("mir-maza tree kategoriyalarini olib bo'lmadi: %s, standart URL sinab ko'riladi", e)

    # 2. Standart URL dan olish
    url = settings.MARKETPLACE_CATEGORIES_URL
    if not url:
        return list(_cache["items"])  # type: ignore[arg-type]
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        items = _normalize(resp.json())
        if items:
            with _lock:
                _cache["items"], _cache["ts"] = items, now
            return list(items)
    except Exception as e:  # noqa: BLE001
        logger.warning("mir-maza kategoriyalarini olib bo'lmadi: %s", e)
    return list(_cache["items"])  # type: ignore[arg-type]


def fetch_categories_tree(force: bool = False) -> List[dict]:
    """Ierarxik daraxt ko'rinishidagi kategoriyalar."""
    fetch_categories(force=force)
    with _lock:
        return list(_cache.get("tree", []))  # type: ignore[arg-type]


def category_ids() -> set:
    try:
        return {int(c["id"]) for c in fetch_categories() if isinstance(c, dict) and c.get("id") is not None}
    except Exception:
        return set()


def category_name_map() -> Dict[int, str]:
    try:
        return {
            int(c["id"]): str(c.get("name") or "")
            for c in fetch_categories()
            if isinstance(c, dict) and c.get("id") is not None
        }
    except Exception as ex:
        logger.warning("category_name_map olishda xatolik: %s", ex)
        return {}


def normalize_phone(phone: str) -> str:
    return phone.strip().replace("+", "").replace(" ", "").replace("-", "")


def clamp_images(images: Optional[list], limit: int = 8) -> list:
    return [str(i)[:500] for i in (images or []) if i][:limit]


def push_product_to_mirmaza(p, category_name: str = "") -> bool:
    """Mir-maza API (v1/integration/products) orqali mahsulotni sinxronlash."""
    url = "https://mir-maza.uz/api/v1/integration/products"
    headers = _mirmaza_headers()
    if not headers:
        logger.error("Mir-maza: MARKETPLACE_API_TOKEN sozlanmagan — mahsulot (id=%s) yuborilmadi", getattr(p, "id", None))
        return False

    base = settings.SERVER_URL.rstrip("/") if settings.SERVER_URL else "https://savdo.e-code.uz"
    full_images = []
    for img in (p.images or []):
        if img:
            full_images.append(img if str(img).startswith("http") else f"{base}{img}")

    payload = {
        "externalId": f"ECODE-PROD-{p.id}",
        "barcode": p.barcode or "",
        "name": p.name,
        "description": p.description or "",
        "price": float(p.price),
        "stock": float(p.qty),
        "categoryId": int(p.category_id) if p.category_id else None,
        "categoryExternalId": str(p.category_id) if p.category_id else "",
        "categoryName": category_name,
        "image": full_images[0] if full_images else "",
        "images": full_images,
        "isActive": p.status.value == "approved",
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=15.0)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error("Mir-maza ga mahsulot yuborishda xatolik: %s", e)
        return False

def notify_agent(
    db: Session,
    agent_id: int,
    company_id: int,
    title: str,
    body: str,
    notif_type: str = "general",
    data: Optional[dict] = None,
):
    """Agentga in-app bildirishnoma va agar FCM ulangan bo'lsa Push yuborish."""
    try:
        from app.models.marketplace import MarketplaceAgentNotification
        from app.models.mobile_device import MobileDevice
        from app.services.fcm_service import send_multicast_notification

        notif = MarketplaceAgentNotification(
            agent_id=agent_id,
            company_id=company_id,
            title=title,
            body=body,
            notif_type=notif_type,
            data=data or {},
        )
        db.add(notif)
        db.flush()

        devices = db.query(MobileDevice.fcm_token).filter(
            MobileDevice.user_id == agent_id,
            MobileDevice.fcm_token.isnot(None),
            MobileDevice.revoked_at.is_(None),
        ).all()
        tokens = [d[0] for d in devices if d[0]]
        if tokens:
            send_multicast_notification(tokens, title, body, {k: str(v) for k, v in (data or {}).items()})
    except Exception as e:
        logger.warning("notify_agent xatoligi: %s", e)


def _resolve_item_company(db: Session, item: dict) -> Optional[int]:
    """Buyurtma elementi qaysi korxonaga tegishli: externalId orqali.
    ECODE-PROD-<mp_id> → MarketplaceProduct.company_id, PROD-<id> → Product.company_id.
    Topilmasa yoki korxona faol emas / marketplace_agents yoqilmagan bo'lsa None."""
    from app.core.features import company_has_feature
    from app.models.company import Company
    from app.models.marketplace import MarketplaceProduct
    from app.models.product import Product

    ext_id = str(item.get("externalId") or "")
    company_id = None
    try:
        if ext_id.startswith("ECODE-PROD-"):
            mp_id = int(ext_id.split("-")[2])
            row = db.query(MarketplaceProduct.company_id).filter(MarketplaceProduct.id == mp_id).first()
            company_id = row[0] if row else None
        elif ext_id.startswith("PROD-"):
            prod_id = int(ext_id.split("-")[1])
            row = db.query(Product.company_id).filter(Product.id == prod_id).first()
            company_id = row[0] if row else None
    except (TypeError, ValueError, IndexError):
        return None
    if not company_id:
        return None
    active = db.query(Company.is_active).filter(Company.id == company_id).first()
    if not active or not active[0]:
        return None
    if not company_has_feature(db, company_id, "marketplace_agents"):
        return None
    return int(company_id)


def _resolve_mirmaza_branch_id(db: Session, company_id: int, customer) -> Optional[int]:
    """Mir-maza buyurtmasi filiali: mijoz filiali (shu korxonaniki bo'lsa) →
    Company.marketplace_default_branch_id → korxonaning birinchi faol filiali → None."""
    from app.models.branch import Branch
    from app.models.company import Company

    if customer is not None and customer.branch_id:
        # T1.15: mijoz filiali faqat faol bo'lsa (yopilgan filialga buyurtma tushmasin)
        row = db.query(Branch.id).filter(
            Branch.id == customer.branch_id, Branch.company_id == company_id,
            Branch.is_active == True,  # noqa: E712
        ).first()
        if row:
            return row[0]
    default_id = db.query(Company.marketplace_default_branch_id).filter(Company.id == company_id).scalar()
    if default_id:
        row = db.query(Branch.id).filter(
            Branch.id == default_id, Branch.company_id == company_id,
            Branch.is_active == True,  # noqa: E712  (T1.12)
        ).first()
        if row:
            return row[0]
    row = db.query(Branch.id).filter(
        Branch.company_id == company_id, Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id).first()
    return row[0] if row else None


def _import_mirmaza_group(db: Session, mo: dict, company_id: int, items: list, order_group_id: str) -> bool:
    """Bitta (Mir-maza buyurtma, korxona) juftligini Orders jadvaliga yozadi.
    Chaqiruvchi savepoint (db.begin_nested) ichida chaqiradi; xato — istisno bilan chiqadi.
    True — saqlandi (yoki avval saqlangan), False — o'tkazib yuborildi (ogohlantirish logda)."""
    from app.models.order import Order, OrderStatus
    from app.models.customer import Customer
    from app.models.product import Product
    from app.models.marketplace import (
        MarketplaceProduct, MarketplaceAgentTransaction, MarketplaceTransactionType,
    )

    market_order_id = mo.get("marketOrderId")

    # Dedup — korxona bo'yicha
    exists = db.query(Order.id).filter(
        Order.company_id == company_id, Order.order_group_id == order_group_id,
    ).first()
    if exists:
        return True

    c_data = mo.get("customer") or {}
    phone = normalize_phone(str(c_data.get("phone") or ""))
    if not phone:
        logger.warning("Mir-maza buyurtma #%s: mijoz telefoni yo'q — o'tkazib yuborildi", market_order_id)
        return False

    customer = db.query(Customer).filter(Customer.phone == phone, Customer.company_id == company_id).first()
    branch_id = _resolve_mirmaza_branch_id(db, company_id, customer)
    if not branch_id:
        logger.warning(
            "Mir-maza buyurtma #%s: korxona %s uchun filial topilmadi (asosiy filial sozlanmagan, faol filial yo'q) — o'tkazib yuborildi",
            market_order_id, company_id,
        )
        return False

    if not customer:
        customer = Customer(
            company_id=company_id,
            name=c_data.get("name") or "MirMaza Mijoz",
            phone=phone,
            customer_type="retail",
        )
        db.add(customer)
        db.flush()

    delivery = mo.get("deliveryAddress") or {}
    address = delivery.get("address", "")

    for item in items:
        ext_id = str(item.get("externalId") or "")
        prod_id = None

        if ext_id.startswith("PROD-"):
            pid = int(ext_id.split("-")[1])
            row = db.query(Product.id).filter(Product.id == pid, Product.company_id == company_id).first()
            prod_id = row[0] if row else None
        elif ext_id.startswith("ECODE-PROD-"):
            # Agent mahsuloti — egasi mp_item.company_id (chaqiruvchi korxona emas)
            mp_id = int(ext_id.split("-")[2])
            mp_item = db.query(MarketplaceProduct).filter(
                MarketplaceProduct.id == mp_id, MarketplaceProduct.company_id == company_id,
            ).first()
            if mp_item:
                # T0.18: webhook bilan umumiy idempotentlik — shu buyurtma+mahsulot uchun
                # income allaqachon yozilgan bo'lsa qoldiq/daromad qayta hisoblanmaydi
                already = db.query(MarketplaceAgentTransaction).filter(
                    MarketplaceAgentTransaction.order_id == market_order_id,
                    MarketplaceAgentTransaction.marketplace_product_id == mp_item.id,
                    MarketplaceAgentTransaction.transaction_type == MarketplaceTransactionType.income,
                ).first()
                if not already:
                    # Qoldiqni yangilash
                    qty_ordered = float(item.get("quantity", 1))
                    mp_item.qty = max(0.0, float(mp_item.qty or 0) - qty_ordered)

                    # Tranzaksiya qo'shish (agent daromadi)
                    item_total = float(item.get("total", 0))
                    tx = MarketplaceAgentTransaction(
                        agent_id=mp_item.agent_id,
                        company_id=mp_item.company_id,
                        order_id=market_order_id,
                        marketplace_product_id=mp_item.id,
                        transaction_type=MarketplaceTransactionType.income,
                        amount=item_total,
                        note=f"Mir-maza buyurtmasi #{market_order_id} ({mp_item.name})",
                    )
                    db.add(tx)

                    # Agentga bildirishnoma yuborish
                    notify_agent(
                        db=db,
                        agent_id=mp_item.agent_id,
                        company_id=mp_item.company_id,
                        title="Mahsulotingiz sotildi! 🎉",
                        body=f"Mir-maza marketplace'ida '{mp_item.name}' mahsulotingizdan {qty_ordered:.0f} dona sotildi. Summa: {item_total:,.0f} so'm.",
                        notif_type="order_sold",
                        data={"product_id": mp_item.id, "order_id": market_order_id, "amount": item_total},
                    )

                # Tizimda to'liq ishlashi uchun Product jadvalidan vaqtincha ID topamiz yoki yaratamiz
                prod = db.query(Product).filter(
                    Product.barcode == (mp_item.barcode or f"MP-{mp_id}"),
                    Product.company_id == mp_item.company_id,
                ).first()
                if not prod:
                    prod = Product(
                        company_id=mp_item.company_id,
                        name=mp_item.name,
                        sku=f"MP-{mp_id}",
                        barcode=mp_item.barcode or f"MP-{mp_id}",
                        sale_price=mp_item.price,
                        # mp_item.category_id — Mir-maza kategoriyasi, lokal categories.id emas (FK buziladi)
                        category_id=None,
                    )
                    db.add(prod)
                    db.flush()
                prod_id = prod.id

        if not prod_id:
            # Element hal qilinmadi — butun guruh savepoint bilan bekor bo'ladi, CONFIRMED qilinmaydi
            raise RuntimeError(f"element {ext_id!r} korxona {company_id} da topilmadi")

        order = Order(
            order_group_id=order_group_id,
            company_id=company_id,
            customer_id=customer.id,
            branch_id=branch_id,
            product_id=prod_id,
            quantity=item.get("quantity", 1),
            unit_price=item.get("price", 0),
            total_amount=item.get("total", 0),
            status=OrderStatus.pending,
            delivery_type="delivery",
            delivery_address=address,
            notes=delivery.get("note", ""),
        )
        db.add(order)
    return True


def pull_mirmaza_orders(db: Session, company_id: Optional[int] = None):
    """Mir-Maza dan yangi buyurtmalarni BIR marta (global) tortib, har bir elementni
    externalId orqali egasi korxonaga yo'naltirib Orders jadvaliga yozish.

    `company_id` — eskirgan, e'tiborga olinmaydi (so'rov global, egasi externalId dan).
    Har (buyurtma, korxona) juftligi alohida guruh (`mirmaza-<id>-c<company_id>`) va
    alohida savepoint — bittasidagi xato boshqalarini to'xtatmaydi. CONFIRMED faqat
    barcha elementlari saqlangan buyurtmalar uchun yuboriladi.
    """
    url = "https://mir-maza.uz/api/v1/integration/orders?status=PENDING&limit=50"
    headers = _mirmaza_headers()
    if not headers:
        logger.error("Mir-maza: MARKETPLACE_API_TOKEN sozlanmagan — buyurtmalar tortilmadi")
        return

    try:
        resp = httpx.get(url, headers=headers, timeout=15.0)
        if resp.status_code != 200:
            logger.warning("Mir-maza buyurtmalar so'rovi: HTTP %s", resp.status_code)
            return

        data = resp.json() or {}
        orders = data.get("orders", []) if isinstance(data, dict) else []

        skipped_orders = 0
        skipped_items = 0
        for mo in orders:
            market_order_id = mo.get("marketOrderId")
            try:
                # Elementlarni egasi korxona bo'yicha guruhlash
                by_company: Dict[int, list] = {}
                unresolved = 0
                for item in mo.get("items", []) or []:
                    cid = _resolve_item_company(db, item)
                    if cid is None:
                        unresolved += 1
                        logger.warning(
                            "Mir-maza buyurtma #%s: element %r egasi korxona topilmadi yoki modul yoqilmagan — o'tkazib yuborildi",
                            market_order_id, item.get("externalId"),
                        )
                        continue
                    by_company.setdefault(cid, []).append(item)
                skipped_items += unresolved

                all_saved = bool(by_company) and unresolved == 0
                for cid, items in by_company.items():
                    order_group_id = f"mirmaza-{market_order_id}-c{cid}"
                    if len(order_group_id) > 36:
                        logger.warning("Mir-maza buyurtma #%s: order_group_id juda uzun (%s) — o'tkazib yuborildi",
                                       market_order_id, order_group_id)
                        all_saved = False
                        continue
                    try:
                        with db.begin_nested():
                            ok = _import_mirmaza_group(db, mo, cid, items, order_group_id)
                        if not ok:
                            all_saved = False
                    except Exception:
                        logger.exception("Mir-maza buyurtma #%s (korxona %s) saqlanmadi", market_order_id, cid)
                        all_saved = False

                db.commit()
            except Exception:
                logger.exception("Mir-maza buyurtma #%s qayta ishlanmadi", market_order_id)
                db.rollback()
                all_saved = False

            if not all_saved:
                skipped_orders += 1
                continue

            # Mir-maza'da statusini CONFIRMED ga o'zgartiramiz (korxona qo'shimchasisiz externalId)
            try:
                presp = httpx.patch(
                    f"https://mir-maza.uz/api/v1/integration/orders/{market_order_id}/status",
                    json={"status": "CONFIRMED", "externalId": f"mirmaza-{market_order_id}"},
                    headers=headers,
                    timeout=5.0,
                )
                if presp.status_code >= 400:
                    logger.warning("Mir-maza buyurtma #%s CONFIRMED yangilash: HTTP %s", market_order_id, presp.status_code)
            except Exception as e:
                logger.warning("Mirmaza status update xatoligi (#%s): %s", market_order_id, e)

        if skipped_orders or skipped_items:
            logger.warning(
                "Mir-maza: %s ta buyurtma CONFIRMED qilinmadi, %s ta element o'tkazib yuborildi (PENDING navbatda qoladi, limit=50)",
                skipped_orders, skipped_items,
            )

    except Exception as e:
        logger.error(f"Mirmaza orders pull xatoligi: {e}")
        try:
            db.rollback()
        except Exception:
            pass

def push_courier_status_to_mirmaza(db: Session, order_group_id: str, courier_id: int, status: str):
    """Kuryer holatini Mir-Maza ga yuborish."""
    if not order_group_id or not order_group_id.startswith("mirmaza-"):
        return
        
    m = _MIRMAZA_GROUP_RE.match(order_group_id)
    if not m:
        return
    market_order_id = m.group(1)
    url = f"https://mir-maza.uz/api/v1/integration/orders/{market_order_id}/courier"
    headers = _mirmaza_headers()
    if not headers:
        logger.error("Mir-maza: MARKETPLACE_API_TOKEN sozlanmagan — kuryer holati yuborilmadi (%s)", order_group_id)
        return
    # Eslatma: bitta Mir-maza buyurtmasi bir nechta korxonaga bo'lingan bo'lsa
    # (..-c<A>, ..-c<B>), har guruh uchun alohida kuryer holati yuboriladi —
    # Mir-maza tomonida bitta buyurtmaga bir nechta holat boradi (qabul qilingan kamchilik).

    # E-code statuslaridan Mir-Maza statuslariga o'girish. Xaritada bo'lmagan holat
    # (confirmed/preparing va h.k.) uchun hech narsa yuborilmaydi.
    _status_map = {
        "assigned": "ASSIGNED",
        "on_way": "ON_THE_WAY",
        "delivered": "DELIVERED",
        "cancelled": "CANCELLED",
    }
    m_status = _status_map.get(status)
    if not m_status:
        return

    from app.models.courier import Courier
    from app.models.vehicle import Vehicle

    courier = db.query(Courier).filter(Courier.id == courier_id).first() if courier_id else None

    c_name = courier.name if courier else "Noma'lum"
    c_phone = courier.phone if courier else ""
    # Mir-maza `vehicle` maydoni enum (CAR va h.k.); Vehicle da transport turi yo'q —
    # fuel_type/model tur sifatida yuborilmaydi, doimiy "CAR".
    v_type = "CAR"
    v_num = ""

    if courier and courier.vehicle_id:
        v = db.query(Vehicle).filter(Vehicle.id == courier.vehicle_id).first()
        if v:
            v_num = v.plate_number or ""

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
