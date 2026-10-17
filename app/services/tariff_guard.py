"""
Tariff Guard Service — tarif limitlarining YAGONA manbai.
Kompaniyalarning obuna tariflaridagi limitlarini (filial, ombor, xodim, tovar/shtrix-kod,
agentlar, kuryerlar, ishlab chiqarish, buyurtmalar) tekshirish, foydalanish hisobi
(`count_usage` / `build_usage_report`) va narx kalkulyatsiyasi.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models.billing import Tariff
from app.models.branch import Branch
from app.models.company import Company
from app.models.courier import Courier
from app.models.product import Product
from app.models.production_order import ProductionOrder
from app.models.user import User, UserRole, UserStatus
from app.models.user_company import UserCompany
from app.models.warehouse import Warehouse

logger = logging.getLogger(__name__)

# Tarifsiz (yoki muddati o'tgan) korxonalar uchun standart cheklovlar
DEFAULT_MAX_BRANCHES = 1
DEFAULT_MAX_USERS = 5
DEFAULT_MAX_WAREHOUSES = 1
# Shu qiymat va undan katta (yoki NULL) limit — "cheksiz" (UI ham shu qoidani ishlatadi)
UNLIMITED_THRESHOLD = 9999


class TariffLimitError(HTTPException):
    """
    Tarif limiti to'lganda ko'tariladi (T3.5): status 403, `detail` — o'zbekcha matn (satr).
    Qo'shimcha: `code="TARIFF_LIMIT"`, `limit`, `current` — frontend buni oddiy "huquq yo'q" 403 dan
    ajratadi (402 emas: axios interceptor 402 da /admin/tariflar ga majburiy redirect qiladi).
    """

    code = "TARIFF_LIMIT"

    def __init__(self, detail: str, limit: int, current: int):
        super().__init__(status_code=403, detail=detail)
        self.limit = limit
        self.current = current


# ── Faol tarif ───────────────────────────────────────────────────────────────

def _active_tariff_of(db: Session, company: Optional[Company]) -> Optional[Tariff]:
    """Siyosat: tarif yo'q -> None; obuna muddati o'tgan -> None;
    `subscription_ends_at IS NULL` va tarif bor -> tarif qaytariladi."""
    if not company or not company.tariff_id:
        return None
    ends = company.subscription_ends_at
    if ends is not None:
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        if ends < datetime.now(timezone.utc):
            return None
    return db.query(Tariff).filter(Tariff.id == company.tariff_id).first()


def get_active_tariff(db: Session, company_id: int) -> Optional[Tariff]:
    """Kompaniyaning hozirda FAOL tarifini oladi (muddati o'tgan / tarifsiz -> None)."""
    if not company_id:
        return None
    comp = db.query(Company).filter(Company.id == company_id).first()
    return _active_tariff_of(db, comp)


def get_company_tariff(db: Session, company_id: int) -> Optional[Tariff]:
    """Orqaga moslik nomi: `get_active_tariff` bilan bir xil siyosat."""
    return get_active_tariff(db, company_id)


# ── Limit qiymatlari ─────────────────────────────────────────────────────────

def _is_unlimited(value: Optional[int]) -> bool:
    return value is None or value >= UNLIMITED_THRESHOLD


def _eff_max_branches(tariff: Optional[Tariff]) -> int:
    # tarifda max_branches NULL/0 bo'lsa ham standart limit ishlaydi (TypeError bo'lmasin)
    return (tariff.max_branches or DEFAULT_MAX_BRANCHES) if tariff else DEFAULT_MAX_BRANCHES


def _eff_max_users(tariff: Optional[Tariff]) -> int:
    if tariff and tariff.max_users is not None:
        return tariff.max_users
    return DEFAULT_MAX_USERS


def _eff_max_warehouses(tariff: Optional[Tariff]) -> int:
    return (tariff.max_warehouses or DEFAULT_MAX_WAREHOUSES) if tariff else DEFAULT_MAX_WAREHOUSES


def _unl(value: Optional[int]) -> Optional[int]:
    """Cheksiz limit -> None (API'da `limit=null`)."""
    return None if _is_unlimited(value) else int(value)


def get_limits(tariff: Optional[Tariff]) -> Dict[str, Optional[int]]:
    """`max_*` qiymatlari. `None` = cheksiz (NULL yoki >= 9999).
    Tarifsiz: filial 1, xodim 5, ombor 1; qolganlari cheklanmagan (tekshiruv funksiyalari ham shunday)."""
    agents = couriers = products = production = None
    if tariff is not None:
        if not tariff.has_distribution:
            agents = couriers = 0          # modul tarifda yo'q
        else:
            agents = _unl(tariff.max_agents)
            couriers = _unl(tariff.max_couriers)
        products = _unl(tariff.max_products)
        production = _unl(tariff.max_production_orders)
    return {
        "max_branches": _unl(_eff_max_branches(tariff)),
        "max_warehouses": _unl(_eff_max_warehouses(tariff)),
        "max_users": _unl(_eff_max_users(tariff)),
        "max_products": products,
        "max_agents": agents,
        "max_couriers": couriers,
        "max_production_orders": production,
    }


# ── Foydalanish hisobi ───────────────────────────────────────────────────────

def count_branches(db: Session, company_id: int, exclude_branch_id: Optional[int] = None) -> int:
    q = db.query(Branch).filter(Branch.company_id == company_id, Branch.is_active == True)  # noqa: E712
    if exclude_branch_id is not None:
        q = q.filter(Branch.id != exclude_branch_id)
    return q.count()


def count_warehouses(db: Session, company_id: int, exclude_warehouse_id: Optional[int] = None) -> int:
    q = db.query(Warehouse).filter(Warehouse.company_id == company_id, Warehouse.is_active == True)  # noqa: E712
    if exclude_warehouse_id is not None:
        q = q.filter(Warehouse.id != exclude_warehouse_id)
    return q.count()


def count_staff(db: Session, company_id: int) -> int:
    """Xodimlar soni: `User.company_id` bo'yicha va faol `UserCompany` orqali qo'shilgan boshqa korxona
    xodimlari (distinct user_id). `super_admin`, `inactive` va marketplace agentlari (T0.18) hisobga olinmaydi."""
    skip_roles = (UserRole.super_admin, UserRole.marketplace_agent)
    ids = {
        r[0] for r in db.query(User.id).filter(
            User.company_id == company_id,
            User.status != UserStatus.inactive,
            User.role.notin_(skip_roles),
        ).all()
    }
    ids |= {
        r[0] for r in db.query(UserCompany.user_id).join(User, User.id == UserCompany.user_id).filter(
            UserCompany.company_id == company_id,
            UserCompany.is_active == True,  # noqa: E712
            User.status != UserStatus.inactive,
            User.role != UserRole.super_admin,
            UserCompany.role.notin_(skip_roles),
        ).all()
    }
    return len(ids)


def count_agents(db: Session, company_id: int, exclude_user_id: Optional[int] = None) -> int:
    q = db.query(User).filter(
        User.company_id == company_id,
        User.role == UserRole.agent,
        User.status.notin_((UserStatus.blocked, UserStatus.inactive)),
    )
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    return q.count()


def count_couriers(db: Session, company_id: int, exclude_user_id: Optional[int] = None,
                   exclude_courier_id: Optional[int] = None) -> int:
    """Faol `Courier` yozuvlari + hali mobil profili yaratilmagan faol `courier` rolidagi xodimlar."""
    q = db.query(Courier).filter(Courier.company_id == company_id, Courier.is_active == True)  # noqa: E712
    if exclude_courier_id is not None:
        q = q.filter(Courier.id != exclude_courier_id)
    if exclude_user_id is not None:
        q = q.filter((Courier.user_id.is_(None)) | (Courier.user_id != exclude_user_id))
    total = q.count()
    has_profile = db.query(Courier.id).filter(Courier.user_id == User.id, Courier.company_id == company_id)
    pending = db.query(User).filter(
        User.company_id == company_id,
        User.role == UserRole.courier,
        User.status.notin_((UserStatus.blocked, UserStatus.inactive)),
        ~has_profile.exists(),
    )
    if exclude_user_id is not None:
        pending = pending.filter(User.id != exclude_user_id)
    return total + pending.count()


def _count_products(db: Session, company_id: int) -> int:
    return db.query(Product).filter(Product.company_id == company_id, Product.is_deleted == False).count()  # noqa: E712


def _count_production_month(db: Session, company_id: int) -> int:
    now = datetime.now(timezone.utc)
    first_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    return db.query(ProductionOrder).filter(
        ProductionOrder.company_id == company_id,
        ProductionOrder.created_at >= first_of_month,
    ).count()


def count_usage(db: Session, company_id: int) -> Dict[str, int]:
    """Korxonaning joriy foydalanishi (faqat faol yozuvlar)."""
    return {
        "branches": count_branches(db, company_id),
        "warehouses": count_warehouses(db, company_id),
        "users": count_staff(db, company_id),
        "products": _count_products(db, company_id),
        "agents": count_agents(db, company_id),
        "couriers": count_couriers(db, company_id),
        "production_orders_month": _count_production_month(db, company_id),
    }


_REPORT_RESOURCES = (
    ("branches", "max_branches"),
    ("warehouses", "max_warehouses"),
    ("users", "max_users"),
    ("products", "max_products"),
    ("agents", "max_agents"),
    ("couriers", "max_couriers"),
)


def usage_items(usage: Dict[str, int], limits: Dict[str, Optional[int]]) -> Dict[str, Dict[str, Any]]:
    """Resurs bo'yicha `{used, limit, over, full}`. `over` — limitdan OSHGAN, `full` — limitga YETGAN."""
    out = {}
    for res, key in _REPORT_RESOURCES:
        used = int(usage.get(res, 0))
        limit = limits.get(key)
        out[res] = {
            "used": used,
            "limit": limit,
            "over": limit is not None and used > limit,
            "full": limit is not None and used >= limit,
        }
    return out


def build_usage_report(db: Session, company: Company) -> Dict[str, Any]:
    """`GET /billing/my-company/usage` javobi."""
    tariff = _active_tariff_of(db, company)
    limits = get_limits(tariff)
    usage = usage_items(count_usage(db, company.id), limits)
    return {
        "tariff": {"id": tariff.id, "name": tariff.name} if tariff else None,
        "limits": limits,
        "usage": usage,
        "over_limit": any(v["over"] for v in usage.values()),
        "subscription_active": tariff is not None,
        "warehouse_limit_mode": warehouse_limit_mode(),
    }


def usage_warnings(db: Session, company_id: int, tariff: Tariff) -> List[Dict[str, Any]]:
    """Joriy foydalanish YANGI tarif limitidan oshsa: `[{resource, used, limit}]` (hech narsa bloklanmaydi)."""
    items = usage_items(count_usage(db, company_id), get_limits(tariff))
    return [
        {"resource": res, "used": v["used"], "limit": v["limit"]}
        for res, v in items.items() if v["over"]
    ]


# ── Limit tekshiruvlari ──────────────────────────────────────────────────────

def _company(db: Session, company_id: int, lock: bool) -> Optional[Company]:
    """`lock=True` bo'lsa korxona qatori `FOR UPDATE` bilan qulflanadi: tekshiruvdan insertgacha
    parallel so'rovlar ketma-ket bajariladi (limitdan oshib ketmaydi)."""
    q = db.query(Company).filter(Company.id == company_id)
    if lock:
        q = q.with_for_update()
    return q.first()


def check_branch_limit(
    db: Session,
    company_id: int,
    acting_user: User,
    exclude_branch_id: Optional[int] = None,
    lock: bool = True,
) -> None:
    """
    Yangi filial qo'shishdan yoki nofaol filialni qayta yoqishdan oldin chaqiriladi.
    Agar tarif limiti to'lgan bo'lsa, 403 xatolik chiqaradi. Super Admin uchun cheklov yo'q.
    `exclude_branch_id` — sanashda hisobga olinmaydigan filial (masalan, qayta yoqilayotgan).
    """
    if acting_user.role == UserRole.super_admin:
        return

    company = _company(db, company_id, lock)
    tariff = _active_tariff_of(db, company)
    max_branches = _eff_max_branches(tariff)
    if _is_unlimited(max_branches):
        return

    current = count_branches(db, company_id, exclude_branch_id)
    if current >= max_branches:
        tariff_name = tariff.name if tariff else "Sinov"
        raise TariffLimitError(
            detail=(
                f"'{tariff_name}' tarifi bo'yicha maksimal filiallar soni: {max_branches}. "
                f"Hozir: {current}. Tarif yangilang yoki administrator bilan bog'laning."
            ),
            limit=max_branches,
            current=current,
        )


def warehouse_limit_mode() -> str:
    mode = (getattr(settings, "TARIFF_WAREHOUSE_LIMIT_MODE", "warn") or "warn").strip().lower()
    return mode if mode in ("off", "warn", "enforce") else "warn"


def check_warehouse_limit(
    db: Session,
    company_id: int,
    acting_user: User,
    exclude_warehouse_id: Optional[int] = None,
    lock: bool = True,
) -> None:
    """
    Yangi ombor yaratish yoki nofaol omborni qayta yoqishdan oldin chaqiriladi.
    Rejim `settings.TARIFF_WAREHOUSE_LIMIT_MODE`: `off` — tekshirilmaydi; `warn` — limit oshsa faqat
    `logging.warning` (usage endpointida `over=true`); `enforce` — 403. Super Admin uchun cheklov yo'q.
    """
    mode = warehouse_limit_mode()
    if mode == "off" or acting_user.role == UserRole.super_admin:
        return

    company = _company(db, company_id, lock)
    tariff = _active_tariff_of(db, company)
    max_wh = _eff_max_warehouses(tariff)
    if _is_unlimited(max_wh):
        return

    current = count_warehouses(db, company_id, exclude_warehouse_id)
    if current < max_wh:
        return
    tariff_name = tariff.name if tariff else "Sinov"
    if mode == "warn":
        logger.warning(
            "Ombor limiti oshdi (warn rejimi): company_id=%s tarif=%r limit=%s hozir=%s",
            company_id, tariff_name, max_wh, current,
        )
        return
    raise TariffLimitError(
        detail=(
            f"'{tariff_name}' tarifi bo'yicha maksimal omborlar soni: {max_wh}. "
            f"Hozir: {current}. Tarif yangilang yoki administrator bilan bog'laning."
        ),
        limit=max_wh,
        current=current,
    )


def check_user_limit(db: Session, company_id: int, acting_user: User, lock: bool = True) -> None:
    """
    Yangi xodim qo'shishdan oldin chaqiriladi (boshqa korxonadan `UserCompany` orqali qo'shilganlar ham
    hisobga olinadi). Super Admin uchun hech qanday cheklov yo'q.
    """
    if acting_user.role == UserRole.super_admin:
        return

    company = _company(db, company_id, lock)
    tariff = _active_tariff_of(db, company)
    max_users = _eff_max_users(tariff)
    if _is_unlimited(max_users):
        return

    current = count_staff(db, company_id)
    if current >= max_users:
        tariff_name = tariff.name if tariff else "Sinov"
        raise TariffLimitError(
            detail=(
                f"'{tariff_name}' tarifi bo'yicha maksimal xodimlar soni: {max_users}. "
                f"Hozir: {current}. Tarif yangilang yoki administrator bilan bog'laning."
            ),
            limit=max_users,
            current=current,
        )


def get_company_limits(db: Session, company: Company) -> dict:
    """
    Korxonaning tarif limitlari va hozirgi foydalanishi (super admin paneli, T3.2/T3.9).
    Faol tarif `get_active_tariff` siyosati bilan olinadi; tarifsiz yoki muddati o'tgan bo'lsa standart limitlar.
    Hisoblash qoidalari `check_*_limit` funksiyalari bilan bir xil.
    """
    tariff = _active_tariff_of(db, company)
    return {
        "limits": {
            "max_branches": _eff_max_branches(tariff),
            "max_users": _eff_max_users(tariff),
            "max_warehouses": _eff_max_warehouses(tariff),
        },
        "usage": {
            "active_branches": count_branches(db, company.id),
            "users": count_staff(db, company.id),
            "active_warehouses": count_warehouses(db, company.id),
        },
    }


def count_company_barcodes(db: Session, company_id: int) -> int:
    """
    Kompaniyaning barcha ishlatilgan shtrix-kodlarini hisoblaydi:
    - Asosiy shtrix-kodlar (is_deleted == False va barcode mavjud)
    - Qo'shimcha shtrix-kodlar (extra_barcodes JSON ro'yxatidagi har bir kod)
    - Variantlarning shtrix-kodlari (ProductVariant.barcode)
    """
    if not company_id:
        return 0

    import json
    from app.models.product_variant import ProductVariant

    # 1. Asosiy va extra_barcodes
    products = db.query(Product.barcode, Product.extra_barcodes).filter(
        Product.company_id == company_id,
        Product.is_deleted == False
    ).all()

    total = 0
    for p_bc, extra_bc_raw in products:
        if p_bc and str(p_bc).strip():
            total += 1
        if extra_bc_raw:
            try:
                parsed = json.loads(extra_bc_raw) if isinstance(extra_bc_raw, str) else extra_bc_raw
                if isinstance(parsed, list):
                    total += len([b for b in parsed if b and str(b).strip()])
            except Exception:
                pass

    # 2. Variantlar shtrix-kodlari
    variant_bc_count = db.query(ProductVariant.id).join(
        Product, Product.id == ProductVariant.product_id
    ).filter(
        Product.company_id == company_id,
        Product.is_deleted == False,
        ProductVariant.barcode.isnot(None),
        ProductVariant.barcode != ""
    ).count()

    total += variant_bc_count
    return total


def get_company_barcode_stats(db: Session, company_id: int) -> dict:
    """Kompaniya shtrix-kodlari limit va sarf statistikasi"""
    tariff = get_company_tariff(db, company_id)
    limit = tariff.max_products if tariff else None
    used = count_company_barcodes(db, company_id)
    percent = round((used / limit) * 100, 1) if (limit and limit > 0) else None
    return {
        "used": used,
        "limit": limit,
        "percent": percent,
        "is_warning": bool(percent and percent >= 90.0 and percent < 100.0),
        "is_exceeded": bool(limit and used >= limit),
    }


def check_product_limit(db: Session, company_id: int, count_to_add: int = 1) -> None:
    """Shtrix-kod limitini tekshiradi (masalan: Kichik do'konda 500 ta shtrix-kod).
    Faol tarif `get_active_tariff` siyosati bilan olinadi; hisob — shtrix-kodlar bo'yicha."""
    tariff = get_active_tariff(db, company_id)
    if not tariff or tariff.max_products is None:
        return

    current_count = count_company_barcodes(db, company_id)
    if current_count + count_to_add > tariff.max_products:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Sizning tarifingizda shtrix-kodlar limiti ({tariff.max_products} dona) to'ldi. "
                f"Hozirda {current_count} ta shtrix-kod band qilingan (+{count_to_add} qo'shilmoqda). "
                f"Yangi tovar qo'shish uchun tarifingizni yuqoriroq paketga yangilang yoki foydalanilmayotgan tovarlarni o'chiring."
            )
        )


