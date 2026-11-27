"""Restoran chekini qaytarish (R5.4).

To'langan chek (status 'paid') to'liq yoki qatorlar bo'yicha qaytariladi. Pul mavjud `create_return_sale`
orqali chiqadi (kassa harakati, smena, asl sotuvning qaytarilgan miqdori va holati odatdagidek), lekin:
  * taom va xizmat haqi omborga qaytmaydi — tayyorlangan taomning ingredientlari to'lovda yechilgan va chiqim
    bo'lib qoladi;
  * tovar (ichimlik) faqat `restock` belgilansa omborga qaytadi.
Chegirma va xizmat haqi qaytarilayotgan taomlar ulushiga mutanosib qaytariladi. Ruxsat: `cancel_sent`
(menejer), aks holda menejer PIN tasdig'i.
"""
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.product import Product
from app.models.restaurant_order import RestaurantOrder, RestaurantOrderItem
from app.models.sale import SaleItem
from app.models.user import User

ZERO = Decimal("0")
CENT = Decimal("0.01")
REFUND_PAY_TYPES = ("cash", "card", "uzcard", "humo", "click", "payme", "uzum")
REFUND_REASONS = ("quality", "guest_refused", "mistake", "long_wait", "other")


def _q(v, step=CENT, rounding=ROUND_HALF_UP) -> Decimal:
    return Decimal(str(v)).quantize(step, rounding=rounding)


def _remaining(it: RestaurantOrderItem) -> Decimal:
    return Decimal(str(it.quantity)) - Decimal(str(it.refunded_qty or 0))


def _line_price(it: RestaurantOrderItem) -> Decimal:
    return Decimal(str(it.unit_price)) + Decimal(str(it.modifiers_total or 0))


def plan_refund(db: Session, order: RestaurantOrder, lines: Optional[list]) -> dict:
    """Qaytariladigan qatorlar, xizmat va chegirma ulushi, summa. Hech narsani o'zgartirmaydi."""
    live = {it.id: it for it in order.items if it.status != "cancelled"}
    picked = []
    if not lines:
        for it in live.values():
            rem = _remaining(it)
            if rem > 0:
                picked.append((it, rem, False))
    else:
        seen = set()
        for i, ln in enumerate(lines, start=1):
            it = live.get(int(ln.get("item_id") or 0))
            if it is None:
                raise HTTPException(status_code=400, detail=f"{i}-qator: chek qatori topilmadi")
            if it.id in seen:
                raise HTTPException(status_code=400, detail=f"{i}-qator takrorlangan")
            seen.add(it.id)
            qty = Decimal(str(ln.get("quantity") if ln.get("quantity") is not None else _remaining(it)))
            if qty <= 0 or qty > _remaining(it):
                raise HTTPException(status_code=400, detail=f"'{it.name}': qaytarish miqdori 0 dan katta va qolgandan oshmasin")
            picked.append((it, qty, bool(ln.get("restock"))))
    if not picked:
        raise HTTPException(status_code=409, detail="Qaytariladigan narsa qolmagan")

    gross = sum((_line_price(it) * q for it, q, _ in picked), ZERO)
    subtotal = Decimal(str(order.subtotal or 0))
    share = (gross / subtotal) if subtotal > 0 else Decimal("1")
    all_left = sum((_remaining(it) for it in live.values()), ZERO)
    full_rest = sum((q for _, q, _ in picked), ZERO) == all_left      # oxirgi qaytarish — qoldiqlar aniq yopiladi
    refunded_before = Decimal(str(order.refunded_amount or 0))

    service_qty = ZERO
    service_amount = Decimal(str(order.service_amount or 0))
    if service_amount > 0:
        sp_item = _service_sale_item(db, order)
        rem_srv = (Decimal(str(sp_item.quantity)) - Decimal(str(sp_item.returned_quantity or 0))) if sp_item else ZERO
        # sale_items.quantity Numeric(12,3) — ulush 3 xonagacha (bazada yaxlitlanib nomuvofiqlik bo'lmasin)
        service_qty = rem_srv if full_rest else min(rem_srv, _q(share, Decimal("0.001"), ROUND_DOWN))
    discount_total = Decimal(str(order.discount_amount or 0))
    if full_rest:
        amount = _q(Decimal(str(order.total or 0)) - refunded_before, CENT, ROUND_DOWN)
        discount = gross + service_amount * service_qty - amount
    else:
        discount = _q(discount_total * share)
        amount = _q(gross + service_amount * service_qty - discount, CENT, ROUND_DOWN)
    return {"picked": picked, "gross": gross, "service_qty": service_qty, "service_price": service_amount,
            "discount": max(ZERO, discount), "amount": max(ZERO, amount)}


