"""Restoran: tannarxni qayta hisoblash va food cost nazorati (R7.5).

Tex karta tannarxi har doim joriy ingredient narxidan hisoblanadi (`CostCalc`), shuning uchun kirimdan keyin
kartalar o'zi yangilanadi. Bu modul o'zgarishni qayd etadi: kirimdan oldin eski tannarxlar olinadi (`snapshot`),
keyin (`record`) narxi o'zgargan ingredientlar ishlatiladigan taom va yarim tayyorlar (ichma-ich kartalar orqali
ham) topiladi, eski va yangi tannarx, food cost % va chegaradan oshgani `restaurant_cost_changes` ga yoziladi.

Do'kon korxonasida `snapshot` None qaytaradi va hech narsa yozilmaydi.
"""
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.bom import BOM, BOMItem
from app.models.product import Product
from app.models.restaurant import RestaurantCostChange

ZERO = Decimal("0")
MAX_DEPTH = 8
SOURCES = ("purchase", "receive", "manual")


def _threshold(db: Session, company_id: int) -> Decimal:
    from app.models.company import Company
    from app.services.restaurant import restaurant_settings_of
    v = restaurant_settings_of(db.get(Company, company_id)).get("food_cost_alert_pct", 35)
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return Decimal("35")


def snapshot(db: Session, company_id: Optional[int], product_ids: Iterable) -> Optional[dict]:
    """Kirimdan oldin: {product_id: cost_price}. Restoran bo'lmasa None."""
    from app.services.restaurant import is_restaurant
    ids = {int(p) for p in product_ids if p}
    if not ids or not is_restaurant(db, company_id):
        return None
    rows = db.query(Product.id, Product.cost_price).filter(Product.company_id == company_id, Product.id.in_(ids)).all()
    return {pid: (Decimal(str(c)) if c is not None else None) for pid, c in rows}


def affected_products(db: Session, company_id: int, changed_ids: Iterable[int]) -> list:
    """Faol kartasida (to'g'ridan-to'g'ri yoki yarim tayyor orqali) shu mahsulotlar bor taom va yarim tayyorlar."""
    seen = set()
    frontier = set(changed_ids)
    depth = 0
    while frontier and depth <= MAX_DEPTH:
        rows = (db.query(BOM.product_id).join(BOMItem, BOMItem.bom_id == BOM.id)
                .filter(BOM.company_id == company_id, BOM.is_active == True,  # noqa: E712
                        BOMItem.component_product_id.in_(list(frontier))).distinct().all())
        nxt = {r[0] for r in rows} - seen
        seen |= nxt
        frontier = nxt
        depth += 1
    if not seen:
        return []
    return (db.query(Product).filter(Product.id.in_(list(seen)), Product.company_id == company_id,
                                     Product.is_deleted == False,  # noqa: E712
                                     Product.item_kind.in_(("dish", "semi"))).all())


