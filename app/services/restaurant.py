"""Restoran rejimi: biznes turi, sozlamalar va yangi restoranni tayyorlash (R0.1-R0.5).

Restoran qoidalari FAQAT `companies.business_type = 'restaurant'` bo'lganda ishlaydi; oddiy do'kon
(`retail`) uchun bu moduldagi hech narsa chaqirilmaydi va hech narsa o'zgarmaydi.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

BUSINESS_TYPES = ("retail", "restaurant")
RESTAURANT = "restaurant"
RETAIL = "retail"

# Format faqat boshlang'ich sozlamalarni belgilaydi; keyin Sozlamalarda o'zgartiriladi.
FORMATS = {
    # stolli restoran: zal, ofitsiant, xizmat haqi 10%
    "full_service": {"service_pct": 10, "table_service": True, "order_number_screen": False},
    "cafe": {"service_pct": 0, "table_service": True, "order_number_screen": False},
    # fast-food: stol yo'q, kassada buyurtma, buyurtma raqami ekrani
    "fast_food": {"service_pct": 0, "table_service": False, "order_number_screen": True},
    # oshxona / choyxona: stollar bor, tez kassa
    "canteen": {"service_pct": 0, "table_service": True, "order_number_screen": False},
}
DEFAULT_FORMAT = "full_service"

DEFAULT_SETTINGS = {
    "format": DEFAULT_FORMAT,
    "table_service": True,
    "service_pct": 10,               # xizmat haqi (obslujivaniye), foiz
    "service_after_discount": True,  # xizmat haqi chegirmadan keyingi summadan
    "deduct_stock_on": "paid",       # ingredient yechish: 'paid' (chek to'langanda) | 'sent' (oshxonaga yuborilganda)
    "semi_auto_expand": True,        # yarim tayyor mahsulot qoldig'i yo'q bo'lsa tex kartasi bo'yicha yoyiladi
    "precheck_lock": True,           # pre-chekdan keyin chek tahriri menejer ruxsati bilan
    "waiter_can_take_payment": False,
    "waiter_sees_all_tables": False,
    "food_cost_alert_pct": 35,
    "auto_stop_on_no_stock": False,
    "delivery_auto_send_kitchen": False,
    "order_number_screen": False,
    "reservation_duration_min": 120,     # R8.1: bron davomiyligi (sukut)
    "reservation_hold_min": 60,          # stol bron vaqtidan shuncha daqiqa oldin zalda "bron" ko'rinadi
    "reservation_remind_hours": 2,       # eslatma bron vaqtidan shuncha soat oldin (0 = o'chiq)
    "reservation_sms_reminder": False,   # Telegram bo'lmasa SMS (pullik) yuborilsinmi
}

DEFAULT_CATEGORIES = (
    "Salatlar", "Birinchi taomlar", "Ikkinchi taomlar", "Gril", "Ichimliklar", "Desertlar", "Non",
)
DEFAULT_STATIONS = ("Issiq sex", "Sovuq sex", "Bar")
DEFAULT_HALL = "Asosiy zal"
DEFAULT_TABLES = 10
KITCHEN_WAREHOUSE_NAME = "Oshxona"

_BOOL_KEYS = ("table_service", "service_after_discount", "semi_auto_expand", "precheck_lock",
              "waiter_can_take_payment", "waiter_sees_all_tables", "auto_stop_on_no_stock",
              "delivery_auto_send_kitchen", "order_number_screen", "reservation_sms_reminder")


def normalize_business_type(value: Optional[str]) -> str:
    v = (value or RETAIL).strip().lower()
    if v not in BUSINESS_TYPES:
        raise HTTPException(status_code=400, detail="Biznes turi noto'g'ri: 'retail' yoki 'restaurant'")
    return v


def normalize_format(value: Optional[str]) -> str:
    v = (value or DEFAULT_FORMAT).strip().lower()
    if v not in FORMATS:
        raise HTTPException(status_code=400, detail="Restoran formati noto'g'ri")
    return v


def settings_for_format(fmt: str) -> dict:
    s = dict(DEFAULT_SETTINGS)
    s.update(FORMATS[fmt])
    s["format"] = fmt
    return s


def normalize_restaurant_settings(raw) -> dict:
    """Foydalanuvchi yuborgan sozlamalarni tekshiradi; noma'lum kalitlar tashlab yuboriladi."""
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Restoran sozlamalari noto'g'ri formatda")
    out = {}
    if raw.get("format") is not None:
        out["format"] = normalize_format(raw["format"])
    for key, lo, hi in (("service_pct", 0, 50), ("food_cost_alert_pct", 0, 100), ("reservation_duration_min", 15, 720),
                        ("reservation_hold_min", 0, 240), ("reservation_remind_hours", 0, 48)):
        if raw.get(key) is not None:
            try:
                v = float(raw[key])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{key}: son bo'lishi kerak")
            if not lo <= v <= hi:
                raise HTTPException(status_code=400, detail=f"{key}: {lo} dan {hi} gacha bo'lishi kerak")
            out[key] = int(v) if v == int(v) else round(v, 2)
    if raw.get("deduct_stock_on") is not None:
        if raw["deduct_stock_on"] not in ("paid", "sent"):
            raise HTTPException(status_code=400, detail="deduct_stock_on: 'paid' yoki 'sent'")
        out["deduct_stock_on"] = raw["deduct_stock_on"]
    for key in _BOOL_KEYS:
        if raw.get(key) is not None:
            out[key] = bool(raw[key])
    return out


