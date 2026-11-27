"""Restoran to'lovi (R5.1-R5.2) va ingredientlarni yechish (R7.1, R7.3).

To'lov mavjud `create_sale` orqali yoziladi (kassa, smena, hamyon, mijoz, hisobotlar o'zgarishsiz ishlaydi).
Taom, modifikator va xizmat haqi qatorlarining o'z qoldig'i yechilmaydi (sale_create: NO_STOCK_ITEM_KINDS);
taom ingredientlari tex karta (sotuv paytidagi versiya) bo'yicha filial "Oshxona" omboridan yechiladi.

Yechish vaqti (`restaurant_settings.deduct_stock_on`):
  * 'paid' (sukut) — chek to'langanda;
  * 'sent' — oshxonaga yuborilganda; pishmagan taom bekor qilinsa ingredientlar qaytariladi.
Tayyorlangan (cooking/ready/served) taom bekor qilinsa ingredientlar chiqim sifatida yechiladi (R7.3).
"""
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.bom import BOM
from app.models.inventory import StockLevel
from app.models.product import Product, ProductStatus
from app.models.restaurant_order import RestaurantOrder, RestaurantOrderItem
from app.models.user import User

ZERO = Decimal("0")
CENT = Decimal("0.01")
PAY_TYPES = ("cash", "card", "uzcard", "humo", "click", "payme", "uzum")
SERVICE_PRODUCT_NAME = "Xizmat haqi"
MAX_DEPTH = 8


def _now():
    return datetime.now(timezone.utc)


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


# ── xizmat haqi mahsuloti ─────────────────────────────────────────

def service_product(db: Session, company_id: int) -> Product:
    """Korxonaning "Xizmat haqi" qatori mahsuloti (item_kind='service', qoldiqsiz). Bo'lmasa yaratiladi.
    Fiskal chek uchun MXIK kodini korxona mahsulot kartasida o'zi kiritadi."""
    p = db.query(Product).filter(Product.company_id == company_id, Product.item_kind == "service",
                                 Product.is_deleted == False).order_by(Product.id).first()  # noqa: E712
    if p is not None:
        return p
    from app.services.restaurant_menu import _new_code
    p = Product(company_id=company_id, name=SERVICE_PRODUCT_NAME, item_kind="service", product_type="service",
                unit="dona", sale_price=ZERO, cost_price=ZERO, sale_currency="UZS", cost_currency="UZS",
                wholesale_currency="UZS", status=ProductStatus.active)
    p.sku = _new_code(db, company_id, "RM-", Product.sku)
    p.barcode = _new_code(db, company_id, "29", Product.barcode)
    db.add(p)
    db.flush()
    return p


# ── ingredientlar ─────────────────────────────────────────────────

def _stock_qty(db: Session, product_id: int, warehouse_id: int) -> Decimal:
    v = db.query(StockLevel.quantity).filter(StockLevel.product_id == product_id, StockLevel.warehouse_id == warehouse_id,
                                             StockLevel.variant_id.is_(None)).scalar()
    return Decimal(str(v or 0))


def expand_card(db: Session, company_id: int, card: Optional[BOM], qty: Decimal, warehouse_id: int,
                settings: dict, depth: int = 0) -> dict:
    """{product_id: (Product, qty)} — 1 birlik uchun `quantity_per_unit` x qty. Yarim tayyor mahsulot qoldig'i
    yetmasa va `semi_auto_expand` yoqilgan bo'lsa yetmagan qismi o'z kartasi bo'yicha xom ashyogacha yoyiladi."""
    from app.services.restaurant_menu import active_card
    out = {}

    def add(p, q):
        if q <= 0:
            return
        cur = out.get(p.id)
        out[p.id] = (p, (cur[1] if cur else ZERO) + q)

    if card is None:
        return out
    for it in card.items:
        comp = it.component_product
        need = Decimal(str(it.quantity_per_unit)) * qty
        if comp.item_kind == "semi" and settings.get("semi_auto_expand", True) and depth < MAX_DEPTH:
            have = max(_stock_qty(db, comp.id, warehouse_id), ZERO)
            sub = active_card(db, company_id, comp.id) if have < need else None
            if sub is not None and sub.items:
                add(comp, have)
                for pid, (p, q) in expand_card(db, company_id, sub, need - have, warehouse_id, settings, depth + 1).items():
                    add(p, q)
                continue
        add(comp, need)
    return out


