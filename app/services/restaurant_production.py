"""Restoran: yarim tayyor mahsulot ishlab chiqarish (R7.2).

Soddalashtirilgan forma: yarim tayyor mahsulot (`item_kind='semi'`) va miqdor kiritiladi ("10 kg qiyma").
Faol tex karta bo'yicha xom ashyo filial "Oshxona" omboridan yechiladi, yarim tayyor mahsulot shu omborga
kirim qilinadi. Hammasi bitta `production_orders` yozuvi (xom ashyo va tayyor mahsulot ombori bir xil,
holat darhol `completed`); harakatlar `reference_type='production_order'`.

Ichidagi yarim tayyor ingredient qoldig'i yetmasa — R7.1 dagi kabi (`semi_auto_expand`) o'z kartasi bo'yicha
xom ashyogacha yoyiladi. Xom ashyo yetmasa 409 INSUFFICIENT_STOCK (ro'yxat bilan); `force=True` bilan
baribir tayyorlanadi (qoldiq minusga tushadi). Bekor qilish yechilgan xom ashyoni qaytaradi va
yarim tayyorni kamaytiradi.
"""
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product
from app.models.production_order import ProductionOrder, ProductionOrderStatus
from app.models.user import User

ZERO = Decimal("0")
Q3 = Decimal("0.001")
REF = "production_order"
MAX_QTY = Decimal("100000")


def _q(v) -> Decimal:
    return Decimal(str(v)).quantize(Q3, rounding=ROUND_HALF_UP)


def _semi(db: Session, company_id: int, product_id: int) -> Product:
    p = db.query(Product).filter(Product.id == product_id, Product.company_id == company_id,
                                 Product.is_deleted == False).first()  # noqa: E712
    if p is None:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    if p.item_kind != "semi":
        raise HTTPException(status_code=400, detail="Faqat yarim tayyor mahsulot tayyorlanadi")
    return p


def _kitchen(db: Session, company_id: int, branch_id: int):
    from app.services.restaurant import get_kitchen_warehouse
    wh = get_kitchen_warehouse(db, company_id, branch_id)
    if wh is None:
        raise HTTPException(status_code=409, detail="Filialda oshxona ombori yo'q")
    return wh


def _stock_map(db: Session, warehouse_id: int, pids) -> dict:
    if not pids:
        return {}
    rows = db.query(StockLevel.product_id, StockLevel.quantity).filter(
        StockLevel.warehouse_id == warehouse_id, StockLevel.product_id.in_(list(pids)),
        StockLevel.variant_id.is_(None)).all()
    out = {}
    for pid, q in rows:
        out[pid] = out.get(pid, ZERO) + Decimal(str(q or 0))
    return out


def plan(db: Session, company_id: int, branch_id: int, product_id: int, quantity, settings: dict) -> dict:
    """Tayyorlash rejasi: kerakli xom ashyo (yoyilgan), qoldiq, yetishmovchilik va tannarx. Hech narsa yozmaydi."""
    from app.services.restaurant_menu import CostCalc, active_card, money
    from app.services.restaurant_payment import expand_card
    product = _semi(db, company_id, product_id)
    try:
        qty = _q(quantity)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Miqdor noto'g'ri")
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Miqdor 0 dan katta bo'lishi kerak")
    if qty > MAX_QTY:
        raise HTTPException(status_code=400, detail="Miqdor juda katta")
    card = active_card(db, company_id, product.id)
    if card is None or not card.items:
        raise HTTPException(status_code=409, detail={"code": "NO_CARD",
                                                     "message": f"'{product.name}' uchun tex karta yo'q"})
    wh = _kitchen(db, company_id, branch_id)
    lines = expand_card(db, company_id, card, qty, wh.id, settings)
    stock = _stock_map(db, wh.id, set(lines) | {product.id})
    calc = CostCalc(db, company_id)
    rows = []
    total = ZERO
    for pid, (p, need) in sorted(lines.items(), key=lambda kv: kv[1][0].name.lower()):
        need = _q(need)
        if need <= 0:
            continue
        have = stock.get(pid, ZERO)
        uc = calc.unit_cost(p) if p.item_kind == "semi" else calc._own_cost(p)
        cost = need * uc
        total += cost
        rows.append({"product_id": p.id, "name": p.name, "kind": p.item_kind, "unit": p.unit,
                     "quantity": float(need), "available": float(have),
                     "shortage": float(max(need - have, ZERO)), "unit_cost": money(uc), "cost": money(cost),
                     "_p": p, "_need": need, "_uc": uc})
    return {
        "product": product, "card": card, "warehouse": wh, "quantity": qty, "lines": rows, "total": total,
        "unit_cost": (total / qty) if qty > 0 else ZERO, "stock": stock.get(product.id, ZERO),
    }