def check_agent_limit(db: Session, company_id: int, exclude_user_id: Optional[int] = None) -> None:
    """Savdo agentlari (role=agent) limitini tekshiradi"""
    from app.core.features import company_has_feature
    # Modul: tarifda bor YOKI faol pullik paket/sinov bor (company_has_feature ikkalasini tekshiradi)
    if not company_has_feature(db, company_id, "distribution"):
        raise HTTPException(
            status_code=403,
            detail="Savdo agentlari (SFA) moduli sizning kompaniyangizda yoqilmagan. Distribyutsiya paketini faollashtiring yoki mos tarifga o'ting."
        )

    # Son limiti tarifdagi distribyutsiya uchun; modul faqat paket orqali yoqilgan bo'lsa tarif max_agents qo'llanmaydi
    tariff = get_active_tariff(db, company_id)
    if tariff and tariff.has_distribution and tariff.max_agents is not None:
        current_agents = count_agents(db, company_id, exclude_user_id=exclude_user_id)

        if current_agents >= tariff.max_agents:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Sizning tarifingizda savdo agentlari limiti ({tariff.max_agents} ta) to'lgan. "
                    f"Yangi agent qo'shish uchun yuqoriroq tarifga o'ting yoki qo'shimcha agent litsenziyasi oling."
                )
            )