def modifier_lines(db: Session, company_id: int, item: RestaurantOrderItem, warehouse_id: int, settings: dict) -> dict:
    """Qo'shimchalarga bog'langan mahsulotlar: miqdor x taom soni. Bog'langan mahsulot taom bo'lsa — o'z kartasi."""
    from app.services.restaurant_menu import active_card
    out = {}
    qty = Decimal(str(item.quantity))
    for m in item.modifiers or []:
        pid = m.get("product_id")
        need = Decimal(str(m.get("quantity") or 0)) * qty
        if not pid or need <= 0:
            continue
        p = db.get(Product, int(pid))
        if p is None or p.company_id != company_id:
            continue
        sub = {}
        if p.item_kind == "dish":
            sub = expand_card(db, company_id, active_card(db, company_id, p.id), need, warehouse_id, settings)
        else:
            sub = {p.id: (p, need)}
        for k, (pp, q) in sub.items():
            cur = out.get(k)
            out[k] = (pp, (cur[1] if cur else ZERO) + q)
    return out


def _card_of(db: Session, item: RestaurantOrderItem) -> Optional[BOM]:
    from app.services.restaurant_menu import active_card
    if item.bom_id:
        card = db.get(BOM, item.bom_id)
        if card is not None:
            return card
    return active_card(db, item.company_id, item.product_id)


def deduct_item(db: Session, user: User, order: RestaurantOrder, item: RestaurantOrderItem, settings: dict,
                *, write_off: bool = False) -> Decimal:
    """Taom ingredientlarini yechadi (bir marta). Qaytaradi: tannarx (UZS)."""
    from app.services.inventory_service import deduct_stock
    from app.services.restaurant import get_kitchen_warehouse
    from app.services.restaurant_menu import CostCalc
    if item.stock_deducted:
        return ZERO
    product = db.get(Product, item.product_id)
    if product is None or product.item_kind != "dish":
        return ZERO
    wh = get_kitchen_warehouse(db, order.company_id, order.branch_id)
    if wh is None:
        raise HTTPException(status_code=409, detail="Filialda oshxona ombori yo'q")
    lines = expand_card(db, order.company_id, _card_of(db, item), Decimal(str(item.quantity)), wh.id, settings)
    for pid, (p, q) in modifier_lines(db, order.company_id, item, wh.id, settings).items():
        cur = lines.get(pid)
        lines[pid] = (p, (cur[1] if cur else ZERO) + q)
    calc = CostCalc(db, order.company_id)
    reason = (f"Chiqim: bekor qilingan taom #{order.daily_no} ({item.name})" if write_off
              else f"Restoran #{order.daily_no}: {item.name} x{item.quantity}")
    cost = ZERO
    saved = []
    for pid, (p, q) in sorted(lines.items()):
        q = q.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if q <= 0:
            continue
        deduct_stock(db, p.id, q, user.id, reason=reason,
                     reference_type="rest_writeoff" if write_off else "restaurant_order",
                     reference_id=order.id, warehouse_id=wh.id, allow_negative=True)
        cost += q * calc._own_cost(p) if p.item_kind != "semi" else q * calc.unit_cost(p)
        saved.append({"product_id": p.id, "quantity": str(q), "warehouse_id": wh.id})
    item.stock_deducted = True
    item.stock_lines = saved
    return cost


def lines_cost(db: Session, company_id: int, item: RestaurantOrderItem) -> Decimal:
    """Allaqachon yechilgan ingredientlar tannarxi (stock_lines bo'yicha)."""
    from app.services.restaurant_menu import CostCalc
    calc = CostCalc(db, company_id)
    total = ZERO
    for ln in item.stock_lines or []:
        p = db.get(Product, int(ln["product_id"]))
        if p is not None:
            q = Decimal(str(ln["quantity"]))
            total += q * (calc.unit_cost(p) if p.item_kind == "semi" else calc._own_cost(p))
    return total