def plan_out(pl: dict) -> dict:
    from app.services.restaurant_menu import money
    p = pl["product"]
    return {
        "product_id": p.id, "name": p.name, "unit": p.unit, "quantity": float(pl["quantity"]),
        "card_version": pl["card"].version or 1, "card_output_qty": float(pl["card"].output_qty or 1),
        "warehouse_id": pl["warehouse"].id, "warehouse_name": pl["warehouse"].name,
        "stock": float(pl["stock"]),
        "lines": [{k: v for k, v in r.items() if not k.startswith("_")} for r in pl["lines"]],
        "total_cost": money(pl["total"]), "unit_cost": money(pl["unit_cost"]),
        "short": [r["name"] for r in pl["lines"] if r["shortage"] > 0],
    }


def _set_cost_price(db: Session, company_id: int, product: Product, unit_cost: Decimal) -> None:
    if unit_cost <= 0:
        return
    cur = (product.cost_currency or "UZS").strip().upper() or "UZS"
    if cur == "UZS":
        product.cost_price = round(unit_cost, 4)
    else:
        from app.services import supplier_ledger as ledger
        rate = ledger.currency_rate(db, company_id, cur)
        if rate and rate > 0:
            product.cost_price = round(unit_cost / rate, 4)


def produce(db: Session, user: User, branch_id: int, product_id: int, quantity, settings: dict, *,
            note: Optional[str] = None, force: bool = False) -> ProductionOrder:
    from app.services.inventory_service import deduct_stock, receive_stock
    from app.services.production_service import generate_production_number
    company_id = user.company_id
    pl = plan(db, company_id, branch_id, product_id, quantity, settings)
    short = [r for r in pl["lines"] if r["shortage"] > 0]
    if short and not force:
        raise HTTPException(status_code=409, detail={
            "code": "INSUFFICIENT_STOCK",
            "message": "Oshxona omborida xom ashyo yetmaydi: " + ", ".join(r["name"] for r in short),
            "lines": [{"product_id": r["product_id"], "name": r["name"], "unit": r["unit"],
                       "quantity": r["quantity"], "available": r["available"], "shortage": r["shortage"]}
                      for r in short],
        })
    product, card, wh, qty = pl["product"], pl["card"], pl["warehouse"], pl["quantity"]
    now = datetime.now(timezone.utc)
    order = ProductionOrder(
        number=generate_production_number(db, company_id, branch_id), bom_id=card.id, product_id=product.id,
        planned_quantity=qty, produced_quantity=qty, defect_quantity=ZERO,
        warehouse_id=wh.id, target_warehouse_id=wh.id, status=ProductionOrderStatus.completed,
        note=((note or "").strip()[:500] or None), created_by=user.id, company_id=company_id,
        started_at=now, completed_at=now,
    )
    db.add(order)
    db.flush()
    reason = f"Tayyorlash #{order.number}: {product.name} {qty.normalize():f} {product.unit or ''}".strip()
    for r in pl["lines"]:
        deduct_stock(db, r["product_id"], r["_need"], user.id, reason=reason, reference_type=REF,
                     reference_id=order.id, warehouse_id=wh.id, allow_negative=True)
    unit_cost = pl["unit_cost"]
    receive_stock(db, product.id, qty, user.id, reason=reason, reference_type=REF, reference_id=order.id,
                  warehouse_id=wh.id, purchase_price=unit_cost.quantize(Decimal("0.0001")), company_id=company_id,
                  production_order_id=order.id)
    order.unit_cost = unit_cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    order.total_cost = pl["total"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    _set_cost_price(db, company_id, product, unit_cost)
    db.flush()
    return order


def get_order(db: Session, company_id: int, branch_id: int, order_id: int) -> ProductionOrder:
    from app.models.warehouse import Warehouse
    o = (db.query(ProductionOrder).join(Warehouse, Warehouse.id == ProductionOrder.warehouse_id)
         .filter(ProductionOrder.id == order_id, ProductionOrder.company_id == company_id,
                 ProductionOrder.warehouse_id == ProductionOrder.target_warehouse_id,
                 Warehouse.branch_id == branch_id).first())
    if o is None:
        raise HTTPException(status_code=404, detail="Tayyorlash yozuvi topilmadi")
    return o


def cancel(db: Session, user: User, order: ProductionOrder) -> ProductionOrder:
    """Yechilgan xom ashyo qaytadi, yarim tayyor kamayadi (qoldiq minusga tushishi mumkin, ogohlantirish UI'da)."""
    from app.models.batch import Batch
    from app.services.inventory_service import deduct_stock, receive_stock
    locked = db.query(ProductionOrder).filter(ProductionOrder.id == order.id).with_for_update().first()
    if locked.status != ProductionOrderStatus.completed:
        raise HTTPException(status_code=400, detail="Bu yozuv allaqachon bekor qilingan")
    reason = f"Tayyorlash bekor qilindi #{locked.number}"
    moves = db.query(StockMovement).filter(StockMovement.reference_type == REF,
                                           StockMovement.reference_id == locked.id).all()
    for m in moves:
        q = Decimal(str(m.quantity or 0))
        if q <= 0:
            continue
        if m.type == MovementType.OUT:
            receive_stock(db, m.product_id, q, user.id, reason=reason, reference_type="production_cancel",
                          reference_id=locked.id, warehouse_id=m.warehouse_id, variant_id=m.variant_id)
        elif m.type == MovementType.IN:
            deduct_stock(db, m.product_id, q, user.id, reason=reason, reference_type="production_cancel",
                         reference_id=locked.id, warehouse_id=m.warehouse_id, allow_negative=True,
                         variant_id=m.variant_id)
    for b in db.query(Batch).filter(Batch.production_order_id == locked.id).all():
        b.quantity = ZERO
    locked.status = ProductionOrderStatus.cancelled
    db.flush()
    return locked


def history(db: Session, company_id: int, branch_id: int, *, date_from=None, date_to=None,
            product_id: Optional[int] = None, limit: int = 100) -> list:
    from app.models.user import User as U
    from app.models.warehouse import Warehouse
    q = (db.query(ProductionOrder, Product.name, Product.unit, U.name)
         .join(Warehouse, Warehouse.id == ProductionOrder.warehouse_id)
         .join(Product, Product.id == ProductionOrder.product_id)
         .outerjoin(U, U.id == ProductionOrder.created_by)
         .filter(ProductionOrder.company_id == company_id, Warehouse.branch_id == branch_id,
                 ProductionOrder.warehouse_id == ProductionOrder.target_warehouse_id,
                 Product.item_kind == "semi"))
    if date_from is not None:
        q = q.filter(ProductionOrder.created_at >= date_from)
    if date_to is not None:
        q = q.filter(ProductionOrder.created_at < date_to)
    if product_id:
        q = q.filter(ProductionOrder.product_id == product_id)
    return [_row(o, name, unit, uname) for o, name, unit, uname in q.order_by(ProductionOrder.id.desc()).limit(limit).all()]


def _row(o: ProductionOrder, name, unit, uname) -> dict:
    st = o.status.value if hasattr(o.status, "value") else o.status
    return {
        "id": o.id, "number": o.number, "product_id": o.product_id, "name": name, "unit": unit,
        "quantity": float(o.produced_quantity or 0), "unit_cost": float(o.unit_cost or 0),
        "total_cost": float(o.total_cost or 0), "status": st, "note": o.note, "user_name": uname,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def detail(db: Session, order: ProductionOrder) -> dict:
    from app.models.user import User as U
    p = db.get(Product, order.product_id)
    u = db.get(U, order.created_by) if order.created_by else None
    out = _row(order, p.name if p else None, p.unit if p else None, u.name if u else None)
    out["lines"] = lines_of(db, order.id)
    return out


def lines_of(db: Session, order_id: int) -> list:
    rows = (db.query(StockMovement, Product.name, Product.unit)
            .join(Product, Product.id == StockMovement.product_id)
            .filter(StockMovement.reference_type == REF, StockMovement.reference_id == order_id,
                    StockMovement.type == MovementType.OUT).order_by(Product.name).all())
    return [{"product_id": m.product_id, "name": n, "unit": u, "quantity": float(m.quantity or 0)}
            for m, n, u in rows]


def semis(db: Session, company_id: int, branch_id: int) -> list:
    """Yarim tayyor mahsulotlar: faol karta, chiqish miqdori, oshxonadagi qoldiq va 1 birlik tannarxi."""
    from app.services.restaurant_menu import CostCalc, active_card, money
    wh = _kitchen(db, company_id, branch_id)
    items = db.query(Product).filter(Product.company_id == company_id, Product.item_kind == "semi",
                                     Product.is_deleted == False).order_by(Product.name).all()  # noqa: E712
    stock = _stock_map(db, wh.id, {p.id for p in items})
    calc = CostCalc(db, company_id)
    out = []
    for p in items:
        card = active_card(db, company_id, p.id)
        out.append({
            "id": p.id, "name": p.name, "unit": p.unit, "has_card": bool(card and card.items),
            "output_qty": float(card.output_qty or 1) if card else None,
            "stock": float(stock.get(p.id, ZERO)), "unit_cost": money(calc.unit_cost(p)),
            "min_stock": float(p.min_stock or 0) if getattr(p, "min_stock", None) is not None else 0,
        })
    return out
