"""Restoran cheki mantig'i (R3.1-R3.4, R2.3): ochish, qator qo'shish, oshxonaga yuborish, pre-chek, bekor qilish,
chegirma, xizmat haqi, stolni ko'chirish va birlashtirish.

Ruxsatlar (`restaurant` bo'limi): rol sukutlari + `user.permissions["restaurant"]` yoki maxsus rol ruxsatlari.
Ruxsati yetmagan amal boshqa xodimning (menejer) PIN tasdig'i bilan bajariladi: `approval = {user_id, pin}`.
To'lov (status 'paid', Sale yaratish) R5 da.
"""
import threading
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.category import Category
from app.models.product import Product, ProductStatus
from app.models.restaurant import Hall, RestaurantTable
from app.models.restaurant_order import KitchenTicket, RestaurantOrder, RestaurantOrderItem
from app.models.user import User, UserRole, UserStatus
from app.services.restaurant import restaurant_settings_of

ZERO = Decimal("0")
CENT = Decimal("0.01")
SELLABLE_KINDS = ("dish", "goods")
SENT_STATES = ("sent", "cooking", "ready", "served")
COOKED_STATES = ("cooking", "ready", "served")
CANCEL_REASONS = ("guest_refused", "mistake", "spoiled", "long_wait", "other")
PIN_MAX_FAILS = 5
PIN_LOCK_MINUTES = 10

# ── ruxsatlar ─────────────────────────────────────────────────────
PERM_KEYS = ("orders", "all_tables", "cancel_sent", "discount_max", "unlock_precheck", "move_table", "kitchen",
             "take_payment", "waiter")
_FULL = {"orders": True, "all_tables": True, "cancel_sent": True, "discount_max": 100, "unlock_precheck": True,
         "move_table": True, "kitchen": True, "take_payment": True, "waiter": False}
_NONE = {k: (0 if k == "discount_max" else False) for k in PERM_KEYS}
ROLE_DEFAULTS = {
    UserRole.super_admin: _FULL, UserRole.admin: _FULL, UserRole.director: _FULL, UserRole.manager: _FULL,
    # kassir: cheklarni yuritadi va to'lov oladi, bekor qilish va chegirma menejer tasdig'i bilan
    UserRole.cashier: {**_NONE, "orders": True, "all_tables": True, "move_table": True, "take_payment": True},
}


def _now():
    return datetime.now(timezone.utc)


def _role(user) -> Optional[UserRole]:
    r = getattr(user, "role", None)
    try:
        return r if isinstance(r, UserRole) else UserRole(r)
    except (ValueError, TypeError):
        return None


def rest_perms(user, settings: Optional[dict] = None) -> dict:
    """Foydalanuvchining restoran ruxsatlari. Avval rol sukuti, ustidan maxsus rol, ustidan shaxsiy ruxsatlar.
    `waiter: true` bo'lgan (ofitsiant) xodim uchun "hamma stollar" va "to'lov olish" restoran sozlamasidan."""
    perms = dict(ROLE_DEFAULTS.get(_role(user), _NONE))
    for src in (getattr(getattr(user, "custom_role", None), "permissions", None), getattr(user, "permissions", None)):
        sect = src.get("restaurant") if isinstance(src, dict) else None
        if isinstance(sect, dict):
            for k in PERM_KEYS:
                if k in sect and sect[k] is not None:
                    perms[k] = sect[k]
    try:
        perms["discount_max"] = max(0, min(100, int(perms.get("discount_max") or 0)))
    except (TypeError, ValueError):
        perms["discount_max"] = 0
    if perms.get("waiter") and settings is not None:
        perms["all_tables"] = bool(perms.get("all_tables")) or bool(settings.get("waiter_sees_all_tables"))
        perms["take_payment"] = bool(perms.get("take_payment")) or bool(settings.get("waiter_can_take_payment"))
    return perms


