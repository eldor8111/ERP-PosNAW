"""Restoran menyusi (R1.1, R1.2, R1.4): taom/ingredient yaratish, texnologik karta versiyalari, tannarx.

Texnologik karta mavjud `boms` / `bom_items` jadvallarida saqlanadi (ishlab chiqarish moduli bilan bir xil):
  * karta `output_qty` birlik mahsulot beradi (taom uchun 1 porsiya, yarim tayyor uchun masalan 5 kg);
  * qator `gross_qty` (brutto) — butun karta uchun; ombordan brutto yechiladi;
  * `quantity_per_unit = gross_qty / output_qty` — 1 birlik mahsulot uchun (ishlab chiqarish va R7.1 yechish shuni oladi).
Karta o'zgarsa yangi versiya yaratiladi, eskisi `is_active = False` bo'lib qoladi (eski sotuvlar eski versiyaga bog'liq).
"""
import random
import string
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.bom import BOM, BOMItem
from app.models.category import Category
from app.models.product import Product, ProductStatus
from app.models.restaurant import KitchenStation

ITEM_KINDS = ("goods", "dish", "semi", "ingredient", "modifier")
# Tex kartasi bo'lishi mumkin bo'lgan turlar
CARD_KINDS = ("dish", "semi")
# Tex karta tarkibiga kira oladigan turlar
COMPONENT_KINDS = ("ingredient", "semi", "goods")
# O'z qoldig'i yuritilmaydigan turlar (taom ingredientlari yechiladi)
NO_STOCK_KINDS = ("dish", "modifier")
UNITS = ("dona", "porsiya", "kg", "g", "l", "ml")
MAX_DEPTH = 8

ZERO = Decimal("0")
ONE = Decimal("1")


def _dec(v, field: str, *, positive: bool = False, allow_none: bool = True) -> Optional[Decimal]:
    if v is None or v == "":
        if allow_none:
            return None
        raise HTTPException(status_code=400, detail=f"{field}: qiymat kiritilishi shart")
    try:
        d = Decimal(str(v))
    except Exception:
        raise HTTPException(status_code=400, detail=f"{field}: son bo'lishi kerak")
    if not d.is_finite() or d < 0 or (positive and d == 0):
        raise HTTPException(status_code=400, detail=f"{field}: {'musbat' if positive else 'manfiy emas'} son bo'lishi kerak")
    return d


def _new_code(db: Session, company_id: int, prefix: str, column) -> str:
    for _ in range(30):
        code = prefix + "".join(random.choices(string.digits, k=9))
        exists = db.query(Product.id).filter(Product.company_id == company_id, column == code,
                                             Product.is_deleted == False).first()  # noqa: E712
        if not exists:
            return code
    raise HTTPException(status_code=500, detail="Ichki kod yaratib bo'lmadi")


def get_item(db: Session, company_id: int, product_id: int) -> Product:
    p = db.query(Product).filter(Product.id == product_id, Product.company_id == company_id,
                                 Product.is_deleted == False).first()  # noqa: E712
    if p is None:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    return p


def _check_category(db: Session, company_id: int, category_id):
    if category_id is None:
        return None
    ok = db.query(Category.id).filter(Category.id == category_id, Category.company_id == company_id,
                                      Category.is_deleted == False).first()  # noqa: E712
    if not ok:
        raise HTTPException(status_code=400, detail="Kategoriya topilmadi")
    return category_id


def check_station(db: Session, company_id: int, station_id):
    if station_id is None:
        return None
    ok = db.query(KitchenStation.id).filter(KitchenStation.id == station_id,
                                            KitchenStation.company_id == company_id).first()
    if not ok:
        raise HTTPException(status_code=400, detail="Sex topilmadi")
    return station_id


