"""Dorixona moduli (D1.1): yoqilganligini tekshirish va sozlamalar.

ASOSIY QOIDA: barcha dorixona qoidalari (FEFO, muddat ogohlantirishi, seriya, retsept ma'lumoti,
dori ma'lumotlari va h.k.) FAQAT `pharmacy_enabled(db, company_id)` True bo'lganda ishlaydi.
Modul o'chiq korxonada (oddiy do'kon) hech qaysi xatti-harakat o'zgarmaydi.

Bitta amal (sotuv, kirim) ichida bir marta `pharmacy_context(db, company_id)` chaqirib, natijani
qayta ishlating — har qator uchun bazaga so'rov yubormang.
"""
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

FEATURE_CODE = "pharmacy"

DEFAULT_SETTINGS = {
    # P.13: sotuvda ishlatilmaydi (dorixonada sotuv cheklanmaydi); eski korxonalar uchun saqlanadi
    "expiry_block_days": 0,
    # Muddatiga shuncha kun qolganda ogohlantirish (POS savati, hisobotlar)
    "expiry_warn_days": 30,
    # P.13: sotuvda ishlatilmaydi — retsept ixtiyoriy (eski korxonalar uchun saqlanadi)
    "rx_mode": "warn",
    # Kirimda qolgan yaroqlilik muddati foizi shundan kam bo'lsa ogohlantirish (0 = o'chiq)
    "min_shelf_life_pct": 0,
    # Kirimda sotuv narxini hisoblash: ustama foizi (0 = o'chiq, narx qo'lda) va yaxlitlash qadami (so'm)
    "markup_pct": 0,
    "price_round": 100,
    # Ustama chegarasi foizi (0 = cheklov yo'q); undan oshgan sotuv narxi saqlanmaydi
    "max_markup_pct": 0,
}
PRICE_ROUND_STEPS = (0, 1, 10, 50, 100, 500, 1000)
RX_MODES = ("warn", "block")


def normalize_pharmacy_settings(raw) -> dict:
    """Foydalanuvchi yuborgan sozlamalarni tekshiradi; noma'lum kalitlarni tashlab yuboradi."""
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Dorixona sozlamalari noto'g'ri formatda")
    out = {}
    for key in ("expiry_block_days", "expiry_warn_days"):
        if key in raw and raw[key] is not None:
            try:
                v = int(raw[key])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{key}: butun son bo'lishi kerak")
            if not 0 <= v <= 365:
                raise HTTPException(status_code=400, detail=f"{key}: 0 dan 365 gacha bo'lishi kerak")
            out[key] = v
    if "min_shelf_life_pct" in raw and raw["min_shelf_life_pct"] is not None:
        try:
            v = int(raw["min_shelf_life_pct"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="min_shelf_life_pct: butun son bo'lishi kerak")
        if not 0 <= v <= 100:
            raise HTTPException(status_code=400, detail="min_shelf_life_pct: 0 dan 100 gacha bo'lishi kerak")
        out["min_shelf_life_pct"] = v
    for key in ("markup_pct", "max_markup_pct"):
        if key in raw and raw[key] is not None:
            try:
                v = int(raw[key])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{key}: butun son bo'lishi kerak")
            if not 0 <= v <= 1000:
                raise HTTPException(status_code=400, detail=f"{key}: 0 dan 1000 gacha bo'lishi kerak")
            out[key] = v
    if "price_round" in raw and raw["price_round"] is not None:
        try:
            v = int(raw["price_round"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="price_round: butun son bo'lishi kerak")
        if v not in PRICE_ROUND_STEPS:
            raise HTTPException(status_code=400, detail=f"price_round: {PRICE_ROUND_STEPS} dan biri bo'lishi kerak")
        out["price_round"] = v
    if "rx_mode" in raw and raw["rx_mode"] is not None:
        if raw["rx_mode"] not in RX_MODES:
            raise HTTPException(status_code=400, detail="rx_mode: 'warn' yoki 'block' bo'lishi kerak")
        out["rx_mode"] = raw["rx_mode"]
    return out


def pharmacy_settings_of(company) -> dict:
    """Korxona sozlamalari standart qiymatlar bilan to'ldirilgan holda."""
    merged = dict(DEFAULT_SETTINGS)
    saved = getattr(company, "pharmacy_settings", None) if company is not None else None
    if isinstance(saved, dict):
        for k in DEFAULT_SETTINGS:
            if saved.get(k) is not None:
                merged[k] = saved[k]
    return merged


def pharmacy_enabled(db: Session, company_id: Optional[int]) -> bool:
    """Dorixona moduli shu korxonada faolmi (bayroq + tarif yoki paket, jamoaning umumiy qoidasi)."""
    if not company_id:
        return False
    from app.core.features import company_has_feature
    return company_has_feature(db, company_id, FEATURE_CODE)


def get_pharmacy_settings(db: Session, company_id: Optional[int]) -> dict:
    if not company_id:
        return dict(DEFAULT_SETTINGS)
    from app.models.company import Company
    return pharmacy_settings_of(db.get(Company, company_id))


def pharmacy_context(db: Session, company_id: Optional[int]) -> Tuple[bool, dict]:
    """(yoqilganmi, sozlamalar) — bitta amal uchun bir marta chaqiriladi."""
    enabled = pharmacy_enabled(db, company_id)
    return enabled, (get_pharmacy_settings(db, company_id) if enabled else dict(DEFAULT_SETTINGS))
