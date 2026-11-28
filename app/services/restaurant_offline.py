"""R5.0: E-Code POS Restoran (desktop) uchun oflayn ma'lumotlar va sinxronlash.

`bootstrap` — oflayn ishlash uchun bir so'rovda: sozlamalar, zallar va stollar, menyu, qo'shimchalar, stop-list,
filialning ochiq cheklari, chek rekvizitlari, xodim ruxsatlari.

`apply_op` — oflayn qilingan bitta amal (yangi chek yoki mavjud chekni davom ettirish). Idempotent: `op_id`
`restaurant_offline_ops` da saqlanadi, takror kelsa saqlangan natija qaytariladi. Chek `order_uuid`
(`restaurant_orders.client_uuid`) bo'yicha topiladi yoki `server_id` bo'yicha davom ettiriladi.

Qoidalar:
* taomlar oflayndagi narx bilan yoziladi (mijoz shuni ko'rgan); joriy narxdan farq qilsa auditga yoziladi;
* stop-list oflayn sotuvni rad etmaydi (taom allaqachon berilgan);
* `sent_at` bilan kelgan taomlar oshxonaga yuborilgan hisoblanadi; tiketlar qurilmada chop etilgan, shuning uchun
  serverdagi navbatda `printed_at` qo'yiladi (qayta chop etilmaydi);
* yuborilgan taomni oflayn bekor qilib bo'lmaydi (menejer PIN tasdig'i onlayn kerak) — qurilma ruxsat bermaydi;
* to'lov oflayndagi vaqt bilan (`create_sale` 72 soat qoidasi), to'lovda qolgan yuborilmagan taomlar yuborilgan
  hisoblanadi; fiskal natija (qurilmadagi fiskal modul) sotuvga yoziladi.
Xato bo'lsa hech narsa yozilmaydi (tranzaksiya orqaga), qurilma amalni "xato" ro'yxatida saqlaydi.
"""
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.product import Product, ProductStatus
from app.models.restaurant_order import KitchenTicket, RestaurantOfflineOp, RestaurantOrder
from app.models.user import User

CENT = Decimal("0.01")
MAX_AGE_HOURS = 72
FISCAL_FIELDS = ("fiscal_sign", "fiscal_qr_url", "fiscal_receipt_seq", "fiscal_transaction_id", "fiscal_at",
                 "fiscal_factory_id")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(d: Optional[datetime]) -> Optional[datetime]:
    if d is None:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d


def _check_time(d: Optional[datetime], label: str) -> Optional[datetime]:
    d = _naive(d)
    if d is None:
        return None
    now = _utcnow()
    if d < now - timedelta(hours=MAX_AGE_HOURS) or d > now + timedelta(minutes=5):
        raise HTTPException(status_code=400, detail=f"{label}: vaqt noto'g'ri yoki juda eski ({MAX_AGE_HOURS} soatdan ko'p)")
    return d


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


# ── bootstrap ──────────────────────────────────────────────────────

