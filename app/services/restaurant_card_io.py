"""Tex kartalarni Excel orqali eksport va import qilish (R1.2, 2-bosqich).

Fayl brauzerda o'qiladi va yoziladi (xlsx); server qatorlar bilan ishlaydi. Bir qator = kartaning bitta ingredienti:
    dish, dish_code, kind, output_qty, output_weight_g, cooking_time_min,
    ingredient, ingredient_code, unit, gross, net, loss_cold, loss_hot, price, row
Taom va ingredient avval kodi (SKU), bo'lmasa nomi bo'yicha (katta-kichik harf farqsiz) topiladi; bir xil nomli
bir nechta mahsulot bo'lsa xato. `create_missing` bilan topilmagan taom (turi ustunidan) va ingredient (birlik,
narx bilan) yaratiladi. Yarim tayyorlar taomlardan oldin saqlanadi. Har taom alohida SAVEPOINT da: xato boshqasiga
ta'sir qilmaydi. Karta o'zgarmagan bo'lsa yangi versiya ochilmaydi.
"""
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.restaurant_menu import (CARD_KINDS, COMPONENT_KINDS, UNITS, CostCalc, active_card, create_item,
                                          money, save_card)

MAX_ROWS = 5000
MAX_CARDS = 500
KIND_ALIASES = {
    "dish": "dish", "taom": "dish", "блюдо": "dish",
    "semi": "semi", "yarim tayyor": "semi", "yarimtayyor": "semi", "полуфабрикат": "semi", "semi-finished": "semi",
}
UNIT_ALIASES = {"кг": "kg", "г": "g", "гр": "g", "л": "l", "мл": "ml", "шт": "dona", "порция": "porsiya",
                "pcs": "dona", "piece": "dona", "portion": "porsiya", "gr": "g"}


def _s(v) -> str:
    return ("" if v is None else str(v)).strip()


def _num(v, label: str, errors: list, row, *, required: bool = False) -> Optional[Decimal]:
    s = _s(v).replace(" ", "").replace(" ", "").replace(",", ".")
    if not s:
        if required:
            errors.append({"row": row, "message": f"{label}: qiymat kerak"})
        return None
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        errors.append({"row": row, "message": f"{label}: son emas ({v})"})
        return None
    if not d.is_finite() or d < 0:
        errors.append({"row": row, "message": f"{label}: manfiy bo'lmasin"})
        return None
    return d


def _fmt(d) -> Optional[float]:
    return float(d) if d is not None else None


# ── eksport ───────────────────────────────────────────────────────

def export_rows(db: Session, company_id: int) -> list:
    calc = CostCalc(db, company_id)
    items = (db.query(Product).filter(Product.company_id == company_id, Product.is_deleted == False,  # noqa: E712
                                      Product.item_kind.in_(CARD_KINDS))
             .order_by(Product.item_kind.desc(), Product.name).all())          # yarim tayyor avval
    out = []
    for p in items:
        card = active_card(db, company_id, p.id)
        if card is None or not card.items:
            continue
        for it in card.items:
            c = it.component_product
            gross = it.gross_qty if it.gross_qty is not None else it.quantity_per_unit
            uc = calc.unit_cost(c)
            out.append({
                "dish": p.name, "dish_code": p.sku, "kind": p.item_kind,
                "output_qty": _fmt(card.output_qty or 1), "output_weight_g": _fmt(card.output_weight_g),
                "cooking_time_min": card.cooking_time_min, "version": card.version or 1,
                "ingredient": c.name, "ingredient_code": c.sku, "unit": c.unit,
                "gross": _fmt(gross), "net": _fmt(it.net_qty), "loss_cold": _fmt(it.loss_cold_pct),
                "loss_hot": _fmt(it.loss_hot_pct), "price": money(uc), "line_cost": money(Decimal(str(gross)) * uc),
                "sale_price": money(Decimal(str(p.sale_price or 0))) if p.item_kind == "dish" else None,
            })
    return out


# ── import ────────────────────────────────────────────────────────

