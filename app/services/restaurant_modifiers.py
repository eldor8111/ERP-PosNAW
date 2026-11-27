"""Taom qo'shimchalari (R1.3): guruhlar, variantlar, taomga biriktirish va buyurtmada tanlovni tekshirish.

Guruh: nomi, min_select (0 = ixtiyoriy, 1+ = majburiy), max_select. Variant: nomi, qo'shimcha narx, ixtiyoriy
bog'langan mahsulot va miqdor (taom ingredientlari bilan birga ombordan yechiladi).
Buyurtma qatorida tanlov surati saqlanadi: [{id, group_id, group, name, price, product_id, quantity}],
`modifiers_total` — 1 porsiya uchun qo'shimchalar narxi (jami = soni x (narx + modifiers_total)).
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.restaurant import Modifier, ModifierGroup, ProductModifierGroup

ZERO = Decimal("0")
CENT = Decimal("0.01")
MAX_IN_GROUP = 50
MAX_SELECT = 20
LINKABLE_KINDS = ("goods", "ingredient", "semi", "modifier", "dish")


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _num(v, field: str) -> Decimal:
    try:
        d = Decimal(str(v if v is not None else 0))
    except Exception:
        raise HTTPException(status_code=400, detail=f"{field}: son bo'lishi kerak")
    if not d.is_finite() or d < 0:
        raise HTTPException(status_code=400, detail=f"{field}: manfiy bo'lmasin")
    return d


def group_out(g: ModifierGroup, product_ids: Optional[list] = None, names: Optional[dict] = None) -> dict:
    names = names or {}
    return {
        "id": g.id, "name": g.name, "min_select": g.min_select, "max_select": g.max_select,
        "sort_order": g.sort_order, "is_active": bool(g.is_active), "required": g.min_select > 0,
        "modifiers": [{"id": m.id, "name": m.name, "price": float(m.price or 0), "product_id": m.product_id,
                       "product_name": names.get(m.product_id), "quantity": float(m.quantity or 0),
                       "sort_order": m.sort_order, "is_active": bool(m.is_active)} for m in g.modifiers],
        "product_ids": product_ids or [],
    }


def list_groups(db: Session, company_id: int, include_inactive: bool = True) -> list:
    q = db.query(ModifierGroup).filter(ModifierGroup.company_id == company_id)
    if not include_inactive:
        q = q.filter(ModifierGroup.is_active == True)  # noqa: E712
    groups = q.order_by(ModifierGroup.sort_order, ModifierGroup.id).all()
    links = {}
    for pid, gid in db.query(ProductModifierGroup.product_id, ProductModifierGroup.group_id).filter(
            ProductModifierGroup.company_id == company_id):
        links.setdefault(gid, []).append(pid)
    pids = {m.product_id for g in groups for m in g.modifiers if m.product_id}
    names = {p.id: p.name for p in db.query(Product).filter(Product.id.in_(pids or {0}))}
    return [group_out(g, sorted(links.get(g.id, [])), names) for g in groups]


def get_group(db: Session, company_id: int, group_id: int) -> ModifierGroup:
    g = db.query(ModifierGroup).filter(ModifierGroup.id == group_id, ModifierGroup.company_id == company_id).first()
    if g is None:
        raise HTTPException(status_code=404, detail="Qo'shimchalar guruhi topilmadi")
    return g


def save_group(db: Session, company_id: int, g: Optional[ModifierGroup], data: dict) -> ModifierGroup:
    """Guruhni yaratadi yoki yangilaydi. `modifiers` berilsa ro'yxat to'liq almashtiriladi (id bo'yicha yangilanadi,
    ro'yxatda yo'q variantlar o'chiriladi — eski cheklarda surati qoladi)."""
    # 1) hammasini tekshirish (yozishdan oldin)
    creating = g is None
    name = (data.get("name") if data.get("name") is not None else (g.name if g else "") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Guruh nomi kiritilmagan")
    mn = int(data["min_select"]) if data.get("min_select") is not None else (g.min_select if g else 0)
    mx = int(data["max_select"]) if data.get("max_select") is not None else (g.max_select if g else 1)
    if not 0 <= mn <= mx or not 1 <= mx <= MAX_SELECT:
        raise HTTPException(status_code=400, detail=f"Tanlov soni noto'g'ri: 0 <= eng kam <= eng ko'p <= {MAX_SELECT}")
    is_active = bool(data["is_active"]) if data.get("is_active") is not None else (bool(g.is_active) if g else True)
    rows = data.get("modifiers")
    clean = None
    if rows is not None:
        if len(rows) > MAX_IN_GROUP:
            raise HTTPException(status_code=400, detail=f"Guruhda {MAX_IN_GROUP} tadan ko'p variant bo'lmaydi")
        clean = []
        for i, r in enumerate(rows, start=1):
            mname = (r.get("name") or "").strip()
            if not mname:
                raise HTTPException(status_code=400, detail=f"{i}-variant: nomi kiritilmagan")
            price = _money(_num(r.get("price"), f"{i}-variant narxi"))
            pid = r.get("product_id")
            qty = _num(r.get("quantity"), f"{i}-variant miqdori").quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            if pid:
                p = db.query(Product).filter(Product.id == pid, Product.company_id == company_id,
                                             Product.is_deleted == False).first()  # noqa: E712
                if p is None or p.item_kind not in LINKABLE_KINDS:
                    raise HTTPException(status_code=400, detail=f"{i}-variant: bog'langan mahsulot topilmadi")
                if qty <= 0:
                    raise HTTPException(status_code=400, detail=f"{i}-variant: ombordan yechiladigan miqdorni kiriting")
            else:
                pid, qty = None, ZERO
            clean.append({"id": r.get("id"), "name": mname[:100], "price": price, "product_id": pid, "quantity": qty,
                          "sort_order": int(r.get("sort_order") if r.get("sort_order") is not None else i),
                          "is_active": bool(r.get("is_active", True))})
    active_count = (sum(1 for r in clean if r["is_active"]) if clean is not None
                    else sum(1 for m in (g.modifiers if g else []) if m.is_active))
    if is_active and mn > active_count:
        raise HTTPException(status_code=400, detail="Majburiy tanlov soni faol variantlardan ko'p")

    # 2) yozish
    if creating:
        g = ModifierGroup(company_id=company_id)
        db.add(g)
    g.name, g.min_select, g.max_select, g.is_active = name[:100], mn, mx, is_active
    if data.get("sort_order") is not None:
        g.sort_order = int(data["sort_order"])
    if clean is not None:
        existing = {m.id: m for m in g.modifiers} if not creating else {}
        keep = set()
        for r in clean:
            m = existing.get(r["id"]) if r["id"] else None
            if m is None:
                m = Modifier(company_id=company_id)
                g.modifiers.append(m)
            else:
                keep.add(m.id)
            m.name, m.price, m.product_id, m.quantity = r["name"], r["price"], r["product_id"], r["quantity"]
            m.sort_order, m.is_active = r["sort_order"], r["is_active"]
        for mid, m in existing.items():
            if mid not in keep:
                g.modifiers.remove(m)
    db.flush()
    return g


def set_product_groups(db: Session, company_id: int, product: Product, group_ids: list) -> list:
    if product.item_kind != "dish":
        raise HTTPException(status_code=400, detail="Qo'shimchalar faqat taomga biriktiriladi")
    ids = list(dict.fromkeys(int(x) for x in group_ids or []))
    if len(ids) > 20:
        raise HTTPException(status_code=400, detail="Taomga 20 tadan ko'p guruh biriktirilmaydi")
    found = {gid for (gid,) in db.query(ModifierGroup.id).filter(ModifierGroup.id.in_(ids or [0]),
                                                                 ModifierGroup.company_id == company_id)}
    if found != set(ids):
        raise HTTPException(status_code=404, detail="Qo'shimchalar guruhi topilmadi")
    db.query(ProductModifierGroup).filter(ProductModifierGroup.product_id == product.id,
                                          ProductModifierGroup.company_id == company_id).delete(synchronize_session=False)
    for i, gid in enumerate(ids):
        db.add(ProductModifierGroup(company_id=company_id, product_id=product.id, group_id=gid, sort_order=i))
    db.flush()
    return ids


def groups_by_product(db: Session, company_id: int, product_ids) -> dict:
    """{product_id: [group_id, ...]} biriktirish tartibida."""
    out = {}
    ids = list(product_ids or [])
    if not ids:
        return out
    for pid, gid in (db.query(ProductModifierGroup.product_id, ProductModifierGroup.group_id)
                     .filter(ProductModifierGroup.company_id == company_id, ProductModifierGroup.product_id.in_(ids))
                     .order_by(ProductModifierGroup.sort_order, ProductModifierGroup.id)):
        out.setdefault(pid, []).append(gid)
    return out


def resolve(db: Session, company_id: int, product: Product, selected, label: str = "") -> tuple:
    """Tanlangan variant id'larini tekshiradi: taomga biriktirilgan faol guruhlardan, faol, takrorlanmagan,
    har guruhda min..max. Qaytaradi: (surat ro'yxati yoki None, 1 porsiya uchun qo'shimchalar narxi)."""
    selected = [int(x) for x in (selected or [])]
    if len(selected) != len(set(selected)):
        raise HTTPException(status_code=400, detail=f"{label}qo'shimcha takrorlangan")
    gids = groups_by_product(db, company_id, [product.id]).get(product.id, [])
    groups = []
    if gids:
        rows = {g.id: g for g in db.query(ModifierGroup).filter(ModifierGroup.id.in_(gids),
                                                                ModifierGroup.is_active == True)}  # noqa: E712
        groups = [rows[g] for g in gids if g in rows]
    allowed = {m.id: (g, m) for g in groups for m in g.modifiers if m.is_active}
    for mid in selected:
        if mid not in allowed:
            raise HTTPException(status_code=400, detail=f"{label}'{product.name}' uchun bu qo'shimcha mavjud emas")
    snap, total = [], ZERO
    for g in groups:
        chosen = [allowed[mid][1] for mid in selected if allowed[mid][0].id == g.id]
        if len(chosen) < g.min_select:
            raise HTTPException(status_code=400, detail=f"{label}'{g.name}' dan kamida {g.min_select} ta tanlang")
        if len(chosen) > g.max_select:
            raise HTTPException(status_code=400, detail=f"{label}'{g.name}' dan ko'pi bilan {g.max_select} ta tanlang")
        for m in chosen:
            price = _money(m.price)
            total += price
            snap.append({"id": m.id, "group_id": g.id, "group": g.name, "name": m.name, "price": float(price),
                         "product_id": m.product_id, "quantity": str(m.quantity or 0)})
    return (snap or None), _money(total)