def restore_item(db: Session, user: User, order: RestaurantOrder, item: RestaurantOrderItem) -> None:
    """'sent' rejimida pishmagan taom bekor qilinsa yechilgan ingredientlar aynan qaytariladi."""
    from app.services.inventory_service import receive_stock
    if not item.stock_deducted:
        return
    for ln in item.stock_lines or []:
        receive_stock(db, int(ln["product_id"]), Decimal(str(ln["quantity"])), user.id,
                      reason=f"Bekor qilingan taom qaytdi #{order.daily_no} ({item.name})",
                      reference_type="restaurant_order", reference_id=order.id, warehouse_id=int(ln["warehouse_id"]))
    item.stock_deducted = False
    item.stock_lines = None


def on_sent(db: Session, user: User, order: RestaurantOrder, items: list, settings: dict) -> None:
    if settings.get("deduct_stock_on") == "sent":
        for it in items:
            deduct_item(db, user, order, it, settings)


def on_cancelled(db: Session, user: User, order: RestaurantOrder, item: RestaurantOrderItem, settings: dict) -> None:
    """Bekor qilingan qator: tayyorlangan bo'lsa chiqim (yechilmagan bo'lsa yechiladi), aks holda yechilgani qaytadi."""
    if item.write_off:
        if not item.stock_deducted:
            deduct_item(db, user, order, item, settings, write_off=True)
    else:
        restore_item(db, user, order, item)


# ── to'lov ────────────────────────────────────────────────────────

def _payments(raw: list, total: Decimal) -> tuple:
    """Tekshiradi va (sotuv to'lovlari, qaytim, jami olingan) qaytaradi. Qaytim faqat naqd puldan."""
    if not raw:
        raise HTTPException(status_code=400, detail="To'lov kiritilmagan")
    if len(raw) > 10:
        raise HTTPException(status_code=400, detail="To'lov qatorlari juda ko'p")
    rows = []
    for p in raw:
        t = p.get("type")
        if t not in PAY_TYPES:
            raise HTTPException(status_code=400, detail="To'lov turi noto'g'ri")
        amt = _money(p.get("amount"))
        if amt <= 0:
            raise HTTPException(status_code=400, detail="To'lov summasi musbat bo'lishi kerak")
        rows.append({"type": t, "amount": amt, "reference": (p.get("reference") or None),
                     "terminal_id": p.get("terminal_id")})
    received = sum((r["amount"] for r in rows), ZERO)
    cash = sum((r["amount"] for r in rows if r["type"] == "cash"), ZERO)
    noncash = received - cash
    if noncash > total:
        raise HTTPException(status_code=400, detail="Naqdsiz to'lov chek summasidan oshmasin")
    if received < total:
        raise HTTPException(status_code=400, detail=f"To'lov yetarli emas: {received} / {total}")
    change = received - total
    # qaytim naqd qatorlardan ayiriladi (sotuvga aynan chek summasi yoziladi)
    left = change
    for r in rows:
        if r["type"] == "cash" and left > 0:
            dec = min(r["amount"], left)
            r["amount"] -= dec
            left -= dec
    rows = [r for r in rows if r["amount"] > 0]
    return rows, change, received