class _Index:
    def __init__(self, db: Session, company_id: int):
        self.by_code, self.by_name = {}, {}
        for p in db.query(Product).filter(Product.company_id == company_id, Product.is_deleted == False):  # noqa: E712
            self.add(p)

    def add(self, p: Product):
        if p.sku:
            self.by_code[p.sku.strip().lower()] = p
        self.by_name.setdefault(p.name.strip().lower(), []).append(p)

    def find(self, name: str, code: str) -> tuple:
        """(mahsulot | None, xato | None)"""
        if code:
            p = self.by_code.get(code.lower())
            if p is not None:
                return p, None
        if not name:
            return None, (f"kod topilmadi: {code}" if code else "nomi bo'sh")
        hits = self.by_name.get(name.lower(), [])
        if len(hits) > 1:
            return None, f"'{name}' nomli {len(hits)} ta mahsulot bor: kodini yozing"
        return (hits[0], None) if hits else (None, None)


def _card_signature(card) -> Optional[tuple]:
    if card is None or not card.items:
        return None
    rows = sorted(((it.component_product_id,
                    Decimal(str(it.gross_qty if it.gross_qty is not None else it.quantity_per_unit)),
                    Decimal(str(it.net_qty)) if it.net_qty is not None else None,
                    Decimal(str(it.loss_cold_pct)) if it.loss_cold_pct is not None else None,
                    Decimal(str(it.loss_hot_pct)) if it.loss_hot_pct is not None else None) for it in card.items),
                  key=lambda x: (x[0], str(x[1:])))
    return (Decimal(str(card.output_qty or 1)),
            Decimal(str(card.output_weight_g)) if card.output_weight_g is not None else None,
            card.cooking_time_min, tuple(rows))


def _data_signature(data: dict) -> tuple:
    rows = sorted(((r["component_product_id"], r["gross_qty"], r["net_qty"], r["loss_cold_pct"], r["loss_hot_pct"])
                   for r in data["items"]), key=lambda x: (x[0], str(x[1:])))
    return (data["output_qty"] or Decimal("1"), data["output_weight_g"], data["cooking_time_min"], tuple(rows))


