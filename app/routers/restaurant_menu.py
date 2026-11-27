"""Restoran menyusi API (R1.1, R1.2, R1.4): taomlar, yarim tayyorlar, ingredientlar, tex kartalar, sexlar.

Hamma endpoint `require_restaurant` ostida (do'kon korxonasi chaqirsa 403).
O'qish — korxonaning ishlaydigan xodimlari; yozish — admin, direktor, menejer (ingredient va tovarni omborchi ham).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.audit import log_action
from app.core.dependencies import require_roles
from app.core.features import require_restaurant
from app.database import get_db
from app.models.bom import BOM
from app.models.category import Category
from app.models.product import Product, ProductStatus
from app.models.restaurant import KitchenStation
from app.models.user import User, UserRole
from app.services import restaurant_modifiers as mod_svc
from app.services.restaurant_menu import (
    CARD_KINDS, ITEM_KINDS, CostCalc, active_card, apply_item_fields, card_out, check_station, create_item,
    food_cost_pct, get_item, money, save_card, used_in_cards,
)

router = APIRouter(prefix="/restaurant", tags=["Restoran menyusi"], dependencies=[Depends(require_restaurant)])

READ_ROLES = (UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant,
              UserRole.warehouse, UserRole.cashier)
EDIT_ROLES = (UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager)
STOCK_EDIT_ROLES = EDIT_ROLES + (UserRole.warehouse,)


class ItemIn(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    unit: Optional[str] = None
    category_id: Optional[int] = None
    station_id: Optional[int] = None
    sale_price: Optional[float] = None
    cost_price: Optional[float] = None
    barcode: Optional[str] = None
    is_active: Optional[bool] = None


class CardRowIn(BaseModel):
    component_product_id: int
    gross_qty: float
    net_qty: Optional[float] = None
    loss_cold_pct: Optional[float] = None
    loss_hot_pct: Optional[float] = None


class CardIn(BaseModel):
    output_qty: Optional[float] = 1
    output_weight_g: Optional[float] = None
    cooking_time_min: Optional[int] = None
    instructions: Optional[str] = None
    items: List[CardRowIn]


class StationIn(BaseModel):
    name: Optional[str] = None
    kds_enabled: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryStationIn(BaseModel):
    station_id: Optional[int] = None


class ModifierIn(BaseModel):
    id: Optional[int] = None
    name: str
    price: float = 0
    product_id: Optional[int] = None
    quantity: Optional[float] = None
    sort_order: Optional[int] = None
    is_active: bool = True


class ModifierGroupIn(BaseModel):
    name: Optional[str] = None
    min_select: Optional[int] = None
    max_select: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    modifiers: Optional[List[ModifierIn]] = None


class ProductGroupsIn(BaseModel):
    group_ids: List[int]


def _guard_edit(user: User, kind: str):
    """Ingredient va tovarni omborchi ham kirita oladi; taom, yarim tayyor va modifikatorni faqat rahbarlar."""
    if user.role in EDIT_ROLES:
        return
    if user.role == UserRole.warehouse and kind in ("ingredient", "goods"):
        return
    raise HTTPException(status_code=403, detail="Bu amal uchun ruxsat yo'q")


def _item_out(p: Product, calc: CostCalc, has_card: bool, cat_station: dict, mod_groups: Optional[dict] = None) -> dict:
    unit_cost = calc.unit_cost(p)
    eff_station = p.station_id or cat_station.get(p.category_id)
    return {
        "id": p.id, "name": p.name, "kind": p.item_kind, "unit": p.unit, "barcode": p.barcode,
        "category_id": p.category_id, "category_name": p.category.name if p.category else None,
        "station_id": p.station_id, "effective_station_id": eff_station,
        "sale_price": money(p.sale_price or 0), "cost_price": money(p.cost_price or 0),
        "unit_cost": money(unit_cost),
        "food_cost_pct": food_cost_pct(unit_cost, p.sale_price) if p.item_kind == "dish" and has_card else None,
        "has_card": has_card, "is_active": p.status == ProductStatus.active,
        "modifier_group_ids": (mod_groups or {}).get(p.id, []),
    }


def _cat_stations(db: Session, company_id: int) -> dict:
    return {cid: sid for cid, sid in db.query(Category.id, Category.station_id).filter(
        Category.company_id == company_id, Category.station_id.isnot(None))}


# ───────────────────────── Menyu elementlari ─────────────────────────

@router.get("/menu/items")
def list_items(
    kind: Optional[str] = Query(None, description="goods | dish | semi | ingredient | modifier; vergul bilan bir nechta"),
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    include_inactive: bool = False,
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ_ROLES)),
):
    cid = user.company_id
    qry = db.query(Product).options(joinedload(Product.category)).filter(
        Product.company_id == cid, Product.is_deleted == False)  # noqa: E712
    if kind:
        kinds = [k.strip() for k in kind.split(",") if k.strip()]
        if any(k not in ITEM_KINDS for k in kinds):
            raise HTTPException(status_code=400, detail="Turi noto'g'ri")
        qry = qry.filter(Product.item_kind.in_(kinds))
    if not include_inactive:
        qry = qry.filter(Product.status == ProductStatus.active)
    if category_id is not None:
        qry = qry.filter(Product.category_id == category_id)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        qry = qry.filter(or_(func.lower(Product.name).like(like), Product.barcode == q.strip()))
    items = qry.order_by(Product.name).limit(limit).all()
    with_card = set()
    card_ids = [p.id for p in items if p.item_kind in CARD_KINDS]
    if card_ids:
        with_card = {r[0] for r in db.query(BOM.product_id).filter(
            BOM.company_id == cid, BOM.is_active == True, BOM.product_id.in_(card_ids))}  # noqa: E712
    calc = CostCalc(db, cid)
    cats = _cat_stations(db, cid)
    mods = mod_svc.groups_by_product(db, cid, [p.id for p in items if p.item_kind == "dish"])
    return [_item_out(p, calc, p.id in with_card, cats, mods) for p in items]


@router.post("/menu/items", status_code=201)
def create_menu_item(payload: ItemIn, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*STOCK_EDIT_ROLES))):
    data = payload.model_dump(exclude_unset=True)
    _guard_edit(user, data.get("kind") or "dish")
    p = create_item(db, user.company_id, data)
    db.commit()
    db.refresh(p)
    return _item_out(p, CostCalc(db, user.company_id), False, _cat_stations(db, user.company_id))


@router.put("/menu/items/{item_id}")
def update_menu_item(item_id: int, payload: ItemIn, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*STOCK_EDIT_ROLES))):
    p = get_item(db, user.company_id, item_id)
    data = payload.model_dump(exclude_unset=True)
    _guard_edit(user, p.item_kind)
    if "kind" in data:
        _guard_edit(user, data["kind"] or p.item_kind)
    data.pop("barcode", None)
    old_price = p.sale_price
    from app.services import restaurant_costs  # R7.5: tannarx qo'lda o'zgarsa ham kartalar qayta hisoblanadi
    cost_before = restaurant_costs.snapshot(db, user.company_id, [p.id]) if "cost_price" in data else None
    apply_item_fields(db, user.company_id, p, data, creating=False)
    if "sale_price" in data and old_price != p.sale_price:
        log_action(db=db, action="MENU_PRICE_CHANGE", entity_type="product", entity_id=p.id, user_id=user.id,
                   old_values={"sale_price": float(old_price or 0)}, new_values={"sale_price": float(p.sale_price or 0)})
    restaurant_costs.record(db, user.company_id, cost_before, "manual", None, user.id)
    db.commit()
    db.refresh(p)
    return _item_out(p, CostCalc(db, user.company_id), active_card(db, user.company_id, p.id) is not None,
                     _cat_stations(db, user.company_id))


@router.delete("/menu/items/{item_id}")
def delete_menu_item(item_id: int, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*STOCK_EDIT_ROLES))):
    p = get_item(db, user.company_id, item_id)
    _guard_edit(user, p.item_kind)
    users = used_in_cards(db, user.company_id, p.id)
    if users:
        raise HTTPException(status_code=400,
                            detail="Bu mahsulot tex kartalarda ishlatilgan: " + ", ".join(users[:5])
                                   + (" va boshqalar" if len(users) > 5 else ""))
    p.is_deleted = True
    db.query(BOM).filter(BOM.company_id == user.company_id, BOM.product_id == p.id,
                         BOM.is_active == True).update({BOM.is_active: False}, synchronize_session=False)  # noqa: E712
    db.commit()
    return {"ok": True}


# ───────────────────────── Tex karta ─────────────────────────

@router.get("/menu/items/{item_id}/card")
def get_card(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*READ_ROLES))):
    p = get_item(db, user.company_id, item_id)
    return card_out(db, user.company_id, p, active_card(db, user.company_id, p.id))


@router.put("/menu/items/{item_id}/card")
def put_card(item_id: int, payload: CardIn, db: Session = Depends(get_db),
             user: User = Depends(require_roles(*EDIT_ROLES))):
    p = get_item(db, user.company_id, item_id)
    card = save_card(db, user.company_id, p, payload.model_dump(), user.id)
    log_action(db=db, action="TECH_CARD_SAVE", entity_type="product", entity_id=p.id, user_id=user.id,
               new_values={"bom_id": card.id, "version": card.version, "items": len(card.items)})
    db.commit()
    return card_out(db, user.company_id, p, card)


@router.get("/menu/items/{item_id}/card/versions")
def card_versions(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*READ_ROLES))):
    p = get_item(db, user.company_id, item_id)
    cards = (db.query(BOM).filter(BOM.company_id == user.company_id, BOM.product_id == p.id)
             .order_by(BOM.id.desc()).limit(50).all())
    calc = CostCalc(db, user.company_id)
    return [card_out(db, user.company_id, p, c, calc) | {"is_active": bool(c.is_active)} for c in cards]


# ───────────────────────── Kategoriyalar va sexlar ─────────────────────────

@router.get("/menu/categories")
def list_categories(db: Session = Depends(get_db), user: User = Depends(require_roles(*READ_ROLES))):
    rows = (db.query(Category).filter(Category.company_id == user.company_id, Category.is_deleted == False)  # noqa: E712
            .order_by(Category.sort_order, Category.name).all())
    return [{"id": c.id, "name": c.name, "parent_id": c.parent_id, "station_id": c.station_id} for c in rows]


@router.put("/menu/categories/{category_id}")
def set_category_station(category_id: int, payload: CategoryStationIn, db: Session = Depends(get_db),
                         user: User = Depends(require_roles(*EDIT_ROLES))):
    c = db.query(Category).filter(Category.id == category_id, Category.company_id == user.company_id,
                                  Category.is_deleted == False).first()  # noqa: E712
    if c is None:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    c.station_id = check_station(db, user.company_id, payload.station_id)
    db.commit()
    return {"id": c.id, "name": c.name, "parent_id": c.parent_id, "station_id": c.station_id}


def _station_out(s: KitchenStation) -> dict:
    return {"id": s.id, "name": s.name, "kds_enabled": s.kds_enabled, "sort_order": s.sort_order,
            "is_active": s.is_active}


@router.get("/stations")
def list_stations(db: Session = Depends(get_db), user: User = Depends(require_roles(*READ_ROLES))):
    rows = (db.query(KitchenStation).filter(KitchenStation.company_id == user.company_id)
            .order_by(KitchenStation.sort_order, KitchenStation.id).all())
    return [_station_out(s) for s in rows]


def _station_name(name) -> str:
    name = (name or "").strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Sex nomi 1-100 belgi bo'lishi kerak")
    return name


@router.post("/stations", status_code=201)
def create_station(payload: StationIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(*EDIT_ROLES))):
    name = _station_name(payload.name)
    dup = db.query(KitchenStation.id).filter(KitchenStation.company_id == user.company_id,
                                             func.lower(KitchenStation.name) == name.lower()).first()
    if dup:
        raise HTTPException(status_code=409, detail="Bunday nomli sex bor")
    last = db.query(func.max(KitchenStation.sort_order)).filter(
        KitchenStation.company_id == user.company_id).scalar() or 0
    s = KitchenStation(company_id=user.company_id, name=name, kds_enabled=bool(payload.kds_enabled),
                       sort_order=payload.sort_order if payload.sort_order is not None else last + 1)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _station_out(s)


@router.put("/stations/{station_id}")
def update_station(station_id: int, payload: StationIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(*EDIT_ROLES))):
    s = db.query(KitchenStation).filter(KitchenStation.id == station_id,
                                        KitchenStation.company_id == user.company_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="Sex topilmadi")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = _station_name(data["name"])
        dup = db.query(KitchenStation.id).filter(KitchenStation.company_id == user.company_id,
                                                 KitchenStation.id != s.id,
                                                 func.lower(KitchenStation.name) == name.lower()).first()
        if dup:
            raise HTTPException(status_code=409, detail="Bunday nomli sex bor")
        s.name = name
    for k in ("kds_enabled", "sort_order", "is_active"):
        if data.get(k) is not None:
            setattr(s, k, data[k])
    db.commit()
    db.refresh(s)
    return _station_out(s)


# ───────────────────────── Qo'shimchalar (R1.3) ─────────────────────────

@router.get("/modifier-groups")
def list_modifier_groups(include_inactive: bool = True, db: Session = Depends(get_db),
                         user: User = Depends(require_roles(*READ_ROLES))):
    return mod_svc.list_groups(db, user.company_id, include_inactive)


def _group_resp(db: Session, company_id: int, gid: int) -> dict:
    return next(g for g in mod_svc.list_groups(db, company_id) if g["id"] == gid)


@router.post("/modifier-groups", status_code=201)
def create_modifier_group(payload: ModifierGroupIn, db: Session = Depends(get_db),
                          user: User = Depends(require_roles(*EDIT_ROLES))):
    data = payload.model_dump(exclude_unset=True)
    if "modifiers" in data:
        data["modifiers"] = [m.model_dump() for m in payload.modifiers or []]
    g = mod_svc.save_group(db, user.company_id, None, data)
    log_action(db=db, action="MODIFIER_GROUP_CREATE", entity_type="modifier_group", entity_id=g.id, user_id=user.id,
               new_values={"name": g.name})
    db.commit()
    return _group_resp(db, user.company_id, g.id)


@router.put("/modifier-groups/{group_id}")
def update_modifier_group(group_id: int, payload: ModifierGroupIn, db: Session = Depends(get_db),
                          user: User = Depends(require_roles(*EDIT_ROLES))):
    g = mod_svc.get_group(db, user.company_id, group_id)
    data = payload.model_dump(exclude_unset=True)
    if "modifiers" in data:
        data["modifiers"] = [m.model_dump() for m in payload.modifiers or []]
    mod_svc.save_group(db, user.company_id, g, data)
    log_action(db=db, action="MODIFIER_GROUP_UPDATE", entity_type="modifier_group", entity_id=g.id, user_id=user.id,
               new_values={"name": g.name, "modifiers": len(g.modifiers)})
    db.commit()
    return _group_resp(db, user.company_id, g.id)


@router.delete("/modifier-groups/{group_id}")
def delete_modifier_group(group_id: int, db: Session = Depends(get_db),
                          user: User = Depends(require_roles(*EDIT_ROLES))):
    """O'chirish taomlardan ham ajratadi; eski cheklarda tanlov surati saqlanib qoladi."""
    from app.models.restaurant import ProductModifierGroup
    g = mod_svc.get_group(db, user.company_id, group_id)
    db.query(ProductModifierGroup).filter(ProductModifierGroup.group_id == g.id).delete(synchronize_session=False)
    log_action(db=db, action="MODIFIER_GROUP_DELETE", entity_type="modifier_group", entity_id=g.id, user_id=user.id,
               old_values={"name": g.name})
    db.delete(g)
    db.commit()
    return {"ok": True}