def check_courier_limit(db: Session, company_id: int, exclude_courier_id: Optional[int] = None,
                        exclude_user_id: Optional[int] = None) -> None:
    """Yetkazib beruvchilar (kuryerlar) limitini tekshiradi.
    `exclude_courier_id` — qayta yoqilayotgan kuryer; `exclude_user_id` — roli o'zgartirilayotgan xodim."""
    from app.core.features import company_has_feature
    # Modul: tarifda bor YOKI faol pullik paket/sinov bor
    if not company_has_feature(db, company_id, "distribution"):
        raise HTTPException(
            status_code=403,
            detail="Yetkazib berish (kuryerlar) moduli sizning kompaniyangizda yoqilmagan. Distribyutsiya paketini faollashtiring yoki mos tarifga o'ting."
        )

    tariff = get_active_tariff(db, company_id)
    if tariff and tariff.has_distribution and tariff.max_couriers is not None:
        current_couriers = count_couriers(
            db, company_id, exclude_user_id=exclude_user_id, exclude_courier_id=exclude_courier_id)

        if current_couriers >= tariff.max_couriers:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Sizning tarifingizda dastavchiklar (kuryerlar) limiti ({tariff.max_couriers} ta) to'lgan. "
                    f"Yangi kuryer qo'shish uchun tarifingizni oshiring."
                )
            )