def set_pin(user: User, pin: str) -> None:
    from app.core.security import hash_password
    pin = (pin or "").strip()
    if not pin.isdigit() or not 4 <= len(pin) <= 6:
        raise HTTPException(status_code=400, detail="PIN 4-6 ta raqamdan iborat bo'lishi kerak")
    if len(set(pin)) == 1 or pin in ("1234", "12345", "123456", "4321"):
        raise HTTPException(status_code=400, detail="PIN juda oddiy")
    user.pin_hash = hash_password(pin)


# Xato PIN urinishlari (jarayon xotirasida; har bir urinish audit logga ham yoziladi)
_PIN_FAILS = {}
_PIN_LOCK = threading.Lock()


def _pin_fails(approver_id: int) -> int:
    edge = _now() - timedelta(minutes=PIN_LOCK_MINUTES)
    with _PIN_LOCK:
        lst = [t for t in _PIN_FAILS.get(approver_id, []) if t > edge]
        _PIN_FAILS[approver_id] = lst
        return len(lst)


def _pin_fail(approver_id: int) -> None:
    with _PIN_LOCK:
        _PIN_FAILS.setdefault(approver_id, []).append(_now())


def _log_pin_fail(user: User, approver_id: int) -> None:
    """Asosiy tranzaksiya bekor bo'lsa ham iz qolsin — alohida sessiyada."""
    from app import database
    s = database.SessionLocal()
    try:
        log_action(db=s, action="REST_PIN_FAIL", entity_type="user", entity_id=approver_id, user_id=user.id)
        s.commit()
    except Exception:
        s.rollback()
    finally:
        s.close()