@router.put("/menu/items/{item_id}/modifier-groups")
def set_item_modifier_groups(item_id: int, payload: ProductGroupsIn, db: Session = Depends(get_db),
                             user: User = Depends(require_roles(*EDIT_ROLES))):
    p = get_item(db, user.company_id, item_id)
    ids = mod_svc.set_product_groups(db, user.company_id, p, payload.group_ids)
    db.commit()
    return {"product_id": p.id, "modifier_group_ids": ids}


# ── R7.5: food cost nazorati ─────────────────────────────────────

COST_ROLES = EDIT_ROLES + (UserRole.accountant, UserRole.warehouse)


@router.get("/food-cost")
def food_cost_overview(db: Session = Depends(get_db), user: User = Depends(require_roles(*COST_ROLES))):
    """Kartasi bor taomlar: tannarx, food cost %, chegaradan oshganlari (tavsiya narx bilan) birinchi."""
    from app.services import restaurant_costs
    return restaurant_costs.overview(db, user.company_id)


@router.get("/food-cost/changes")
def food_cost_changes(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db),
                      user: User = Depends(require_roles(*COST_ROLES))):
    """Ingredient tannarxi o'zgarishlari (kirim yoki qo'lda) va ta'sirlangan taomlar: eski / yangi tannarx va food cost."""
    from app.services import restaurant_costs
    return {"items": restaurant_costs.list_changes(db, user.company_id, limit)}