def _service_sale_item(db: Session, order: RestaurantOrder) -> Optional[SaleItem]:
    if not order.sale_id:
        return None
    return (db.query(SaleItem).join(Product, Product.id == SaleItem.product_id)
            .filter(SaleItem.sale_id == order.sale_id, Product.item_kind == "service").first())


def refund_order(db: Session, user: User, order: RestaurantOrder, settings: dict, *, lines: Optional[list],
                 reason: Optional[str], note: Optional[str], payment_type: str, approval: Optional[dict],
                 ip: Optional[str] = None):
    from app.schemas.sale import SaleCreate
    from app.services.branch_provisioning import get_default_warehouse
    from app.services.restaurant_orders import bump, require_capability
    from app.services.sale_return import create_return_sale

    if order.status != "paid" or not order.sale_id:
        raise HTTPException(status_code=409, detail="Faqat to'langan chek qaytariladi")
    if reason not in REFUND_REASONS:
        raise HTTPException(status_code=400, detail="Qaytarish sababini tanlang")
    if payment_type not in REFUND_PAY_TYPES:
        raise HTTPException(status_code=400, detail="Pul qaytarish usuli noto'g'ri")
    approver = require_capability(db, user, settings, lambda p: bool(p.get("cancel_sent")), approval,
                                  "To'langan chekni qaytarish")
    plan = plan_refund(db, order, lines)
    if plan["amount"] <= 0:
        raise HTTPException(status_code=409, detail="Qaytariladigan summa yo'q")

    wh = get_default_warehouse(db, order.company_id, order.branch_id)
    if wh is None:
        raise HTTPException(status_code=409, detail="Filialda asosiy ombor yo'q")
    items, restock = [], set()
    for it, qty, rs in plan["picked"]:
        items.append({"product_id": it.product_id, "quantity": qty, "warehouse_id": wh.id})
        if rs:
            p = db.get(Product, it.product_id)
            if p is not None and p.item_kind == "goods":
                restock.add(p.id)
    if plan["service_qty"] > 0:
        sp = _service_sale_item(db, order)
        items.append({"product_id": sp.product_id, "quantity": plan["service_qty"], "warehouse_id": wh.id})

    amount = plan["amount"]
    data = SaleCreate(
        items=items, payment_type=payment_type, paid_amount=amount,
        paid_cash=amount if payment_type == "cash" else ZERO,
        paid_card=amount if payment_type != "cash" else ZERO,
        discount_amount=plan["discount"], original_sale_id=order.sale_id, warehouse_id=wh.id,
        customer_id=order.customer_id,
        note=f"Restoran #{order.daily_no}: {reason}" + (f" ({note.strip()[:200]})" if note and note.strip() else ""),
    )

    # chek holati create_return_sale bilan bitta tranzaksiyada (u commit qiladi)
    for it, qty, _ in plan["picked"]:
        it.refunded_qty = Decimal(str(it.refunded_qty or 0)) + qty
    order.refunded_amount = Decimal(str(order.refunded_amount or 0)) + amount
    bump(order)
    db.flush()

    ret = create_return_sale(db, data, user, ip=ip, restaurant=True, restock_product_ids=restock)

    record = {
        "sale_id": ret.id, "number": ret.number, "amount": float(amount), "payment_type": payment_type,
        "reason": reason, "note": (note or "").strip()[:200] or None,
        "at": datetime.now(timezone.utc).isoformat(), "by": user.id,
        "approved_by": approver.id if approver else None,
        "lines": [{"item_id": it.id, "name": it.name, "quantity": float(q), "restock": bool(rs)}
                  for it, q, rs in plan["picked"]],
    }
    order.refunds = list(order.refunds or []) + [record]
    log_action(db=db, action="REST_ORDER_REFUND", entity_type="restaurant_order", entity_id=order.id,
               user_id=user.id, ip_address=ip, new_values=record)
    db.commit()
    return ret, plan