def apply_item_fields(db: Session, company_id: int, p: Product, data: dict, creating: bool) -> None:
    if "name" in data or creating:
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Nomi kiritilishi shart")
        if len(name) > 200:
            raise HTTPException(status_code=400, detail="Nomi 200 belgidan oshmasin")
        p.name = name
    if "kind" in data or creating:
        kind = data.get("kind") or "dish"
        if kind not in ITEM_KINDS:
            raise HTTPException(status_code=400, detail="Turi noto'g'ri")
        if not creating and kind != p.item_kind and kind not in CARD_KINDS and active_card(db, company_id, p.id):
            raise HTTPException(status_code=400, detail="Tex kartasi bor mahsulot faqat taom yoki yarim tayyor bo'la oladi")
        p.item_kind = kind
        p.product_type = "service" if kind in NO_STOCK_KINDS else "simple"
    if "unit" in data or creating:
        unit = (data.get("unit") or ("porsiya" if p.item_kind == "dish" else "kg" if p.item_kind in ("ingredient", "semi") else "dona"))
        unit = unit.strip().lower()
        if unit not in UNITS:
            raise HTTPException(status_code=400, detail="Birlik noto'g'ri")
        p.unit = unit
    if "category_id" in data:
        p.category_id = _check_category(db, company_id, data.get("category_id"))
    if "station_id" in data:
        p.station_id = check_station(db, company_id, data.get("station_id"))
    if "sale_price" in data or creating:
        p.sale_price = _dec(data.get("sale_price"), "Sotuv narxi") or ZERO
    if "cost_price" in data or creating:
        p.cost_price = _dec(data.get("cost_price"), "Tannarx") or ZERO
    if "is_active" in data and data["is_active"] is not None:
        p.status = ProductStatus.active if data["is_active"] else ProductStatus.inactive


def create_item(db: Session, company_id: int, data: dict) -> Product:
    p = Product(company_id=company_id, sale_currency="UZS", cost_currency="UZS", wholesale_currency="UZS")
    apply_item_fields(db, company_id, p, data, creating=True)
    p.sku = _new_code(db, company_id, "RM-", Product.sku)
    # Taomlar uchun ichki kod (skaner uchun emas); haqiqiy shtrix-kod berilsa o'sha
    barcode = (data.get("barcode") or "").strip()
    if barcode:
        dup = db.query(Product.id).filter(Product.company_id == company_id, Product.barcode == barcode,
                                          Product.is_deleted == False).first()  # noqa: E712
        if dup:
            raise HTTPException(status_code=409, detail="Bu shtrix-kod boshqa mahsulotda bor")
        p.barcode = barcode
    else:
        p.barcode = _new_code(db, company_id, "29", Product.barcode)
    db.add(p)
    db.flush()
    return p


def active_card(db: Session, company_id: int, product_id: int) -> Optional[BOM]:
    return (db.query(BOM).filter(BOM.company_id == company_id, BOM.product_id == product_id,
                                 BOM.is_active == True)  # noqa: E712
            .order_by(BOM.id.desc()).first())


def _reaches(db: Session, company_id: int, start_id: int, target_id: int, seen: set, depth: int = 0) -> bool:
    """start_id ning faol kartasi (ichma-ich) target_id ga yetadimi (aylana bog'lanish tekshiruvi)."""
    if start_id == target_id:
        return True
    if depth > MAX_DEPTH or start_id in seen:
        return False
    seen.add(start_id)
    card = active_card(db, company_id, start_id)
    if card is None:
        return False
    return any(_reaches(db, company_id, it.component_product_id, target_id, seen, depth + 1) for it in card.items)


