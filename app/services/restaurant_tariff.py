"""Restoran tariflari (R9.1): tarif biznes turi, restoran imkoniyatlari va limitlari.

* Tarif `business_type` ('retail' | 'restaurant') — do'kon va restoran tariflari aralashmaydi: korxona faqat o'z
  turidagi tarifni ko'radi va sotib oladi (Super Admin ham boshqa turdagi tarifni biriktira olmaydi).
* `restaurant_features` — restoran tarifiga kiradigan imkoniyatlar. NULL bo'lsa (yoki korxona tarifi restoran
  tarifi bo'lmasa) cheklov yo'q: hammasi ochiq (mavjud restoranlar buzilmasligi uchun).
* `max_waiter_devices` — faol ofitsiant planshetlari soni (NULL = cheksiz).
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

RESTAURANT_FEATURES = {
    "kds": "Oshxona ekrani (KDS)",
    "reservations": "Bron",
    "delivery": "Yetkazib berish",
    "aggregators": "Agregatorlar",
    "qr_menu": "QR menyu",
}
BUSINESS_TYPES = ("retail", "restaurant")
TYPE_TITLES = {"retail": "do'konlar", "restaurant": "restoranlar"}


def normalize_features(value) -> Optional[list]:
    """None -> None (cheklovsiz); ro'yxat -> tartiblangan, noma'lum kodsiz. Noto'g'ri tur -> 400."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise HTTPException(status_code=400, detail="restaurant_features ro'yxat bo'lishi kerak")
    bad = [v for v in value if v not in RESTAURANT_FEATURES]
    if bad:
        raise HTTPException(status_code=400, detail=f"Noma'lum restoran imkoniyati: {', '.join(map(str, bad))}")
    return [k for k in RESTAURANT_FEATURES if k in value]


def normalize_business_type(value) -> str:
    v = (value or "retail").strip().lower()
    if v not in BUSINESS_TYPES:
        raise HTTPException(status_code=400, detail="Tarif turi 'retail' yoki 'restaurant' bo'lishi kerak")
    return v


def _company(db: Session, company_id):
    from app.models.company import Company
    return db.query(Company).filter(Company.id == company_id).first() if company_id else None


def _restaurant_tariff(company):
    t = getattr(company, "tariff", None) if company is not None else None
    if t is None or (getattr(t, "business_type", None) or "retail") != "restaurant":
        return None
    return t


def enabled_features(db: Session, company_id) -> list:
    t = _restaurant_tariff(_company(db, company_id))
    allowed = getattr(t, "restaurant_features", None) if t is not None else None
    return list(RESTAURANT_FEATURES) if allowed is None else [k for k in RESTAURANT_FEATURES if k in allowed]


def feature_on(db: Session, company_id, code: str) -> bool:
    return code in enabled_features(db, company_id)


def check_waiter_devices(db: Session, company_id: int) -> None:
    """Yangi planshet ulashdan oldin: faol (bekor qilinmagan) planshetlar tarif limitiga yetgan bo'lsa 403."""
    from app.models.restaurant import RestaurantTerminal
    t = _restaurant_tariff(_company(db, company_id))
    limit = getattr(t, "max_waiter_devices", None) if t is not None else None
    if limit is None:
        return
    used = db.query(RestaurantTerminal.id).filter(RestaurantTerminal.company_id == company_id,
                                                  RestaurantTerminal.revoked_at.is_(None)).count()
    if used >= int(limit):
        raise HTTPException(status_code=403, detail={
            "code": "TARIFF_LIMIT",
            "message": f"Tarifingizda {limit} ta ofitsiant plansheti bor. Eski planshetni bekor qiling yoki tarifni oshiring.",
            "limit": int(limit), "used": used,
        })


def check_tariff_fits(tariff, company) -> None:
    """Tarif korxona turiga mos kelmasa 400 (restoran do'kon tarifini va aksincha sotib ololmaydi)."""
    t_type = getattr(tariff, "business_type", None) or "retail"
    c_type = getattr(company, "business_type", None) or "retail"
    if t_type != c_type:
        raise HTTPException(status_code=400, detail={
            "code": "TARIFF_TYPE_MISMATCH",
            "message": f"Bu tarif {TYPE_TITLES.get(t_type, t_type)} uchun. Korxonangizga mos tarifni tanlang.",
        })
