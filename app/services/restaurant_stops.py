"""Stop-list (R1.5): taomni filial bo'yicha to'xtatish, "qoldi N porsiya" hisoblagichi, ingredient yetishmasligi.

* Qo'lda stop: sabab, kim, qachongacha (`until` o'tsa o'zi qaytadi).
* Hisoblagich: chekka qo'shilganda kamayadi; 0 bo'lsa taom sotilmaydi. Qoralama o'chirilsa, miqdor kamaytirilsa
  yoki pishmagan taom bekor qilinsa porsiya qaytadi (tayyorlangani qaytmaydi).
* Ingredientlar: oshxona omboridagi qoldiq tex karta bo'yicha necha porsiyaga yetishi hisoblanadi (yarim tayyor
  mahsulot qoldig'i yetmasa o'z kartasi bo'yicha). 1 porsiyaga yetmasa ogohlantirish; `auto_stop_on_no_stock`
  yoqilgan bo'lsa taom sotilmaydi. Bu taxmin: taomlar umumiy ingredientni bir-biridan mustaqil hisoblaydi.
"""
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.bom import BOM, BOMItem
from app.models.inventory import StockLevel
from app.models.product import Product, ProductStatus
from app.models.restaurant import MenuStop

ZERO = Decimal("0")
MAX_DEPTH = 8


def _now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(d: Optional[datetime]) -> Optional[datetime]:
    if d is None:
        return None
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def is_stopped(row: Optional[MenuStop], now: Optional[datetime] = None) -> bool:
    if row is None:
        return False
    now = now or _now_naive()
    if row.stopped and (row.until is None or _naive(row.until) > now):
        return True
    return row.remaining is not None and Decimal(str(row.remaining)) <= 0


def stops_for(db: Session, company_id: int, branch_id: int) -> dict:
    return {r.product_id: r for r in db.query(MenuStop).filter(MenuStop.company_id == company_id,
                                                               MenuStop.branch_id == branch_id)}


# ── ingredientlar ─────────────────────────────────────────────────

class Availability:
    """Bir filial oshxona ombori bo'yicha taomlar necha porsiyaga yetishi (so'rovlar bir marta yuklanadi)."""

    def __init__(self, db: Session, company_id: int, branch_id: int, settings: dict):
        from app.services.restaurant import get_kitchen_warehouse
        self.settings = settings
        wh = get_kitchen_warehouse(db, company_id, branch_id)
        self.stock = {}
        if wh is not None:
            for pid, q in db.query(StockLevel.product_id, StockLevel.quantity).filter(
                    StockLevel.warehouse_id == wh.id, StockLevel.variant_id.is_(None)):
                self.stock[pid] = self.stock.get(pid, ZERO) + Decimal(str(q or 0))
        self.cards = {}
        for card in (db.query(BOM).options(joinedload(BOM.items).joinedload(BOMItem.component_product))
                     .filter(BOM.company_id == company_id, BOM.is_active == True)  # noqa: E712
                     .order_by(BOM.id)):
            self.cards[card.product_id] = card            # oxirgisi (eng katta id) qoladi = active_card
        self._memo = {}

    def portions(self, product_id: int, depth: int = 0) -> Optional[Decimal]:
        """Xom ashyodan qancha birlik tayyorlash mumkin. Karta yo'q yoki bo'sh bo'lsa None (noma'lum)."""
        if product_id in self._memo:
            return self._memo[product_id]
        card = self.cards.get(product_id)
        if card is None or not card.items or depth > MAX_DEPTH:
            return None
        self._memo[product_id] = ZERO                    # aylana bog'lanishdan himoya
        best = None
        for it in card.items:
            per = Decimal(str(it.quantity_per_unit or 0))
            if per <= 0:
                continue
            have = self.total_of(it.component_product, depth)
            n = max(have, ZERO) / per
            best = n if best is None or n < best else best
        self._memo[product_id] = best
        return best

    def total_of(self, comp: Product, depth: int) -> Decimal:
        have = self.stock.get(comp.id, ZERO)
        if comp.item_kind == "semi" and self.settings.get("semi_auto_expand", True):
            extra = self.portions(comp.id, depth + 1)
            if extra is not None:
                have = max(have, ZERO) + extra
        return have

    def missing(self, product_id: int) -> list:
        """1 porsiyaga yetmaydigan ingredientlar."""
        card = self.cards.get(product_id)
        out = []
        for it in (card.items if card else []):
            per = Decimal(str(it.quantity_per_unit or 0))
            comp = it.component_product
            have = self.total_of(comp, 0)
            if per > 0 and have < per:
                out.append({"product_id": comp.id, "name": comp.name, "unit": comp.unit,
                            "need": float(per), "have": float(max(have, ZERO))})
        return out


# ── buyurtma uchun ────────────────────────────────────────────────

def _row_locked(db: Session, company_id: int, branch_id: int, product_id: int) -> Optional[MenuStop]:
    q = db.query(MenuStop).filter(MenuStop.company_id == company_id, MenuStop.branch_id == branch_id,
                                  MenuStop.product_id == product_id)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        q = q.with_for_update()
    return q.first()