def save_card(db: Session, company_id: int, product: Product, data: dict, user_id: Optional[int]) -> BOM:
    """Yangi versiya yaratadi va faol qiladi. Avvalgi faol versiya o'chiriladi (o'chirilmaydi, tarix uchun qoladi)."""
    if product.item_kind not in CARD_KINDS:
        raise HTTPException(status_code=400, detail="Tex karta faqat taom yoki yarim tayyor mahsulot uchun")
    output_qty = _dec(data.get("output_qty"), "Chiqish miqdori", positive=True) or ONE
    weight = _dec(data.get("output_weight_g"), "Porsiya og'irligi")
    cook = data.get("cooking_time_min")
    if cook is not None and cook != "":
        try:
            cook = int(cook)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Tayyorlash vaqti butun son bo'lishi kerak")
        if not 0 <= cook <= 1440:
            raise HTTPException(status_code=400, detail="Tayyorlash vaqti 0 dan 1440 daqiqagacha")
    else:
        cook = None
    rows = data.get("items") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="Tex kartada kamida bitta ingredient bo'lishi kerak")
    if len(rows) > 200:
        raise HTTPException(status_code=400, detail="Tex kartada 200 tadan ko'p qator bo'lmasin")

    seen_ids = set()
    parsed = []
    for i, r in enumerate(rows, start=1):
        if not isinstance(r, dict):
            raise HTTPException(status_code=400, detail=f"{i}-qator noto'g'ri")
        try:
            cid = int(r.get("component_product_id"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{i}-qator: ingredient tanlanmagan")
        if cid in seen_ids:
            raise HTTPException(status_code=400, detail=f"{i}-qator: ingredient takrorlangan")
        seen_ids.add(cid)
        comp = db.query(Product).filter(Product.id == cid, Product.company_id == company_id,
                                        Product.is_deleted == False).first()  # noqa: E712
        if comp is None:
            raise HTTPException(status_code=400, detail=f"{i}-qator: ingredient topilmadi")
        if comp.item_kind not in COMPONENT_KINDS:
            raise HTTPException(status_code=400, detail=f"{i}-qator: '{comp.name}' ingredient sifatida ishlatilmaydi")
        if _reaches(db, company_id, comp.id, product.id, set()):
            raise HTTPException(status_code=400, detail=f"{i}-qator: '{comp.name}' aylana bog'lanish hosil qiladi")
        gross = _dec(r.get("gross_qty"), f"{i}-qator brutto", positive=True, allow_none=False)
        net = _dec(r.get("net_qty"), f"{i}-qator netto")
        if net is not None and net > gross:
            raise HTTPException(status_code=400, detail=f"{i}-qator: netto bruttodan katta bo'lmasin")
        lc = _dec(r.get("loss_cold_pct"), f"{i}-qator sovuq ishlov yo'qotishi")
        lh = _dec(r.get("loss_hot_pct"), f"{i}-qator issiq ishlov yo'qotishi")
        for v, nm in ((lc, "sovuq"), (lh, "issiq")):
            if v is not None and v >= 100:
                raise HTTPException(status_code=400, detail=f"{i}-qator: {nm} ishlov yo'qotishi 100% dan kam bo'lsin")
        parsed.append((comp, gross, net, lc, lh))

    prev = active_card(db, company_id, product.id)
    version = 1
    if prev is not None:
        version = (prev.version or 1) + 1
        db.query(BOM).filter(BOM.company_id == company_id, BOM.product_id == product.id,
                             BOM.is_active == True).update({BOM.is_active: False}, synchronize_session=False)  # noqa: E712
    card = BOM(product_id=product.id, company_id=company_id, name=f"{product.name} (v{version})", is_active=True,
               output_qty=output_qty, output_weight_g=weight, cooking_time_min=cook,
               instructions=(data.get("instructions") or "").strip()[:5000] or None,
               version=version, created_by=user_id)
    db.add(card)
    db.flush()
    for comp, gross, net, lc, lh in parsed:
        db.add(BOMItem(bom_id=card.id, component_product_id=comp.id,
                       quantity_per_unit=(gross / output_qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                       gross_qty=gross, net_qty=net, loss_cold_pct=lc, loss_hot_pct=lh))
    db.flush()
    db.refresh(card)
    return card


class CostCalc:
    """Tannarx hisoblagichi (UZS). Ingredient: mahsulot tannarxi; yarim tayyor: faol kartasi bo'lsa karta bo'yicha."""

    def __init__(self, db: Session, company_id: int):
        from app.services.currency_service import rate_map
        self.db = db
        self.company_id = company_id
        self.rates = rate_map(db, company_id)
        self._cache = {}

    def _own_cost(self, p: Product) -> Decimal:
        from app.services.currency_service import to_uzs
        return to_uzs(p.cost_price or 0, p.cost_currency, self.rates)

    def unit_cost(self, p: Product, depth: int = 0) -> Decimal:
        """1 birlik mahsulot tannarxi."""
        if p.id in self._cache:
            return self._cache[p.id]
        cost = self._own_cost(p)
        if p.item_kind in CARD_KINDS and depth <= MAX_DEPTH:
            card = active_card(self.db, self.company_id, p.id)
            if card is not None and card.items:
                cost = self.card_total(card, depth + 1) / Decimal(str(card.output_qty or 1))
        self._cache[p.id] = cost
        return cost

    def card_total(self, card: BOM, depth: int = 0) -> Decimal:
        total = ZERO
        for it in card.items:
            total += Decimal(str(it.gross_qty if it.gross_qty is not None else it.quantity_per_unit)) * \
                self.unit_cost(it.component_product, depth)
        return total


def money(d: Decimal) -> float:
    return float(Decimal(d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def food_cost_pct(cost: Decimal, price) -> Optional[float]:
    price = Decimal(str(price or 0))
    if price <= 0:
        return None
    return float((cost / price * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def card_out(db: Session, company_id: int, product: Product, card: Optional[BOM], calc: Optional[CostCalc] = None) -> dict:
    calc = calc or CostCalc(db, company_id)
    if card is None:
        return {"product_id": product.id, "card": None, "unit_cost": money(calc.unit_cost(product)),
                "food_cost_pct": None}
    out_qty = Decimal(str(card.output_qty or 1))
    rows = []
    for it in card.items:
        c = it.component_product
        uc = calc.unit_cost(c)
        gross = Decimal(str(it.gross_qty if it.gross_qty is not None else it.quantity_per_unit))
        rows.append({
            "id": it.id, "component_product_id": c.id, "name": c.name, "kind": c.item_kind, "unit": c.unit,
            "gross_qty": float(gross), "net_qty": float(it.net_qty) if it.net_qty is not None else None,
            "loss_cold_pct": float(it.loss_cold_pct) if it.loss_cold_pct is not None else None,
            "loss_hot_pct": float(it.loss_hot_pct) if it.loss_hot_pct is not None else None,
            "unit_cost": money(uc), "line_cost": money(gross * uc),
        })
    total = calc.card_total(card)
    unit_cost = total / out_qty
    return {
        "product_id": product.id,
        "card": {
            "id": card.id, "version": card.version or 1, "output_qty": float(out_qty),
            "output_weight_g": float(card.output_weight_g) if card.output_weight_g is not None else None,
            "cooking_time_min": card.cooking_time_min, "instructions": card.instructions,
            "created_at": card.created_at.isoformat() if card.created_at else None,
            "items": rows,
        },
        "total_cost": money(total),
        "unit_cost": money(unit_cost),
        "food_cost_pct": food_cost_pct(unit_cost, product.sale_price) if product.item_kind == "dish" else None,
    }


def used_in_cards(db: Session, company_id: int, product_id: int) -> list:
    """Shu mahsulot qaysi faol kartalarda ishlatiladi (o'chirishdan oldin tekshiruv)."""
    rows = (db.query(Product.name).join(BOM, BOM.product_id == Product.id)
            .join(BOMItem, BOMItem.bom_id == BOM.id)
            .filter(BOM.company_id == company_id, BOM.is_active == True,  # noqa: E712
                    BOMItem.component_product_id == product_id).all())
    return sorted({r[0] for r in rows})