def _pct(cost: Decimal, price) -> Optional[float]:
    price = Decimal(str(price or 0))
    if price <= 0:
        return None
    return float((cost / price * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _m(v: Decimal) -> float:
    return float(Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def suggested_price(cost: Decimal, threshold: Decimal) -> Optional[float]:
    """Food cost chegarasiga tushish uchun eng kam sotuv narxi (100 so'mga yuqoriga yaxlitlangan)."""
    if threshold <= 0 or cost <= 0:
        return None
    raw = cost * 100 / threshold
    return float((raw / 100).to_integral_value(rounding=ROUND_CEILING) * 100)


def record(db: Session, company_id: Optional[int], before: Optional[dict], source: str,
           reference_id: Optional[int] = None, user_id: Optional[int] = None) -> Optional[RestaurantCostChange]:
    """Kirimdan keyin: tannarxi o'zgargan ingredientlar va ta'sirlangan kartalar. Hech qaysi karta tannarxi
    o'zgarmagan bo'lsa yozilmaydi (None)."""
    from app.services.restaurant_menu import CostCalc
    if not before:
        return None
    db.flush()
    current = {pid: (Decimal(str(c)) if c is not None else None) for pid, c in
               db.query(Product.id, Product.cost_price).filter(Product.id.in_(list(before))).all()}
    changed = {pid: old for pid, old in before.items() if (old or ZERO) != (current.get(pid) or ZERO)}
    if not changed:
        return None
    new_calc = CostCalc(db, company_id)
    old_calc = CostCalc(db, company_id, overrides=changed)
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(list(changed))).all()}
    ingredients = []
    for pid in sorted(changed, key=lambda i: products[i].name.lower() if i in products else ""):
        p = products.get(pid)
        if p is None:
            continue
        ingredients.append({"product_id": pid, "name": p.name, "unit": p.unit,
                            "old": _m(old_calc._own_cost(p)), "new": _m(new_calc._own_cost(p))})
    threshold = _threshold(db, company_id)
    dishes = []
    for p in affected_products(db, company_id, changed):
        old_c, new_c = old_calc.unit_cost(p), new_calc.unit_cost(p)
        if _m(old_c) == _m(new_c):
            continue
        is_dish = p.item_kind == "dish"
        new_pct = _pct(new_c, p.sale_price) if is_dish else None
        dishes.append({
            "product_id": p.id, "name": p.name, "kind": p.item_kind, "unit": p.unit,
            "price": _m(Decimal(str(p.sale_price or 0))) if is_dish else None,
            "old_cost": _m(old_c), "new_cost": _m(new_c),
            "old_pct": _pct(old_c, p.sale_price) if is_dish else None, "new_pct": new_pct,
            "over": bool(new_pct is not None and Decimal(str(new_pct)) > threshold),
        })
    if not dishes:
        return None                      # hech qaysi faol kartaga ta'sir qilmadi
    dishes.sort(key=lambda d: (d["kind"] != "dish", -(d["new_pct"] or 0), d["name"].lower()))
    ev = RestaurantCostChange(company_id=company_id, source=source if source in SOURCES else "manual",
                              reference_id=reference_id, user_id=user_id, threshold=threshold,
                              ingredients=ingredients, dishes=dishes, over_count=sum(1 for d in dishes if d["over"]))
    db.add(ev)
    db.flush()
    return ev


def overview(db: Session, company_id: int) -> dict:
    """Hozirgi holat: kartasi bor barcha taomlar tannarxi va food cost %, chegaradan oshganlari birinchi."""
    from app.services.restaurant_menu import CostCalc, active_card
    threshold = _threshold(db, company_id)
    calc = CostCalc(db, company_id)
    items = db.query(Product).filter(Product.company_id == company_id, Product.item_kind == "dish",
                                     Product.is_deleted == False).all()  # noqa: E712
    out = []
    for p in items:
        card = active_card(db, company_id, p.id)
        if card is None or not card.items:
            continue
        cost = calc.unit_cost(p)
        pct = _pct(cost, p.sale_price)
        over = pct is not None and Decimal(str(pct)) > threshold
        out.append({
            "product_id": p.id, "name": p.name, "price": _m(Decimal(str(p.sale_price or 0))), "cost": _m(cost),
            "pct": pct, "over": over, "no_price": pct is None,
            "suggested_price": suggested_price(cost, threshold) if over else None,
        })
    out.sort(key=lambda d: (not d["over"], not d["no_price"], -(d["pct"] or 0), d["name"].lower()))
    return {"threshold": float(threshold), "dishes": out, "over_count": sum(1 for d in out if d["over"])}


def change_out(ev: RestaurantCostChange, user_name: Optional[str] = None) -> dict:
    return {
        "id": ev.id, "source": ev.source, "reference_id": ev.reference_id, "user_name": user_name,
        "threshold": float(ev.threshold) if ev.threshold is not None else None,
        "ingredients": ev.ingredients or [], "dishes": ev.dishes or [], "over_count": ev.over_count or 0,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


def list_changes(db: Session, company_id: int, limit: int = 50) -> list:
    from app.models.user import User
    rows = (db.query(RestaurantCostChange, User.name).outerjoin(User, User.id == RestaurantCostChange.user_id)
            .filter(RestaurantCostChange.company_id == company_id)
            .order_by(RestaurantCostChange.id.desc()).limit(limit).all())
    return [change_out(ev, uname) for ev, uname in rows]