def courier_limit_reached(db: Session, company_id: int, exclude_user_id: Optional[int] = None) -> bool:
    """HTTPException ko'tarmaydigan variant (login yo'lida): yangi kuryer sig'maydimi?"""
    tariff = get_active_tariff(db, company_id)
    if not tariff or tariff.max_couriers is None:
        return False
    return count_couriers(db, company_id, exclude_user_id=exclude_user_id) >= tariff.max_couriers


def check_production_limit(db: Session, company_id: int) -> None:
    """Ishlab chiqarish (BOM / Partiyalar) ruxsati va oylik kvotasini tekshiradi"""
    from app.core.features import company_has_feature
    # Modul: tarifda bor YOKI faol pullik paket/sinov bor
    if not company_has_feature(db, company_id, "manufacturing"):
        raise HTTPException(
            status_code=403,
            detail="Ishlab chiqarish moduli sizning kompaniyangizda yoqilmagan. Ishlab chiqarish paketini faollashtiring yoki mos tarifga o'ting."
        )

    # Oylik kvota tarifdagi ishlab chiqarish uchun; modul faqat paket orqali yoqilgan bo'lsa tarif kvotasi qo'llanmaydi
    tariff = get_active_tariff(db, company_id)
    if tariff and tariff.has_manufacturing and tariff.max_production_orders is not None:
        orders_this_month = _count_production_month(db, company_id)

        if orders_this_month >= tariff.max_production_orders:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Shu oy uchun ishlab chiqarish buyurtmalari kvotasi ({tariff.max_production_orders} ta) to'lgan. "
                    f"Keyingi oy boshlanishini kuting yoki yuqori tarifga o'ting."
                )
            )