def pay_order(db: Session, user: User, order: RestaurantOrder, settings: dict, payments: list, tips,
              ip: Optional[str] = None):
    """Chekni to'laydi: Sale yaratadi, ingredientlarni yechadi, chekni yopadi. Qaytaradi: (sale, change)."""
    from app.models.sale import SaleItem
    from app.schemas.sale import SaleCreate
    from app.services.branch_provisioning import get_default_warehouse
    from app.services.restaurant_orders import recalc, rest_perms
    from app.services.sale_create import create_sale

    if not rest_perms(user, settings).get("take_payment"):
        raise HTTPException(status_code=403, detail="To'lov qabul qilishga ruxsat yo'q")
    if order.status not in ("open", "prechecked"):
        raise HTTPException(status_code=409, detail="Chek allaqachon yopilgan")
    if any(it.status == "draft" for it in order.items):
        raise HTTPException(status_code=409, detail={"code": "HAS_DRAFT",
                                                     "message": "Oshxonaga yuborilmagan taomlar bor: yuboring yoki o'chiring"})
    live = [it for it in order.items if it.status != "cancelled"]
    if not live:
        raise HTTPException(status_code=400, detail="Chek bo'sh")
    recalc(db, order, settings)
    total = _money(order.total)
    rows, change, received = _payments(payments, total)
    tips = _money(tips)
    if tips < 0:
        raise HTTPException(status_code=400, detail="Choy puli manfiy bo'lmasin")

    wh = get_default_warehouse(db, order.company_id, order.branch_id)
    if wh is None:
        raise HTTPException(status_code=409, detail="Filialda asosiy ombor yo'q")

    items = [{"product_id": it.product_id, "quantity": it.quantity,
              "unit_price": _money(Decimal(str(it.unit_price)) + Decimal(str(it.modifiers_total or 0))),
              "price_manual": True, "discount": ZERO, "warehouse_id": wh.id} for it in live]
    if order.service_amount and Decimal(str(order.service_amount)) > 0:
        sp = service_product(db, order.company_id)
        items.append({"product_id": sp.id, "quantity": Decimal("1"), "unit_price": _money(order.service_amount),
                      "price_manual": True, "discount": ZERO, "warehouse_id": wh.id})

    # Ingredientlar (to'lovda yechish rejimi yoki hali yechilmaganlar) — create_sale bilan bitta tranzaksiyada
    dish_cost = {}
    for it in live:
        c = lines_cost(db, order.company_id, it) if it.stock_deducted else deduct_item(db, user, order, it, settings)
        if it.product_id not in dish_cost:
            dish_cost[it.product_id] = [ZERO, ZERO]
        dish_cost[it.product_id][0] += c
        dish_cost[it.product_id][1] += Decimal(str(it.quantity))

    table = None
    if order.table_id:
        from app.models.restaurant import RestaurantTable
        table = db.get(RestaurantTable, order.table_id)
    data = SaleCreate(
        items=items,
        payment_type=rows[0]["type"] if len(rows) == 1 else "mixed",
        paid_amount=total,
        payments=[{"type": r["type"], "amount": r["amount"], "reference": r["reference"],
                   "terminal_id": r["terminal_id"]} for r in rows],
        discount_amount=_money(order.discount_amount),
        customer_id=order.customer_id,
        warehouse_id=wh.id,
        status="completed",
        note=f"Restoran #{order.daily_no}" + (f", stol {table.name}" if table else ""),
    )

    now = _now()
    order.status = "paid"
    order.closed_at = now
    order.paid_by = user.id
    order.tips_amount = tips
    order.change_amount = change
    order.payments = [{"type": r["type"], "amount": float(r["amount"]), "reference": r["reference"],
                       "terminal_id": r["terminal_id"]} for r in rows]
    for it in live:
        if it.status in ("sent", "cooking", "ready"):
            it.status = "served"
            it.served_at = it.served_at or now
    from app.services.restaurant_orders import bump
    bump(order)
    db.flush()

    sale = create_sale(db, data, user, ip=ip)          # o'zi commit qiladi (yuqoridagi o'zgarishlar bilan birga)

    # Bog'lash va taom tannarxi (sotuv qatoriga)
    order.sale_id = sale.id
    for si in db.query(SaleItem).filter(SaleItem.sale_id == sale.id):
        dc = dish_cost.get(si.product_id)
        if dc and dc[1] > 0:
            si.cost_price = (dc[0] / dc[1]).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    from app.core.audit import log_action
    log_action(db=db, action="REST_ORDER_PAID", entity_type="restaurant_order", entity_id=order.id, user_id=user.id,
               ip_address=ip, new_values={"sale_id": sale.id, "total": float(total), "received": float(received),
                                          "change": float(change), "tips": float(tips)})
    db.commit()
    return sale, change