def import_cards(db: Session, user, rows: list, create_missing: bool = False) -> dict:
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="Faylda qator yo'q")
    if len(rows) > MAX_ROWS:
        raise HTTPException(status_code=400, detail=f"{MAX_ROWS} qatordan ko'p bo'lmasin")
    company_id = user.company_id
    errors = []
    groups = OrderedDict()
    for i, r in enumerate(rows, start=2):
        if not isinstance(r, dict):
            continue
        row = r.get("row") or i
        dish, ing = _s(r.get("dish")), _s(r.get("ingredient"))
        if not dish and not ing:
            continue                                   # bo'sh qator
        if not dish:
            errors.append({"row": row, "message": "Taom nomi bo'sh"})
            continue
        if not ing and not _s(r.get("ingredient_code")):
            errors.append({"row": row, "message": "Ingredient nomi bo'sh"})
            continue
        key = (_s(r.get("dish_code")).lower() or dish.lower())
        g = groups.setdefault(key, {"dish": dish, "dish_code": _s(r.get("dish_code")), "kind": None,
                                    "output_qty": None, "output_weight_g": None, "cooking_time_min": None,
                                    "lines": [], "rows": [], "bad": False})
        kind_raw = _s(r.get("kind")).lower()
        if kind_raw:
            kind = KIND_ALIASES.get(kind_raw)
            if kind is None:
                errors.append({"row": row, "message": f"Turi noto'g'ri: {r.get('kind')} (taom yoki yarim tayyor)"})
                g["bad"] = True
            elif g["kind"] is None:
                g["kind"] = kind
        n_err = len(errors)
        for f, label in (("output_qty", "Chiqish"), ("output_weight_g", "Og'irlik")):
            v = _num(r.get(f), label, errors, row)
            if v is not None and g[f] is None:
                g[f] = v
        ct = _num(r.get("cooking_time_min"), "Tayyorlash vaqti", errors, row)
        if ct is not None and g["cooking_time_min"] is None:
            g["cooking_time_min"] = int(ct)
        gross = _num(r.get("gross"), "Brutto", errors, row, required=True)
        net = _num(r.get("net"), "Netto", errors, row)
        lc = _num(r.get("loss_cold"), "Sovuq yo'qotish", errors, row)
        lh = _num(r.get("loss_hot"), "Issiq yo'qotish", errors, row)
        price = _num(r.get("price"), "Narx", errors, row)
        unit = _s(r.get("unit")).lower()
        unit = UNIT_ALIASES.get(unit, unit)
        if unit and unit not in UNITS:
            errors.append({"row": row, "message": f"Birlik noto'g'ri: {r.get('unit')}"})
            unit = ""
        if len(errors) > n_err or gross is None:
            g["bad"] = True
            continue
        g["rows"].append(row)
        g["lines"].append({"name": ing, "code": _s(r.get("ingredient_code")), "gross": gross, "net": net,
                           "lc": lc, "lh": lh, "unit": unit, "price": price, "row": row})
    if len(groups) > MAX_CARDS:
        raise HTTPException(status_code=400, detail=f"Bir importda {MAX_CARDS} tadan ko'p karta bo'lmasin")

    idx = _Index(db, company_id)
    created_dishes, created_ings = [], []
    result = []
    # 1) taomlar va yarim tayyorlar
    for key, g in groups.items():
        p, err = idx.find(g["dish"], g["dish_code"])
        g["product"] = None
        if err:
            g["error"] = err
            continue
        if p is None:
            if not create_missing:
                g["error"] = "Menyuda topilmadi (yaratish belgilanmagan)"
                continue
            p = create_item(db, company_id, {"name": g["dish"], "kind": g["kind"] or "dish"})
            idx.add(p)
            created_dishes.append(p.name)
        elif p.item_kind not in CARD_KINDS:
            g["error"] = f"'{p.name}' taom yoki yarim tayyor emas"
            continue
        g["product"] = p
    # 2) ingredientlar
    for g in groups.values():
        if g.get("product") is None:
            continue
        for ln in g["lines"]:
            c, err = idx.find(ln["name"], ln["code"])
            if err:
                errors.append({"row": ln["row"], "message": f"Ingredient: {err}"})
                g["bad"] = True
                continue
            if c is None:
                if not create_missing:
                    errors.append({"row": ln["row"], "message": f"Ingredient topilmadi: {ln['name']}"})
                    g["bad"] = True
                    continue
                c = create_item(db, company_id, {"name": ln["name"], "kind": "ingredient", "unit": ln["unit"] or "kg",
                                                 "cost_price": ln["price"]})
                idx.add(c)
                created_ings.append(c.name)
            elif c.item_kind not in COMPONENT_KINDS:
                errors.append({"row": ln["row"], "message": f"'{c.name}' ingredient sifatida ishlatilmaydi"})
                g["bad"] = True
                continue
            ln["product"] = c
    # 3) kartalar: yarim tayyorlar avval
    order = sorted(groups.values(), key=lambda g: 0 if g.get("product") is not None and g["product"].item_kind == "semi" else 1)
    for g in order:
        p = g.get("product")
        out = {"name": g["dish"], "rows": len(g["rows"]), "kind": p.item_kind if p is not None else g["kind"]}
        if p is None or g.get("error"):
            result.append({**out, "status": "error", "error": g.get("error") or "Xato"})
            continue
        if g["bad"]:
            result.append({**out, "status": "error", "error": "Qatorlarda xato bor (pastda)"})
            continue
        data = {"output_qty": g["output_qty"], "output_weight_g": g["output_weight_g"],
                "cooking_time_min": g["cooking_time_min"],
                "items": [{"component_product_id": ln["product"].id, "gross_qty": ln["gross"], "net_qty": ln["net"],
                           "loss_cold_pct": ln["lc"], "loss_hot_pct": ln["lh"]} for ln in g["lines"]]}
        prev = active_card(db, company_id, p.id)
        if prev is not None and _card_signature(prev) == _data_signature(data):
            result.append({**out, "status": "unchanged", "version": prev.version or 1})
            continue
        try:
            with db.begin_nested():
                card = save_card(db, company_id, p, data, user.id)
            result.append({**out, "status": "updated" if prev is not None else "created", "version": card.version})
        except HTTPException as e:
            result.append({**out, "status": "error", "error": e.detail if isinstance(e.detail, str) else str(e.detail)})
    summary = {k: sum(1 for r in result if r["status"] == k) for k in ("created", "updated", "unchanged", "error")}
    return {"cards": result, "row_errors": sorted(errors, key=lambda e: (int(e["row"]) if str(e["row"]).isdigit() else 0)),
            "created_dishes": created_dishes, "created_ingredients": created_ings, "summary": summary}