def bootstrap(db: Session, user: User, branch_id: int, settings: dict) -> dict:
    from app.models.branch import Branch
    from app.models.category import Category
    from app.models.company import Company
    from app.models.restaurant import Hall, KitchenStation, RestaurantTable
    from app.routers.restaurant_floor import _hall_out
    from app.routers.restaurant_orders import _order_out
    from app.services import restaurant_modifiers as mod_svc
    from app.services import restaurant_stops as stops
    from app.services.restaurant_menu import money
    from app.services.restaurant_orders import rest_perms
    from app.services.restaurant_payment import PAY_TYPES
    cid = user.company_id
    company = db.get(Company, cid)
    branch = db.get(Branch, branch_id)
    halls = (db.query(Hall).filter(Hall.company_id == cid, Hall.branch_id == branch_id, Hall.is_active == True)  # noqa: E712
             .order_by(Hall.sort_order, Hall.id).all())
    by_hall = {}
    if halls:
        for t in (db.query(RestaurantTable).filter(RestaurantTable.hall_id.in_([h.id for h in halls]),
                                                   RestaurantTable.is_active == True)  # noqa: E712
                  .order_by(RestaurantTable.id)):
            by_hall.setdefault(t.hall_id, []).append(t)
    cats = db.query(Category).filter(Category.company_id == cid, Category.is_deleted == False).all()  # noqa: E712
    cat_station = {c.id: c.station_id for c in cats if getattr(c, "station_id", None)}
    items = (db.query(Product).filter(Product.company_id == cid, Product.is_deleted == False,  # noqa: E712
                                      Product.status == ProductStatus.active,
                                      Product.item_kind.in_(("dish", "goods")))
             .order_by(Product.name).all())
    mods = mod_svc.groups_by_product(db, cid, [p.id for p in items if p.item_kind == "dish"])
    open_orders = (db.query(RestaurantOrder).filter(RestaurantOrder.company_id == cid,
                                                    RestaurantOrder.branch_id == branch_id,
                                                    RestaurantOrder.status.in_(("open", "prechecked")))
                   .order_by(RestaurantOrder.id).all())
    used_cats = {p.category_id for p in items if p.category_id}
    # oflayn fiskal chek (qurilmadagi fiskal modul) uchun: MXIK, o'lchov kodi, QQS foizi
    from app.services.hippo_fiscalize import _vat_percent
    default_vat = getattr(company, "fiscal_default_vat", None)

    def fiscal_of(p):
        return {"mxik_code": getattr(p, "mxik_code", None) or "", "package_code": getattr(p, "package_code", None),
                "vat_percent": _vat_percent(p, default_vat)}
    # "Xizmat haqi" qatori (GET da yaratilmaydi; birinchi to'lovda serverning o'zi yaratadi)
    sp = (db.query(Product).filter(Product.company_id == cid, Product.item_kind == "service",
                                   Product.is_deleted == False).order_by(Product.id).first())  # noqa: E712
    return {
        "server_time": datetime.now(timezone.utc).isoformat(),
        "company": {"id": cid, "name": company.name if company else None,
                    "phone": getattr(company, "phone", None), "address": getattr(company, "address", None)},
        "branch": {"id": branch_id, "name": branch.name if branch else None,
                   "phone": getattr(branch, "phone", None), "address": getattr(branch, "address", None),
                   "legal_name": getattr(branch, "legal_name", None), "stir": getattr(branch, "stir", None)},
        "user": {"id": user.id, "name": user.name, "role": getattr(user.role, "value", user.role),
                 "perms": rest_perms(user, settings)},
        "settings": settings,
        "pay_types": list(PAY_TYPES),
        "halls": [_hall_out(h, by_hall.get(h.id, [])) for h in halls],
        "stations": [{"id": s.id, "name": s.name} for s in
                     db.query(KitchenStation).filter(KitchenStation.company_id == cid).order_by(KitchenStation.sort_order,
                                                                                                KitchenStation.id)],
        "categories": [{"id": c.id, "name": c.name, "station_id": cat_station.get(c.id)}
                       for c in sorted(cats, key=lambda c: c.name.lower()) if c.id in used_cats],
        "menu": [{"id": p.id, "name": p.name, "kind": p.item_kind, "unit": p.unit, "barcode": p.barcode,
                  "category_id": p.category_id, "price": money(p.sale_price or 0),
                  "station_id": (p.station_id or cat_station.get(p.category_id)) if p.item_kind == "dish" else None,
                  "modifier_group_ids": mods.get(p.id, []), **fiscal_of(p)} for p in items],
        "service_item": ({"product_id": sp.id, "name": sp.name, "barcode": sp.barcode, **fiscal_of(sp)} if sp else
                         {"product_id": None, "name": "Xizmat haqi", "barcode": "", "mxik_code": "", "package_code": None,
                          "vat_percent": int(default_vat) if default_vat is not None else 12}),
        "modifier_groups": mod_svc.list_groups(db, cid, include_inactive=False),
        "stop_list": stops.status(db, cid, branch_id, settings),
        "open_orders": [_order_out(db, o, settings) for o in open_orders],
    }


# ── sinxronlash ────────────────────────────────────────────────────