def calculate_subscription_price(tariff: Tariff, months: int, bhm: Optional[float] = None) -> Dict[str, Any]:
    """
    Obuna narxi va chegirmasini hisoblaydi.
    Mini: oyma-oy (1 oy).
    Distribyutorlar: kamida min_duration_months (masalan 3 oy).
    Chegirmalar: 3 oy - 0%, 6 oy - 10%, 12 oy - 20%.
    BHM foizi (bhm_percent) ko'rsatilgan bo'lsa, narx BHM miqdoridan kelib chiqib hisoblanadi.
    """
    min_months = tariff.min_duration_months or 1
    if months < min_months:
        raise HTTPException(
            status_code=400,
            detail=f"'{tariff.name}' tarifi kamida {min_months} oylik paket bilan faollashtiriladi."
        )

    monthly_price = float(tariff.price_per_month or 0)
    if tariff.bhm_percent and tariff.bhm_percent > 0:
        bhm_val = bhm if bhm is not None else 440000.0
        monthly_price = round(bhm_val * (float(tariff.bhm_percent) / 100.0))

    original_total = monthly_price * months

    # Chegirma foizini aniqlash
    discount_pct = 0
    if tariff.period_discounts and isinstance(tariff.period_discounts, dict):
        discount_pct = float(tariff.period_discounts.get(str(months), 0))
    else:
        if months >= 12:
            discount_pct = 20.0
        elif months >= 6:
            discount_pct = 10.0
        elif months >= 3:
            discount_pct = 0.0

    discount_amount = round(original_total * (discount_pct / 100.0), 2)
    final_price = round(original_total - discount_amount, 2)

    return {
        "tariff_id": tariff.id,
        "tariff_name": tariff.name,
        "months": months,
        "price_per_month": monthly_price,
        "original_total": original_total,
        "discount_percent": discount_pct,
        "discount_amount": discount_amount,
        "total_price": final_price,
    }