def restaurant_settings_of(company) -> dict:
    """Korxona sozlamalari standart qiymatlar bilan to'ldirilgan holda (format sukutlari ustidan saqlangan qiymatlar)."""
    saved = getattr(company, "restaurant_settings", None) if company is not None else None
    saved = saved if isinstance(saved, dict) else {}
    fmt = saved.get("format") if saved.get("format") in FORMATS else DEFAULT_FORMAT
    merged = settings_for_format(fmt)
    for k in DEFAULT_SETTINGS:
        if saved.get(k) is not None:
            merged[k] = saved[k]
    return merged


def is_restaurant_company(company) -> bool:
    return bool(company is not None and getattr(company, "business_type", None) == RESTAURANT)


def is_restaurant(db: Session, company_id: Optional[int]) -> bool:
    if not company_id:
        return False
    from app.models.company import Company
    return is_restaurant_company(db.get(Company, company_id))


def provision_restaurant(db: Session, company, branch, fmt: Optional[str] = None) -> dict:
    """Restoran korxonasi filiali uchun boshlang'ich ma'lumotlar (R0.3). Commit qilmaydi.

    Takroriy chaqiruv xavfsiz: allaqachon bor narsa (nomi bo'yicha) qayta yaratilmaydi.
    Yaratadi: filialda "Oshxona" ombori (ingredientlar shundan yechiladi, `get_kitchen_warehouse`), sexlar,
    zal va stollar (stol xizmati bo'lsa), menyu kategoriyalari, sozlamalar (format sukutlari).
    """
    from app.models.category import Category
    from app.models.restaurant import Hall, KitchenStation, RestaurantTable
    from app.models.warehouse import Warehouse, WarehouseType

    settings = restaurant_settings_of(company)
    if fmt is not None:
        fmt = normalize_format(fmt)
        if (company.restaurant_settings or {}).get("format") != fmt:
            settings = settings_for_format(fmt)
    created = {"warehouse": False, "stations": 0, "halls": 0, "tables": 0, "categories": 0}

    kitchen = db.query(Warehouse).filter(
        Warehouse.company_id == company.id, Warehouse.branch_id == branch.id,
        Warehouse.name == KITCHEN_WAREHOUSE_NAME,
    ).first()
    if kitchen is None:
        kitchen = Warehouse(name=KITCHEN_WAREHOUSE_NAME, type=WarehouseType.raw_material,
                            company_id=company.id, branch_id=branch.id, is_active=True, is_default=False)
        db.add(kitchen)
        db.flush()
        created["warehouse"] = True

    # sexlar korxona darajasida: faqat korxonada hali birorta sex bo'lmasa yaratiladi
    if not db.query(KitchenStation.id).filter(KitchenStation.company_id == company.id).first():
        for i, name in enumerate(DEFAULT_STATIONS):
            db.add(KitchenStation(company_id=company.id, name=name, sort_order=i))
            created["stations"] += 1

    if settings.get("table_service"):
        has_hall = db.query(Hall.id).filter(Hall.company_id == company.id, Hall.branch_id == branch.id).first()
        if not has_hall:
            hall = Hall(company_id=company.id, branch_id=branch.id, name=DEFAULT_HALL, sort_order=0)
            db.add(hall)
            db.flush()
            created["halls"] = 1
            for i in range(DEFAULT_TABLES):
                db.add(RestaurantTable(company_id=company.id, hall_id=hall.id, name=str(i + 1), seats=4,
                                       x=(i % 5) * 3, y=(i // 5) * 3, w=2, h=2, shape="rect"))
                created["tables"] += 1

    existing_cat = {n for (n,) in db.query(Category.name).filter(
        Category.company_id == company.id, Category.is_deleted == False)}  # noqa: E712
    for i, name in enumerate(DEFAULT_CATEGORIES):
        if name not in existing_cat:
            db.add(Category(name=name, company_id=company.id, sort_order=i))
            created["categories"] += 1

    company.restaurant_settings = settings
    db.flush()
    created["roles"] = ensure_default_roles(db, company.id)
    return created


# Tayyor restoran rollari (rol ruxsatlarining `restaurant` bo'limi; app/services/restaurant_orders.rest_perms o'qiydi).
# Xodimga rol biriktiriladi, asosiy tizim roli (masalan kassir) alohida tanlanadi.
ROLE_TEMPLATES = {
    "Ofitsiant": {"orders": True, "waiter": True, "all_tables": False, "take_payment": False, "move_table": False,
                  "kitchen": False, "cancel_sent": False, "unlock_precheck": False, "discount_max": 0},
    "Oshpaz": {"orders": False, "waiter": False, "all_tables": False, "take_payment": False, "move_table": False,
               "kitchen": True, "cancel_sent": False, "unlock_precheck": False, "discount_max": 0},
    "Kassir (restoran)": {"orders": True, "waiter": False, "all_tables": True, "take_payment": True,
                          "move_table": True, "kitchen": False, "cancel_sent": False, "unlock_precheck": False,
                          "discount_max": 0},
    "Zal menejeri": {"orders": True, "waiter": False, "all_tables": True, "take_payment": True, "move_table": True,
                     "kitchen": True, "cancel_sent": True, "unlock_precheck": True, "discount_max": 20},
}


def ensure_default_roles(db: Session, company_id: int) -> int:
    """Korxonada yo'q tayyor rollarni yaratadi (nomi bo'yicha; mavjudiga tegmaydi). Qaytaradi: yaratilganlar soni."""
    from app.models.role import Role
    have = {n for (n,) in db.query(Role.name).filter(Role.company_id == company_id)}
    made = 0
    for name, perms in ROLE_TEMPLATES.items():
        if name in have:
            continue
        db.add(Role(name=name, company_id=company_id, permissions={"restaurant": dict(perms)}, is_system=False))
        made += 1
    if made:
        db.flush()
    return made


def get_kitchen_warehouse(db: Session, company_id: int, branch_id: int):
    """Filialning oshxona ombori ("Oshxona"); bo'lmasa filialning asosiy ombori."""
    from app.models.warehouse import Warehouse
    from app.services.branch_provisioning import get_default_warehouse
    wh = db.query(Warehouse).filter(
        Warehouse.company_id == company_id, Warehouse.branch_id == branch_id,
        Warehouse.name == KITCHEN_WAREHOUSE_NAME, Warehouse.is_active == True,  # noqa: E712
    ).order_by(Warehouse.id).first()
    return wh or get_default_warehouse(db, company_id, branch_id)
