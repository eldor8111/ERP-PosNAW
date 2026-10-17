"""Aksiyalar (T4.3): serverda faollik/filial/mahsulot tekshiruvi va chegirma hisobi.

Qoidalar (frontend `UlgurjiSotuv.getPromoDiscount` bilan bir xil):
  - `is_active`, `start_date <= now`, `end_date` — sana ko'rinishida (00:00) bo'lsa kun oxirigacha;
  - `promotion_branches` bo'sh bo'lsa hamma filial, aks holda filial ro'yxatda bo'lishi shart;
  - `applies_to == "all"` (yoki eski qatorda mahsulotlar bo'sh) bo'lsa hamma mahsulot;
  - bir nechta mos aksiyadan eng katta chegirma tanlanadi.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.promotion import Promotion

PROMO_NOT_APPLICABLE = "Aksiya bu filialda yoki hozir amal qilmaydi"
_CENT = Decimal("0.01")


def local_now() -> datetime:
    """Toshkent vaqti (UTC+5), tz'siz — aksiya sanalari shu vaqt bo'yicha talqin qilinadi."""
    return (datetime.now(timezone.utc) + timedelta(hours=5)).replace(tzinfo=None)


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) is not None else dt


def promo_is_current(promo, now: Optional[datetime] = None) -> bool:
    """Faol va sana oralig'ida mi. `end_date` 00:00:00 bo'lsa (sana ko'rinishida) — kun oxirigacha amal qiladi."""
    if not getattr(promo, "is_active", False):
        return False
    now = _naive(now) or local_now()
    start = _naive(promo.start_date)
    if start is not None and start > now:
        return False
    end = _naive(promo.end_date)
    if end is not None:
        if end.hour == 0 and end.minute == 0 and end.second == 0 and end.microsecond == 0:
            end = end + timedelta(days=1)   # tugash kuni to'liq amal qiladi
            if now >= end:
                return False
        elif now > end:
            return False
    return True


def promo_matches_branch(promo, branch_id: Optional[int]) -> bool:
    branch_ids = {b.branch_id for b in (getattr(promo, "branches", None) or [])}
    if not branch_ids:
        return True
    return branch_id is not None and int(branch_id) in branch_ids


def promo_covers_product(promo, product_id: int) -> bool:
    applies = getattr(promo, "applies_to", None)
    items = getattr(promo, "products", None) or []
    if applies == "all" or (applies is None and not items):
        return True
    return any(pp.product_id == product_id for pp in items)


def get_active_promotions(db: Session, company_id: int, branch_id: Optional[int],
                          product_ids: Optional[Iterable[int]] = None,
                          now: Optional[datetime] = None) -> list:
    """Hozir amal qilayotgan, shu filialga mos aksiyalar. `product_ids` berilsa — shu mahsulotlardan
    kamida bittasini qamrab olganlari (universal aksiya hammasini)."""
    if company_id is None:
        return []
    promos = db.query(Promotion).options(
        joinedload(Promotion.products), joinedload(Promotion.branches),
    ).filter(
        Promotion.company_id == company_id,
        Promotion.is_active == True,  # noqa: E712
    ).order_by(Promotion.id.asc()).all()
    ids = None if product_ids is None else {int(i) for i in product_ids}
    out = []
    for p in promos:
        if not promo_is_current(p, now) or not promo_matches_branch(p, branch_id):
            continue
        if ids is not None and not any(promo_covers_product(p, pid) for pid in ids):
            continue
        out.append(p)
    return out


def calc_promo_discount(promo, unit_price, qty) -> Decimal:
    """Qator uchun aksiya chegirmasi (jami summa). Foiz: narx * foiz; summa: birlik uchun qiymat
    (narxdan oshmaydi) * miqdor."""
    price = Decimal(str(unit_price or 0))
    quantity = Decimal(str(qty or 0))
    value = Decimal(str(promo.discount_value or 0))
    per_unit = price * value / Decimal("100") if promo.discount_type == "percent" else value
    per_unit = max(Decimal("0"), min(per_unit, price))
    return (per_unit * quantity).quantize(_CENT, rounding=ROUND_HALF_UP)


def best_promotion(promos: Iterable, product_id: int, unit_price, qty):
    """Mahsulot uchun eng katta chegirmali mos aksiya -> `(promo, discount)`; mos aksiya yo'q bo'lsa `(None, 0)`."""
    best, best_disc = None, Decimal("0")
    for p in promos or []:
        if not promo_covers_product(p, product_id):
            continue
        d = calc_promo_discount(p, unit_price, qty)
        if d > best_disc:
            best, best_disc = p, d
    return best, best_disc


def apply_item_promotion(promos: list, product_id: int, promotion_id: Optional[int],
                         unit_price, qty, discount, auto_apply: bool = False):
    """Sotuv qatoriga aksiyani qo'llash -> `(discount, promotion_id, promotion_discount)`.

    `promos` — `get_active_promotions` natijasi (shu filial, hozirgi vaqt).
      - `promotion_id` berilgan: aksiya `promos` da va mahsulotni qamrasa — tekshiriladi, aks holda 400.
        Qo'shimcha chegirma QO'SHILMAYDI: `discount` o'zgarmaydi, aksiya ulushi
        `min(server hisobi, discount)` sifatida alohida saqlanadi (ikki marta chegirma yo'q).
      - `promotion_id` yo'q va `auto_apply`: eng yaxshi aksiya qo'llanadi, agar uning chegirmasi
        qatordagi mavjud chegirmadan katta bo'lsa (u holda chegirma aksiya chegirmasiga tenglanadi).
      - aks holda hech narsa o'zgarmaydi.
    """
    discount = Decimal(str(discount or 0))
    if promotion_id is not None:
        promo = next((p for p in (promos or []) if p.id == promotion_id), None)
        if promo is None or not promo_covers_product(promo, product_id):
            raise HTTPException(status_code=400, detail=PROMO_NOT_APPLICABLE)
        promo_disc = calc_promo_discount(promo, unit_price, qty)
        return discount, promo.id, min(promo_disc, discount)
    if auto_apply:
        promo, promo_disc = best_promotion(promos, product_id, unit_price, qty)
        if promo is not None and promo_disc > discount:
            return promo_disc, promo.id, promo_disc
    return discount, None, None


def company_auto_apply(db: Session, company_id: int) -> bool:
    from app.models.company import Company
    return bool(db.query(Company.promotions_auto_apply).filter(Company.id == company_id).scalar())


class SalePricingContext:
    """Sotuv narxlash konteksti (T4.3): filial narxlari + amaldagi aksiyalar, so'rov boshida bir marta yuklanadi."""

    def __init__(self, prices=None, promos=None, auto_apply=False):
        self.prices = prices or {}
        self.promos = promos or []
        self.auto_apply = auto_apply

    def branch_price(self, product_id: int, variant_id: Optional[int] = None):
        from app.services.branch_price_service import pick_branch_price
        return pick_branch_price(self.prices, product_id, variant_id)

    def apply(self, item_data, unit_price, discount):
        """-> `(discount, promotion_id, promotion_discount)` (`apply_item_promotion`)."""
        return apply_item_promotion(
            self.promos, item_data.product_id, getattr(item_data, "promotion_id", None),
            unit_price, item_data.quantity, discount, auto_apply=self.auto_apply,
        )


def load_sale_pricing_context(db: Session, user, warehouse_id, items, company_id: Optional[int] = None,
                              now: Optional[datetime] = None) -> SalePricingContext:
    """Sotuv qatorlari uchun filial narxlari va aksiyalarni yuklaydi. Filial: ombor filiali -> xodim filiali;
    aniqlanmasa filial narxi yo'q (korxona narxi), filialga bog'langan aksiyalar mos kelmaydi."""
    from app.services.branch_price_service import get_branch_prices, resolve_price_branch_id

    cid = company_id if company_id is not None else getattr(user, "company_id", None)
    branch_id = resolve_price_branch_id(db, user, warehouse_id)
    product_ids = [i.product_id for i in items]
    prices = get_branch_prices(db, cid, branch_id, product_ids)
    needs_promos = any(getattr(i, "promotion_id", None) is not None for i in items)
    auto = company_auto_apply(db, cid) if cid is not None else False
    promos = get_active_promotions(db, cid, branch_id, product_ids, now) if (needs_promos or auto) else []
    return SalePricingContext(prices, promos, auto)