def consume(db: Session, order, product: Product, qty: Decimal, settings: dict, label: str = "") -> None:
    """Chekka qo'shishdan oldin: stop, hisoblagich va (sozlama bo'yicha) ingredient tekshiruvi."""
    row = _row_locked(db, order.company_id, order.branch_id, product.id)
    if row is not None:
        now = _now_naive()
        if row.stopped and (row.until is None or _naive(row.until) > now):
            raise HTTPException(status_code=409, detail=f"{label}'{product.name}' stop-listda"
                                                       + (f": {row.reason}" if row.reason else ""))
        if row.remaining is not None:
            left = Decimal(str(row.remaining))
            if left < qty:
                raise HTTPException(status_code=409, detail=(
                    f"{label}'{product.name}' tugadi (stop-list)" if left <= 0
                    else f"{label}'{product.name}' dan faqat {left.normalize():f} porsiya qoldi"))
            row.remaining = left - qty
            row.updated_at = datetime.now(timezone.utc)
    if product.item_kind == "dish" and settings.get("auto_stop_on_no_stock"):
        n = Availability(db, order.company_id, order.branch_id, settings).portions(product.id)
        if n is not None and n < qty:
            raise HTTPException(status_code=409, detail=f"{label}'{product.name}' uchun ingredient yetmaydi (stop-list)")


def release(db: Session, order, product_id: int, qty: Decimal) -> None:
    """Porsiya hisoblagichga qaytadi (qoralama o'chirildi, miqdor kamaydi, pishmagan taom bekor qilindi)."""
    if qty <= 0:
        return
    row = _row_locked(db, order.company_id, order.branch_id, product_id)
    if row is not None and row.remaining is not None:
        row.remaining = Decimal(str(row.remaining)) + qty
        row.updated_at = datetime.now(timezone.utc)


# ── ro'yxat ───────────────────────────────────────────────────────

def _q(v) -> Optional[float]:
    return float(v) if v is not None else None


def status(db: Session, company_id: int, branch_id: int, settings: dict) -> dict:
    """Stop-list sahifasi va buyurtma ekrani uchun: qo'lda stoplar, hisoblagichlar, ingredient yetishmasligi va
    hozir sotilmaydigan taomlar ro'yxati."""
    from app.models.user import User
    now = _now_naive()
    rows = stops_for(db, company_id, branch_id)
    sellable = (db.query(Product).filter(Product.company_id == company_id, Product.is_deleted == False,  # noqa: E712
                                         Product.status == ProductStatus.active,
                                         Product.item_kind.in_(("dish", "goods"))).all())
    names = {p.id: p for p in sellable}
    users = {u.id: u.name for u in db.query(User).filter(User.id.in_({r.updated_by for r in rows.values()
                                                                       if r.updated_by} or {0}))}
    avail = Availability(db, company_id, branch_id, settings)
    auto = bool(settings.get("auto_stop_on_no_stock"))
    stops, low, unavailable = [], [], set()
    for pid, r in rows.items():
        p = names.get(pid)
        if p is None:
            continue
        stopped = is_stopped(r, now)
        if stopped:
            unavailable.add(pid)
        stops.append({"product_id": pid, "name": p.name, "kind": p.item_kind, "stopped": bool(r.stopped),
                      "reason": r.reason, "until": (r.until.replace(tzinfo=timezone.utc).isoformat()
                                                   if r.until and r.until.tzinfo is None else
                                                   (r.until.isoformat() if r.until else None)),
                      "expired": bool(r.stopped and r.until is not None and _naive(r.until) <= now),
                      "remaining": _q(r.remaining), "effective": stopped,
                      "updated_by": users.get(r.updated_by),
                      "updated_at": r.updated_at.isoformat() if r.updated_at else None})
    for p in sellable:
        if p.item_kind != "dish":
            continue
        n = avail.portions(p.id)
        if n is not None and n < 1:
            low.append({"product_id": p.id, "name": p.name, "portions": 0, "missing": avail.missing(p.id)})
            if auto:
                unavailable.add(p.id)
    stops.sort(key=lambda x: (not x["effective"], x["name"].lower()))
    low.sort(key=lambda x: x["name"].lower())
    portions = {}
    for p in sellable:
        if p.item_kind == "dish":
            n = avail.portions(p.id)
            if n is not None:
                portions[p.id] = int(n.to_integral_value(rounding=ROUND_DOWN))
    return {"auto_stop": auto, "stops": stops, "low": low, "unavailable": sorted(unavailable),
            "remaining": {str(s["product_id"]): s["remaining"] for s in stops if s["remaining"] is not None},
            "portions": {str(k): v for k, v in portions.items()}}


def upsert(db: Session, user, company_id: int, branch_id: int, product: Product, data: dict) -> Optional[MenuStop]:
    """Qo'lda stop va hisoblagichni yozadi. Ikkalasi ham bo'lmasa qator o'chadi (taom sotuvga qaytadi)."""
    if product.item_kind not in ("dish", "goods"):
        raise HTTPException(status_code=400, detail="Stop-listga faqat taom yoki tovar qo'yiladi")
    stopped = bool(data.get("stopped"))
    until = data.get("until")
    if until is not None:
        until = _naive(until)
        if until <= _now_naive():
            raise HTTPException(status_code=400, detail="'Qachongacha' vaqti o'tib ketgan")
    remaining = data.get("remaining")
    if remaining is not None:
        try:
            remaining = Decimal(str(remaining))
        except Exception:
            raise HTTPException(status_code=400, detail="Porsiya soni noto'g'ri")
        if not remaining.is_finite() or remaining < 0 or remaining > 100000:
            raise HTTPException(status_code=400, detail="Porsiya soni 0 dan 100000 gacha")
    row = db.query(MenuStop).filter(MenuStop.company_id == company_id, MenuStop.branch_id == branch_id,
                                    MenuStop.product_id == product.id).first()
    if not stopped and remaining is None:
        if row is not None:
            db.delete(row)
            db.flush()
        return None
    if row is None:
        row = MenuStop(company_id=company_id, branch_id=branch_id, product_id=product.id)
        db.add(row)
    row.stopped = stopped
    row.reason = ((data.get("reason") or "").strip()[:200] or None) if stopped else None
    row.until = until if stopped else None
    row.remaining = remaining
    row.updated_by = user.id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row