def require_capability(db: Session, user: User, settings: dict, check, approval: Optional[dict], what: str) -> Optional[User]:
    """`check(perms) -> bool`. Xodimning o'zida bo'lsa None; bo'lmasa approval (boshqa xodim + PIN) tekshiriladi va
    tasdiqlagan xodim qaytadi. Ruxsat yo'q va tasdiq yo'q — 403 `APPROVAL_REQUIRED`."""
    if check(rest_perms(user, settings)):
        return None
    if not approval or not approval.get("user_id") or not approval.get("pin"):
        raise HTTPException(status_code=403, detail={"code": "APPROVAL_REQUIRED",
                                                     "message": f"{what}: menejer tasdig'i kerak"})
    from app.core.security import verify_password
    try:
        approver_id = int(approval["user_id"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Tasdiqlovchi noto'g'ri")
    approver = db.query(User).filter(User.id == approver_id, User.company_id == user.company_id,
                                     User.status == UserStatus.active).first()
    if approver is None or not approver.pin_hash:
        raise HTTPException(status_code=403, detail={"code": "APPROVAL_INVALID", "message": "Tasdiqlovchi topilmadi yoki PIN o'rnatilmagan"})
    if _pin_fails(approver.id) >= PIN_MAX_FAILS:
        raise HTTPException(status_code=429, detail=f"PIN ko'p marta xato kiritildi. {PIN_LOCK_MINUTES} daqiqadan keyin urinib ko'ring")
    if not verify_password(str(approval["pin"]), approver.pin_hash):
        _pin_fail(approver.id)
        _log_pin_fail(user, approver.id)
        raise HTTPException(status_code=403, detail={"code": "APPROVAL_INVALID", "message": "PIN noto'g'ri"})
    if not check(rest_perms(approver, settings)):
        raise HTTPException(status_code=403, detail={"code": "APPROVAL_INVALID", "message": "Tasdiqlovchida bu amalga ruxsat yo'q"})
    return approver


# ── yordamchilar ──────────────────────────────────────────────────

def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def get_order(db: Session, company_id: int, order_id: int, *, lock: bool = False) -> RestaurantOrder:
    q = db.query(RestaurantOrder).filter(RestaurantOrder.id == order_id, RestaurantOrder.company_id == company_id)
    if lock and db.get_bind().dialect.name == "postgresql":
        q = q.with_for_update()
    o = q.first()
    if o is None:
        raise HTTPException(status_code=404, detail="Chek topilmadi")
    return o


def check_version(order: RestaurantOrder, version: Optional[int]) -> None:
    if version is not None and int(version) != int(order.version or 1):
        raise HTTPException(status_code=409, detail={"code": "ORDER_CHANGED",
                                                     "message": "Chek boshqa qurilmada o'zgartirildi, yangilang"})


def bump(order: RestaurantOrder) -> None:
    order.version = int(order.version or 1) + 1


def ensure_access(user: User, order: RestaurantOrder, perms: dict, allowed_branches) -> None:
    if allowed_branches is not None and order.branch_id not in allowed_branches:
        raise HTTPException(status_code=403, detail="Bu filialga ruxsat yo'q")
    if not perms.get("orders"):
        raise HTTPException(status_code=403, detail="Cheklar bilan ishlashga ruxsat yo'q")
    if not perms.get("all_tables") and order.waiter_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="Bu boshqa ofitsiantning cheki")


def ensure_editable(order: RestaurantOrder, settings: dict) -> None:
    if order.status == "open":
        return
    if order.status == "prechecked":
        if settings.get("precheck_lock", True):
            raise HTTPException(status_code=409, detail={"code": "PRECHECK_LOCKED",
                                                         "message": "Pre-chek chiqarilgan. Tahrir uchun menejer qulfni ochishi kerak"})
        order.status = "open"
        order.prechecked_at = None
        return
    raise HTTPException(status_code=409, detail="Chek yopilgan")


def effective_service_pct(db: Session, order: RestaurantOrder, settings: dict) -> Decimal:
    if order.order_type != "dine_in":
        return ZERO
    if order.hall_id:
        hall = db.get(Hall, order.hall_id)
        if hall is not None and hall.service_pct is not None:
            return Decimal(str(hall.service_pct))
    return Decimal(str(settings.get("service_pct") or 0))


def recalc(db: Session, order: RestaurantOrder, settings: dict) -> None:
    subtotal = ZERO
    for it in order.items:
        if it.status == "cancelled":
            continue
        subtotal += Decimal(str(it.quantity)) * (Decimal(str(it.unit_price)) + Decimal(str(it.modifiers_total or 0)))
    subtotal = _money(subtotal)
    if order.discount_pct is not None:
        discount = _money(subtotal * Decimal(str(order.discount_pct)) / 100)
    else:
        discount = min(_money(order.discount_amount), subtotal)
    pct = effective_service_pct(db, order, settings)
    base = subtotal - discount if settings.get("service_after_discount", True) else subtotal
    service = _money(base * pct / 100) if pct > 0 else ZERO
    order.subtotal, order.discount_amount, order.service_pct, order.service_amount = subtotal, discount, pct, service
    order.total = subtotal - discount + service


def _station_of(db: Session, product: Product) -> Optional[int]:
    if product.station_id:
        return product.station_id
    if product.category_id:
        cat = db.get(Category, product.category_id)
        return cat.station_id if cat is not None else None
    return None


def _next_daily_no(db: Session, company_id: int, branch_id: int) -> tuple:
    from app.services.document_numbers import _upsert_returning, tashkent_today
    period = tashkent_today().strftime("%Y%m%d")
    seq = _upsert_returning(db, {"company_id": company_id, "branch_id": branch_id, "doc_type": "RC",
                                 "period": period, "last_value": 1})
    return f"RC{period}-{company_id}-{branch_id}-{seq:04d}", seq


# ── amallar ───────────────────────────────────────────────────────

def open_order(db: Session, user: User, settings: dict, *, branch_id: int, order_type: str, table_id: Optional[int],
               guests: int, comment: Optional[str], customer_id: Optional[int] = None) -> RestaurantOrder:
    if order_type not in ("dine_in", "takeaway", "delivery"):
        raise HTTPException(status_code=400, detail="Buyurtma turi noto'g'ri")
    if not 1 <= int(guests or 1) <= 100:
        raise HTTPException(status_code=400, detail="Mehmonlar soni 1 dan 100 gacha")
    hall_id = None
    if order_type == "dine_in":
        if not settings.get("table_service", True) and table_id is None:
            pass   # fast-food: stolsiz zalda ovqatlanish
        elif table_id is None:
            raise HTTPException(status_code=400, detail="Stol tanlanmagan")
    if table_id is not None:
        t = db.query(RestaurantTable).filter(RestaurantTable.id == table_id, RestaurantTable.company_id == user.company_id,
                                             RestaurantTable.is_active == True).first()  # noqa: E712
        if t is None:
            raise HTTPException(status_code=404, detail="Stol topilmadi")
        hall = db.get(Hall, t.hall_id)
        if hall is None or hall.branch_id != branch_id or not hall.is_active:
            raise HTTPException(status_code=400, detail="Stol bu filialga tegishli emas")
        hall_id = hall.id
    number, daily_no = _next_daily_no(db, user.company_id, branch_id)
    o = RestaurantOrder(company_id=user.company_id, branch_id=branch_id, number=number, daily_no=daily_no,
                        order_type=order_type, table_id=table_id, hall_id=hall_id, guests=int(guests or 1),
                        waiter_id=user.id, customer_id=customer_id, status="open", created_by=user.id,
                        comment=(comment or "").strip()[:500] or None, opened_at=_now())
    db.add(o)
    db.flush()
    recalc(db, o, settings)
    return o


def add_items(db: Session, user: User, order: RestaurantOrder, settings: dict, rows: list) -> list:
    ensure_editable(order, settings)
    if not rows or len(rows) > 100:
        raise HTTPException(status_code=400, detail="1 dan 100 tagacha qator yuboring")
    from app.services.restaurant_menu import active_card
    from app.services.restaurant_modifiers import resolve as resolve_modifiers
    added = []
    for i, r in enumerate(rows, start=1):
        p = db.query(Product).filter(Product.id == r.get("product_id"), Product.company_id == user.company_id,
                                     Product.is_deleted == False).first()  # noqa: E712
        if p is None or p.status != ProductStatus.active:
            raise HTTPException(status_code=400, detail=f"{i}-qator: taom topilmadi yoki nofaol")
        if p.item_kind not in SELLABLE_KINDS:
            raise HTTPException(status_code=400, detail=f"{i}-qator: '{p.name}' sotilmaydi")
        try:
            qty = Decimal(str(r.get("quantity", 1)))
        except Exception:
            raise HTTPException(status_code=400, detail=f"{i}-qator: miqdor noto'g'ri")
        if not qty.is_finite() or qty <= 0 or qty > 1000:
            raise HTTPException(status_code=400, detail=f"{i}-qator: miqdor 0 dan katta va 1000 dan kichik bo'lsin")
        course = int(r.get("course") or 1)
        if not 1 <= course <= 5:
            raise HTTPException(status_code=400, detail=f"{i}-qator: kurs 1 dan 5 gacha")
        guest_no = r.get("guest_no")
        if guest_no is not None and not 1 <= int(guest_no) <= 100:
            raise HTTPException(status_code=400, detail=f"{i}-qator: mehmon raqami noto'g'ri")
        card = active_card(db, user.company_id, p.id) if p.item_kind == "dish" else None
        mods, mods_total = resolve_modifiers(db, user.company_id, p, r.get("modifiers"), f"{i}-qator: ")
        it = RestaurantOrderItem(company_id=user.company_id, product_id=p.id, bom_id=card.id if card else None,
                                 name=p.name, quantity=qty, unit_price=_money(p.sale_price),
                                 modifiers=mods, modifiers_total=mods_total,
                                 course=course, guest_no=int(guest_no) if guest_no is not None else None,
                                 station_id=_station_of(db, p) if p.item_kind == "dish" else None,
                                 status="draft", comment=(r.get("comment") or "").strip()[:300] or None,
                                 created_by=user.id, created_at=_now())
        order.items.append(it)
        added.append(it)
    db.flush()
    recalc(db, order, settings)
    bump(order)
    return added


def _ticket_lines(items) -> list:
    return [{"item_id": it.id, "name": it.name, "quantity": float(it.quantity), "comment": it.comment,
             "course": it.course, "guest_no": it.guest_no,
             "modifiers": [m.get("name") for m in (it.modifiers or [])]} for it in items]


def _make_tickets(db: Session, user: User, order: RestaurantOrder, items: list, kind: str) -> list:
    """Sex bo'yicha tiketlar. Sexsiz qatorlar (tayyor tovar, sex belgilanmagan taom) station_id=None tiketiga."""
    groups = {}
    for it in items:
        groups.setdefault(it.station_id, []).append(it)
    tickets = []
    for station_id, its in sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        t = KitchenTicket(company_id=order.company_id, branch_id=order.branch_id, order_id=order.id,
                          station_id=station_id, kind=kind, lines=_ticket_lines(its), created_by=user.id,
                          created_at=_now())
        db.add(t)
        tickets.append(t)
    db.flush()
    return tickets


def send_to_kitchen(db: Session, user: User, order: RestaurantOrder, settings: dict, course: Optional[int]) -> list:
    ensure_editable(order, settings)
    drafts = [it for it in order.items if it.status == "draft" and (course is None or it.course == int(course))]
    if not drafts:
        raise HTTPException(status_code=400, detail="Yuboriladigan yangi taom yo'q")
    now = _now()
    for it in drafts:
        it.status = "sent"
        it.sent_at = now
    tickets = _make_tickets(db, user, order, drafts, "order")
    from app.services.restaurant_payment import on_sent
    on_sent(db, user, order, drafts, settings)          # R7.1: 'sent' rejimida ingredientlar shu yerda yechiladi
    bump(order)
    return tickets


def update_draft_item(db: Session, order: RestaurantOrder, settings: dict, item: RestaurantOrderItem, data: dict) -> None:
    ensure_editable(order, settings)
    if item.status != "draft":
        raise HTTPException(status_code=409, detail="Oshxonaga yuborilgan qatorni o'zgartirib bo'lmaydi, bekor qiling")
    if data.get("quantity") is not None:
        q = Decimal(str(data["quantity"]))
        if q <= 0 or q > 1000:
            raise HTTPException(status_code=400, detail="Miqdor noto'g'ri")
        item.quantity = q
    if "comment" in data:
        item.comment = (data.get("comment") or "").strip()[:300] or None
    if data.get("course") is not None:
        if not 1 <= int(data["course"]) <= 5:
            raise HTTPException(status_code=400, detail="Kurs 1 dan 5 gacha")
        item.course = int(data["course"])
    if data.get("modifiers") is not None:
        from app.services.restaurant_modifiers import resolve as resolve_modifiers
        p = db.get(Product, item.product_id)
        item.modifiers, item.modifiers_total = resolve_modifiers(db, order.company_id, p, data["modifiers"])
    if "guest_no" in data:
        g = data.get("guest_no")
        item.guest_no = int(g) if g is not None else None
    recalc(db, order, settings)
    bump(order)


def cancel_item(db: Session, user: User, order: RestaurantOrder, settings: dict, item: RestaurantOrderItem,
                reason: Optional[str], note: Optional[str], approval: Optional[dict]) -> None:
    ensure_editable(order, settings)
    if item.status == "cancelled":
        raise HTTPException(status_code=409, detail="Qator allaqachon bekor qilingan")
    if item.status == "draft":
        order.items.remove(item)
        db.flush()
        recalc(db, order, settings)
        bump(order)
        return
    if reason not in CANCEL_REASONS:
        raise HTTPException(status_code=400, detail="Bekor qilish sababini tanlang")
    approver = require_capability(db, user, settings, lambda p: bool(p.get("cancel_sent")), approval,
                                  "Oshxonaga yuborilgan taomni bekor qilish")
    was = item.status
    item.write_off = was in COOKED_STATES
    item.status = "cancelled"
    item.cancelled_at = _now()
    item.cancel_reason = (reason + (f": {note.strip()[:250]}" if note and note.strip() else ""))
    item.cancelled_by = user.id
    item.cancel_approved_by = approver.id if approver else None
    if was != "served":
        _make_tickets(db, user, order, [item], "cancel")
    from app.services.restaurant_payment import on_cancelled
    on_cancelled(db, user, order, item, settings)       # R7.3: tayyorlangan — chiqim, aks holda qaytarish
    recalc(db, order, settings)
    bump(order)
    log_action(db=db, action="REST_ITEM_CANCEL", entity_type="restaurant_order", entity_id=order.id, user_id=user.id,
               old_values={"item_id": item.id, "status": was},
               new_values={"reason": item.cancel_reason, "write_off": item.write_off,
                           "approved_by": item.cancel_approved_by, "amount": float(item.quantity * (item.unit_price + (item.modifiers_total or 0)))})


def set_item_status(db: Session, user: User, order: RestaurantOrder, settings: dict, item: RestaurantOrderItem,
                    status: str) -> None:
    """Oshxona (KDS) va ofitsiant: sent -> cooking -> ready -> served. Ofitsiant faqat 'served' qo'ya oladi."""
    flow = {"cooking": ("sent",), "ready": ("sent", "cooking"), "served": ("sent", "cooking", "ready")}
    if status not in flow:
        raise HTTPException(status_code=400, detail="Holat noto'g'ri")
    if order.status not in ("open", "prechecked"):
        raise HTTPException(status_code=409, detail="Chek yopilgan")
    perms = rest_perms(user, settings)
    if status in ("cooking", "ready") and not perms.get("kitchen"):
        raise HTTPException(status_code=403, detail="Oshxona holatini faqat oshxona xodimi o'zgartiradi")
    if status == "served" and not (perms.get("orders") or perms.get("kitchen")):
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    if item.status not in flow[status]:
        raise HTTPException(status_code=409, detail=f"'{item.status}' holatidan '{status}' ga o'tib bo'lmaydi")
    now = _now()
    item.status = status
    if status == "cooking":
        item.cooking_at = now
    elif status == "ready":
        item.ready_at = now
    else:
        item.served_at = now
    bump(order)


def set_discount(db: Session, user: User, order: RestaurantOrder, settings: dict, pct, amount, reason: Optional[str],
                 approval: Optional[dict]) -> None:
    ensure_editable(order, settings)
    recalc(db, order, settings)
    subtotal = Decimal(str(order.subtotal or 0))
    if pct is not None and amount is not None:
        raise HTTPException(status_code=400, detail="Foiz yoki summadan bittasini yuboring")
    if pct is not None:
        pct = Decimal(str(pct))
        if not ZERO <= pct <= 100:
            raise HTTPException(status_code=400, detail="Chegirma foizi 0 dan 100 gacha")
        eff = pct
    else:
        amount = _money(amount or 0)
        if amount < 0 or amount > subtotal:
            raise HTTPException(status_code=400, detail="Chegirma summasi chek summasidan oshmasin")
        eff = (amount / subtotal * 100) if subtotal > 0 else ZERO
    approver = None
    if eff > 0:
        if not (reason or "").strip():
            raise HTTPException(status_code=400, detail="Chegirma sababini yozing")
        approver = require_capability(db, user, settings, lambda p: Decimal(p.get("discount_max") or 0) >= eff,
                                      approval, f"{eff.quantize(Decimal('0.1'))}% chegirma")
    old = {"pct": float(order.discount_pct) if order.discount_pct is not None else None,
           "amount": float(order.discount_amount or 0)}
    if pct is not None:
        order.discount_pct = pct if pct > 0 else None
        order.discount_amount = ZERO
    else:
        order.discount_pct = None
        order.discount_amount = amount
    order.discount_reason = (reason or "").strip()[:200] or None if eff > 0 else None
    recalc(db, order, settings)
    bump(order)
    log_action(db=db, action="REST_DISCOUNT", entity_type="restaurant_order", entity_id=order.id, user_id=user.id,
               old_values=old, new_values={"pct": float(pct) if pct is not None else None,
                                           "amount": float(order.discount_amount), "reason": order.discount_reason,
                                           "approved_by": approver.id if approver else None})


def precheck(db: Session, user: User, order: RestaurantOrder, settings: dict) -> None:
    if order.status != "open":
        raise HTTPException(status_code=409, detail="Pre-chek faqat ochiq chekka chiqariladi")
    if any(it.status == "draft" for it in order.items):
        raise HTTPException(status_code=409, detail={"code": "HAS_DRAFT",
                                                     "message": "Oshxonaga yuborilmagan taomlar bor: yuboring yoki o'chiring"})
    if not any(it.status != "cancelled" for it in order.items):
        raise HTTPException(status_code=400, detail="Chek bo'sh")
    recalc(db, order, settings)
    order.status = "prechecked"
    order.prechecked_at = _now()
    bump(order)


def unlock(db: Session, user: User, order: RestaurantOrder, settings: dict, approval: Optional[dict]) -> None:
    if order.status != "prechecked":
        raise HTTPException(status_code=409, detail="Chek qulflanmagan")
    approver = require_capability(db, user, settings, lambda p: bool(p.get("unlock_precheck")), approval,
                                  "Pre-chekdan keyin chekni ochish")
    order.status = "open"
    order.prechecked_at = None
    bump(order)
    log_action(db=db, action="REST_UNLOCK", entity_type="restaurant_order", entity_id=order.id, user_id=user.id,
               new_values={"approved_by": approver.id if approver else None})


def cancel_order(db: Session, user: User, order: RestaurantOrder, settings: dict, reason: Optional[str],
                 note: Optional[str], approval: Optional[dict]) -> None:
    if order.status not in ("open", "prechecked"):
        raise HTTPException(status_code=409, detail="Chek yopilgan")
    live = [it for it in order.items if it.status != "cancelled"]
    sent = [it for it in live if it.status in SENT_STATES]
    approver = None
    if sent:
        if reason not in CANCEL_REASONS:
            raise HTTPException(status_code=400, detail="Bekor qilish sababini tanlang")
        approver = require_capability(db, user, settings, lambda p: bool(p.get("cancel_sent")), approval,
                                      "Oshxonaga yuborilgan chekni bekor qilish")
    now = _now()
    for it in list(order.items):
        if it.status == "draft":
            order.items.remove(it)
    kitchen_cancel = []
    for it in sent:
        if it.status != "served":
            kitchen_cancel.append(it)
        it.write_off = it.status in COOKED_STATES
        it.status = "cancelled"
        it.cancelled_at = now
        it.cancel_reason = (reason or "other") + (f": {note.strip()[:250]}" if note and note.strip() else "")
        it.cancelled_by = user.id
        it.cancel_approved_by = approver.id if approver else None
    db.flush()
    if kitchen_cancel:
        _make_tickets(db, user, order, kitchen_cancel, "cancel")
    from app.services.restaurant_payment import on_cancelled
    for it in sent:
        on_cancelled(db, user, order, it, settings)
    order.status = "cancelled"
    order.cancelled_at = now
    order.cancel_reason = (reason or "empty")[:300]
    recalc(db, order, settings)
    bump(order)
    log_action(db=db, action="REST_ORDER_CANCEL", entity_type="restaurant_order", entity_id=order.id, user_id=user.id,
               new_values={"reason": order.cancel_reason, "items": len(sent),
                           "approved_by": approver.id if approver else None})


def move_order(db: Session, user: User, order: RestaurantOrder, settings: dict, table_id: int) -> None:
    if not rest_perms(user, settings).get("move_table"):
        raise HTTPException(status_code=403, detail="Chekni ko'chirishga ruxsat yo'q")
    if order.status not in ("open", "prechecked"):
        raise HTTPException(status_code=409, detail="Chek yopilgan")
    t = db.query(RestaurantTable).filter(RestaurantTable.id == table_id, RestaurantTable.company_id == order.company_id,
                                         RestaurantTable.is_active == True).first()  # noqa: E712
    if t is None:
        raise HTTPException(status_code=404, detail="Stol topilmadi")
    hall = db.get(Hall, t.hall_id)
    if hall is None or hall.branch_id != order.branch_id or not hall.is_active:
        raise HTTPException(status_code=400, detail="Stol boshqa filialda")
    old = order.table_id
    order.table_id, order.hall_id = t.id, hall.id
    recalc(db, order, settings)
    bump(order)
    log_action(db=db, action="REST_ORDER_MOVE", entity_type="restaurant_order", entity_id=order.id, user_id=user.id,
               old_values={"table_id": old}, new_values={"table_id": t.id})


def merge_orders(db: Session, user: User, target: RestaurantOrder, source: RestaurantOrder, settings: dict) -> None:
    if not rest_perms(user, settings).get("move_table"):
        raise HTTPException(status_code=403, detail="Cheklarni birlashtirishga ruxsat yo'q")
    if target.id == source.id:
        raise HTTPException(status_code=400, detail="Chekni o'zi bilan birlashtirib bo'lmaydi")
    if target.branch_id != source.branch_id:
        raise HTTPException(status_code=400, detail="Cheklar boshqa-boshqa filialda")
    if target.status != "open" or source.status != "open":
        raise HTTPException(status_code=409, detail="Faqat ochiq (pre-chek chiqmagan) cheklar birlashtiriladi")
    if source.discount_pct is not None or (source.discount_amount or 0) > 0:
        raise HTTPException(status_code=409, detail="Chegirmali chekni birlashtirib bo'lmaydi: avval chegirmani olib tashlang")
    for it in list(source.items):
        it.order = target          # qayta biriktirish (delete-orphan o'chirmaydi)
    db.flush()
    target.guests = int(target.guests or 1) + int(source.guests or 1)
    source.status = "cancelled"
    source.cancelled_at = _now()
    source.cancel_reason = f"Birlashtirildi: #{target.daily_no}"
    source.merged_into_id = target.id
    recalc(db, target, settings)
    recalc(db, source, settings)
    bump(target)
    bump(source)
    log_action(db=db, action="REST_ORDER_MERGE", entity_type="restaurant_order", entity_id=target.id, user_id=user.id,
               new_values={"source_id": source.id})


def transfer_waiter(db: Session, user: User, order: RestaurantOrder, settings: dict, waiter_id: int) -> None:
    if not rest_perms(user, settings).get("move_table"):
        raise HTTPException(status_code=403, detail="Chekni boshqa xodimga o'tkazishga ruxsat yo'q")
    w = db.query(User).filter(User.id == waiter_id, User.company_id == order.company_id,
                              User.status == UserStatus.active).first()
    if w is None or not rest_perms(w, settings).get("orders"):
        raise HTTPException(status_code=400, detail="Xodim topilmadi yoki cheklar bilan ishlamaydi")
    old = order.waiter_id
    order.waiter_id = w.id
    bump(order)
    log_action(db=db, action="REST_ORDER_WAITER", entity_type="restaurant_order", entity_id=order.id, user_id=user.id,
               old_values={"waiter_id": old}, new_values={"waiter_id": w.id})


def settings_for(db: Session, company_id: int) -> dict:
    from app.models.company import Company
    return restaurant_settings_of(db.get(Company, company_id))