def _find_order(db: Session, user: User, op: dict) -> Optional[RestaurantOrder]:
    q = db.query(RestaurantOrder).filter(RestaurantOrder.company_id == user.company_id)
    if op.get("order_uuid"):
        o = q.filter(RestaurantOrder.client_uuid == op["order_uuid"]).with_for_update().first()
        if o is not None:
            return o
    if op.get("server_id"):
        o = q.filter(RestaurantOrder.id == int(op["server_id"])).with_for_update().first()
        if o is None:
            raise HTTPException(status_code=404, detail="Chek serverda topilmadi")
        return o
    return None


def apply_op(db: Session, user: User, settings: dict, branch_id: int, op: dict, device: Optional[str] = None) -> dict:
    from app.services import restaurant_orders as svc
    from app.services.restaurant_payment import on_sent, pay_order
    cid = user.company_id
    op_id = (op.get("op_id") or "").strip()
    if not 8 <= len(op_id) <= 64:
        raise HTTPException(status_code=400, detail="op_id noto'g'ri")
    done = db.query(RestaurantOfflineOp).filter(RestaurantOfflineOp.company_id == cid,
                                                RestaurantOfflineOp.op_id == op_id).first()
    if done is not None:
        return {**(done.result or {}), "duplicate": True}

    if op.get("cancel") and (op.get("payment") or any(r.get("sent_at") for r in (op.get("items") or []))):
        raise HTTPException(status_code=409, detail="Oshxonaga yuborilgan yoki to'langan chekni oflayn bekor qilib bo'lmaydi")
    warnings = []
    opened_at = _check_time(op.get("opened_at"), "Chek ochilgan vaqt")
    order = _find_order(db, user, op)
    created = False
    if order is None:
        order = svc.open_order(db, user, settings, branch_id=branch_id, order_type=op.get("order_type") or "dine_in",
                               table_id=op.get("table_id"), guests=int(op.get("guests") or 1),
                               comment=op.get("comment"), customer_id=op.get("customer_id"))
        order.client_uuid = (op.get("order_uuid") or "")[:40] or None
        order.offline_no = (op.get("offline_no") or "")[:20] or None
        if opened_at:
            order.opened_at = opened_at
        created = True
    else:
        if order.branch_id != branch_id:
            raise HTTPException(status_code=409, detail="Chek boshqa filialga tegishli")
        if (order.status == "paid" and op.get("payment") and op.get("order_uuid")
                and order.client_uuid == op.get("order_uuid")):
            # to'lov allaqachon yozilgan (javob qurilmaga yetmagan bo'lishi mumkin) — qayta yozilmaydi
            return {"op_id": op_id, "order_id": order.id, "daily_no": order.daily_no, "number": order.number,
                    "status": order.status, "created": False, "sale_id": order.sale_id, "sale_number": None,
                    "change": float(order.change_amount or 0), "total": float(order.total or 0),
                    "warnings": ["To'lov avval yozilgan"], "duplicate": True}
        if order.status in ("paid", "cancelled"):
            raise HTTPException(status_code=409, detail={"code": "ORDER_CLOSED",
                                                         "message": f"Chek #{order.daily_no} serverda allaqachon yopilgan"})
        if op.get("guests"):
            order.guests = int(op["guests"])

    # ── taomlar ──
    rows = op.get("items") or []
    if rows:
        if order.status == "prechecked":
            order.status = "open"                      # oflayn pre-chekdan keyin ham qo'shilgan bo'lishi mumkin
        clean = []
        for r in rows:
            row = {k: r.get(k) for k in ("product_id", "quantity", "comment", "course", "guest_no")}
            row["modifiers"] = r.get("modifiers") or None
            clean.append(row)
        has_mods = any(row["modifiers"] for row in clean)
        try:
            with db.begin_nested():
                added = svc.add_items(db, user, order, settings, clean, enforce_stops=False)
        except HTTPException as e:
            if not has_mods:
                raise
            for row in clean:                       # o'zgargan/o'chirilgan qo'shimcha sotuvni to'xtatmasin
                row["modifiers"] = None
            warnings.append(f"Qo'shimchalar qabul qilinmadi, ularsiz yozildi: {e.detail}")
            added = svc.add_items(db, user, order, settings, clean, enforce_stops=False)
        price_diff = []
        sent_now = []
        for it, r in zip(added, rows):
            if r.get("unit_price") is not None:
                offline_price = _money(r["unit_price"])
                if offline_price != _money(it.unit_price):
                    price_diff.append({"product_id": it.product_id, "server": float(it.unit_price),
                                       "offline": float(offline_price)})
                    it.unit_price = offline_price
            if r.get("created_at"):
                it.created_at = _check_time(r["created_at"], "Taom qo'shilgan vaqt") or it.created_at
            if r.get("sent_at"):
                it.status = "sent"
                it.sent_at = _check_time(r["sent_at"], "Oshxonaga yuborilgan vaqt")
                sent_now.append(it)
        db.flush()
        if sent_now:
            _sent(db, user, order, sent_now, settings)
            on_sent(db, user, order, sent_now, settings)
        if price_diff:
            from app.core.audit import log_action
            log_action(db=db, action="REST_OFFLINE_PRICE", entity_type="restaurant_order", entity_id=order.id,
                       user_id=user.id, new_values={"items": price_diff, "op_id": op_id})
        svc.recalc(db, order, settings)

    if op.get("precheck_at") and order.status == "open":
        order.status = "prechecked"
        order.prechecked_at = _check_time(op["precheck_at"], "Pre-chek vaqti")

    sale = None
    change = Decimal("0")
    pay = op.get("payment")
    if pay:
        paid_at = _check_time(pay.get("paid_at"), "To'lov vaqti") or _utcnow()
        drafts = [it for it in order.items if it.status == "draft"]
        if drafts:                                    # to'lov paytida yuborilmagan taomlar ham berilgan
            for it in drafts:
                it.status = "sent"
                it.sent_at = paid_at
            _sent(db, user, order, drafts, settings)
            on_sent(db, user, order, drafts, settings)
        sale, change = pay_order(db, user, order, settings, pay.get("payments") or [], pay.get("tips") or 0,
                                 created_at=paid_at)
        fiscal = pay.get("fiscal") or {}
        if fiscal and sale is not None and not sale.fiscal_sign:
            for k in FISCAL_FIELDS:
                if fiscal.get(k) not in (None, ""):
                    setattr(sale, k, fiscal[k])
    elif op.get("cancel"):
        live = [it for it in order.items if it.status != "cancelled"]
        if any(it.status != "draft" for it in live):
            raise HTTPException(status_code=409, detail="Oshxonaga yuborilgan chekni oflayn bekor qilib bo'lmaydi")
        svc.cancel_order(db, user, order, settings, (op["cancel"] or {}).get("reason") or "empty", None, None)

    svc.bump(order)
    db.flush()
    result = {"op_id": op_id, "order_id": order.id, "daily_no": order.daily_no, "number": order.number,
              "status": order.status, "created": created, "sale_id": sale.id if sale is not None else None,
              "sale_number": sale.number if sale is not None else None, "change": float(change),
              "total": float(order.total or 0), "warnings": warnings}
    db.add(RestaurantOfflineOp(company_id=cid, op_id=op_id, order_id=order.id, device=(device or "")[:100] or None,
                               result=result, created_by=user.id, created_at=_utcnow()))
    from app.core.audit import log_action
    log_action(db=db, action="REST_OFFLINE_SYNC", entity_type="restaurant_order", entity_id=order.id, user_id=user.id,
               new_values={"op_id": op_id, "created": created, "items": len(rows), "paid": bool(pay),
                           "device": device, "offline_no": order.offline_no})
    return result


def _sent(db: Session, user: User, order: RestaurantOrder, items: list, settings: dict) -> None:
    """Oflayn yuborilgan taomlar tiketlari: qurilmada chop etilgan, navbatda qayta chop etilmaydi."""
    from app.services.restaurant_orders import _make_tickets
    tickets = _make_tickets(db, user, order, items, "order")
    now = _utcnow()
    for t in tickets:
        t.printed_at = now
    db.flush()
