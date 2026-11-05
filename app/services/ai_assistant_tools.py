"""E-code AI yordamchi (Claude) vositalari.

O'qish vositalari: mahsulot/mijoz/ta'minotchi qidirish (nom, shtrix-kod, ta'sir etuvchi modda), qoldiq,
omborlar, ta'minotchi qarzlari. Amal vositalari: kirim/xarid, chiqim, mijoz qarzini tuzatish, qarz to'lovi,
yangi mahsulot. Amallar avval `preview()` (hech narsa yozmaydi) -> tasdiq kartasi -> foydalanuvchi
"Tasdiqlash" bosgandan keyin `execute()`. `execute()` oddiy UI chaqiradigan router/servis funksiyalarini
aynan chaqiradi (alohida "AI yo'li" yo'q) va rolni qayta tekshiradi.

ASSISTANT_TOOLS — yordamchiga beriladigan vositalar ro'yxati (eski vositalardan faqat ishonchlilari).
"""
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.services.ai_tools_registry import (
    AITool, AIToolRegistry, _transliterate_to_cyrillic, _transliterate_to_latin, needs_confirmation,
)

# Chatdan foydalanadigan rollar
CHAT_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant,
              UserRole.warehouse, UserRole.cashier)
LEADER_ROLES = (UserRole.admin, UserRole.director)                      # pulga oid amallar
STOCK_ROLES = (UserRole.admin, UserRole.director, UserRole.manager)     # tovar amallari
SENSITIVE_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant)  # foyda/tannarx

# Yordamchiga beriladigan vositalar (nomi bo'yicha alifbo tartibida yuboriladi — kesh barqaror bo'lsin)
ASSISTANT_TOOLS = (
    # o'qish (mavjud vositalar)
    "get_sales_summary", "get_top_products", "get_low_stock", "get_debtors_list", "check_customer_debt",
    "get_top_customers", "get_inactive_customers", "get_new_customers_stat", "predict_stock_depletion",
    "get_profit_today", "get_product_profit",
    # o'qish (yangi)
    "match_products", "match_customers", "match_suppliers", "get_product_stock", "get_supplier_debts",
    "list_warehouses",
    # amallar (tasdiq bilan)
    "receive_goods", "stock_out", "adjust_customer_debt", "accept_debt_payment", "add_product",
)

# Mavjud vositalar uchun yordamchi sozlamalari: sarlavha, sezgirlik va Claude uchun aniqroq tavsif
_LEGACY = {
    "get_sales_summary": ("Savdo xulosasi", False,
                          "Savdo xulosasi: jami tushum, qaytarishlar, sof tushum, cheklar soni, naqd va karta. "
                          "Davr: today, yesterday, week (oxirgi 7 kun), month (oxirgi 30 kun)."),
    "get_top_products": ("Top mahsulotlar", False,
                         "Oxirgi 30 kunda eng ko'p sotilgan mahsulotlar (miqdor va tushum)."),
    "get_low_stock": ("Kam qolgan tovarlar", False,
                      "Qoldig'i minimal chegaradan (yoki berilgan sondan) kam bo'lgan mahsulotlar."),
    "get_debtors_list": ("Qarzdor mijozlar", False,
                         "Mijozlar qarzi: eng katta qarzdorlar ro'yxati (butun korxona bo'yicha)."),
    "check_customer_debt": ("Mijoz qarzi", False,
                            "Bitta mijozning hozirgi qarzi (ism bo'yicha qidiradi)."),
    "get_top_customers": ("Top mijozlar", False, None),
    "get_inactive_customers": ("Passiv mijozlar", False, None),
    "get_new_customers_stat": ("Yangi mijozlar", False, None),
    "predict_stock_depletion": ("Tugash prognozi", False, None),
    "get_profit_today": ("Foyda hisobi", True,
                         "Foyda: tushum, tannarx, sof foyda va marja (qaytarishlar ayirilgan). "
                         "Davr: today, yesterday, week, month."),
    "get_product_profit": ("Mahsulot foydasi", True, None),
}

_UNITS = ("dona", "kg", "g", "litr", "ml", "metr", "m2", "quti", "pachka", "to'plam", "juft")


# ───────────────────────── yordamchi funksiyalar ─────────────────────────

def _d(v) -> Decimal:
    try:
        return Decimal(str(v if v is not None else 0))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _num(v) -> str:
    d = _d(v)
    s = f"{d:,.3f}".rstrip("0").rstrip(".")
    return s.replace(",", " ")


def _money(v, cur: str = "so'm") -> str:
    return f"{float(_d(v)):,.0f}".replace(",", " ") + f" {cur}"


def _debts_text(balances, fallback) -> str:
    parts = []
    if isinstance(balances, dict):
        for cur, amt in balances.items():
            if abs(float(amt or 0)) > 0.004:
                parts.append(_money(amt, "so'm" if cur == "UZS" else cur))
    return ", ".join(parts) if parts else _money(fallback)


# Lotin yozuvidagi keng tarqalgan farqlar: paratsetamol/paracetamol, ksilometazolin/xylometazoline
_SPELLING = (("ts", "c"), ("c", "ts"), ("ks", "x"), ("x", "ks"), ("y", "i"))


def _name_variants(q: str) -> list:
    q = " ".join((q or "").split())
    out = [q]

    def add(v):
        if v and v.casefold() not in {o.casefold() for o in out}:
            out.append(v)
    for v in (_transliterate_to_latin(q), _transliterate_to_cyrillic(q)):
        add(v)
    latin = _transliterate_to_latin(q).casefold()
    for a, b in _SPELLING:
        if a in latin and len(out) < 7:
            add(latin.replace(a, b))
    return out


def _like(t: str) -> str:
    t = t.replace("\\", "").replace("%", "").replace("_", " ")
    return f"%{t}%"


def _name_cond(cols, q: str):
    """Har bir so'z (lotin/kirill varianti bilan) nomda uchrashi kerak."""
    conds = []
    for v in _name_variants(q):
        toks = [t for t in v.split() if t][:6]
        if toks:
            conds.append(and_(*[or_(*[c.ilike(_like(t)) for c in cols]) for t in toks]))
    return or_(*conds) if conds else None


def can_see_sensitive(user) -> bool:
    return getattr(user, "role", None) in SENSITIVE_ROLES


def _scope_wh_ids(db: Session, user) -> Optional[list]:
    """Foydalanuvchi ko'ra oladigan omborlar (filialga bog'langan xodim — o'z filiali). None = butun korxona."""
    from app.services.ai_scope import resolve_ai_scope, scope_warehouse_ids
    return scope_warehouse_ids(resolve_ai_scope(db, user))


def _stock_totals(db: Session, company_id: int, product_ids: list, wh_ids: Optional[list]) -> dict:
    from app.models.inventory import StockLevel
    from app.models.warehouse import Warehouse
    if not product_ids:
        return {}
    q = db.query(StockLevel.product_id, func.coalesce(func.sum(StockLevel.quantity), 0)).join(
        Warehouse, Warehouse.id == StockLevel.warehouse_id,
    ).filter(StockLevel.product_id.in_(product_ids), Warehouse.company_id == company_id,
             Warehouse.is_active == True)  # noqa: E712
    if wh_ids is not None:
        q = q.filter(StockLevel.warehouse_id.in_(wh_ids or [0]))
    return {pid: qty for pid, qty in q.group_by(StockLevel.product_id).all()}


def _units_map(db: Session, company_id: int, product_ids: list) -> dict:
    from app.models.product_units import ProductUnit
    out = {}
    if not product_ids:
        return out
    for u in db.query(ProductUnit).filter(ProductUnit.company_id == company_id,
                                          ProductUnit.product_id.in_(product_ids)).order_by(
            ProductUnit.product_id, ProductUnit.ratio.desc()).all():
        out.setdefault(u.product_id, []).append(u)
    return out


def _company_product(db: Session, company_id: int, product_id):
    from app.models.product import Product
    try:
        pid = int(product_id)
    except (TypeError, ValueError):
        return None
    return db.query(Product).filter(Product.id == pid, Product.company_id == company_id,
                                    Product.is_deleted == False).first()  # noqa: E712


def _parse_date(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Sana noto'g'ri: {v} (YYYY-MM-DD kerak)")


def _branch_ctx(db: Session, user):
    from app.core.branch_context import build_branch_context
    ctx = build_branch_context(db, user)
    db.info["branch_ctx"] = ctx
    return ctx


def _denied(tool) -> Optional[dict]:
    return {"reply": "Sizning rolingizga bu amal ruxsat etilmagan.", "error": True}


def _check_role(tool, user) -> Optional[dict]:
    roles = getattr(tool, "allowed_roles", None)
    if roles is not None and getattr(user, "role", None) not in roles:
        return _denied(tool)
    return None


def _fail(db: Session, exc: Exception) -> dict:
    db.rollback()
    detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
    if not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False, default=str)
    return {"reply": f"Amal bajarilmadi: {detail}", "error": True}


def _warehouse_label(db: Session, wh_id: int) -> str:
    from app.models.warehouse import Warehouse
    w = db.get(Warehouse, wh_id)
    return w.name if w else f"#{wh_id}"


def tool_allowed(user, tool_class, allow_actions: bool = True) -> bool:
    """Yordamchida shu foydalanuvchiga vosita beriladimi."""
    role = getattr(user, "role", None)
    if role not in CHAT_ROLES or tool_class.name not in ASSISTANT_TOOLS:
        return False
    if getattr(tool_class, "sensitive", False) and role not in SENSITIVE_ROLES:
        return False
    if needs_confirmation(tool_class):
        if not allow_actions:
            return False
        roles = getattr(tool_class, "allowed_roles", None) or LEADER_ROLES
        return role in roles
    return True


def tool_title(tool_class) -> str:
    return getattr(tool_class, "title", "") or _LEGACY.get(tool_class.name, (tool_class.name,))[0]


def tool_description(tool_class) -> str:
    legacy = _LEGACY.get(tool_class.name)
    desc = (legacy[2] if legacy and legacy[2] else tool_class.description) or tool_class.name
    if needs_confirmation(tool_class):
        desc += (" MUHIM: bu vosita amalni darhol bajarmaydi — foydalanuvchiga tasdiq kartasi chiqadi va amal faqat "
                 "u 'Tasdiqlash' tugmasini bosgandan keyin bajariladi.")
    return desc


def tool_is_sensitive(tool_class) -> bool:
    legacy = _LEGACY.get(tool_class.name)
    return bool(legacy[1]) if legacy else bool(getattr(tool_class, "sensitive", False))


# Mavjud vositalarga sezgirlik bayrog'ini qo'yamiz (foyda/tannarx)
for _name, (_title, _sens, _desc) in _LEGACY.items():
    _cls = AIToolRegistry.get_tool(_name)
    if _cls is not None:
        _cls.sensitive = bool(_sens)
        if not getattr(_cls, "title", ""):
            _cls.title = _title


# ───────────────────────── o'qish vositalari ─────────────────────────

@AIToolRegistry.register
class MatchProductsTool(AITool):
    name = "match_products"
    title = "Mahsulot qidirilmoqda"
    description = (
        "Mahsulotni nomi (lotin yoki kirill), shtrix-kodi yoki ta'sir etuvchi moddasi bo'yicha qidiradi. "
        "Har bir natijada id, nom, shtrix-kod, sotuv narxi, qoldiq va qadoq birliklari (quti=N dona) bor. "
        "Amaldan oldin mahsulot id sini doim shu vosita bilan aniqlang. Aniq mos keladigan bitta natija bo'lmasa "
        "taxmin qilmang: o'xshashlarini ko'rsatib foydalanuvchidan so'rang."
    )
    required_permission = "products.view"
    risk_level = "LOW"
    read_only = True
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Mahsulot nomi, nomining bir qismi yoki shtrix-kod"},
            "limit": {"type": "integer", "description": "Natijalar soni, 1-15 (standart 8)"},
        },
        "required": ["query"],
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        from app.models.product import Product
        from app.models.product_pharma import PharmaSubstance, ProductSubstance
        from app.models.product_units import ProductUnit

        q = " ".join(str(kwargs.get("query") or "").split())
        if len(q) < 2:
            return {"reply": "Qidiruv so'zi juda qisqa (kamida 2 belgi)."}
        try:
            limit = min(max(int(kwargs.get("limit") or 8), 1), 15)
        except (TypeError, ValueError):
            limit = 8
        base = db.query(Product).filter(Product.company_id == company_id, Product.is_deleted == False)  # noqa: E712
        ranked = {}

        def put(p, rank):
            if p.id not in ranked or ranked[p.id][0] > rank:
                ranked[p.id] = (rank, p)

        # 1) shtrix-kod / mahsulot kodi aynan
        for p in base.filter(or_(Product.barcode == q, Product.product_code == q,
                                 Product.extra_barcodes.like(f'%"{q}"%'))).limit(5).all():
            put(p, 0)
        unit_pids = [r[0] for r in db.query(ProductUnit.product_id).filter(
            ProductUnit.company_id == company_id, ProductUnit.barcode == q).limit(5).all()]
        for p in base.filter(Product.id.in_(unit_pids or [0])).all():
            put(p, 0)
        # 2) nom bo'yicha
        cond = _name_cond([Product.name, Product.name_ru], q)
        if cond is not None:
            folded = {v.casefold() for v in _name_variants(q)}
            for p in base.filter(cond).order_by(func.length(Product.name)).limit(60).all():
                n = (p.name or "").casefold()
                rank = 1 if n in folded else (2 if any(n.startswith(v) for v in folded) else 3)
                put(p, rank)
        # 3) ta'sir etuvchi modda (dorixona)
        scond = _name_cond([PharmaSubstance.name_uz, PharmaSubstance.name_ru, PharmaSubstance.name_lat], q)
        if scond is not None:
            sub_pids = [r[0] for r in db.query(ProductSubstance.product_id).join(
                PharmaSubstance, PharmaSubstance.id == ProductSubstance.substance_id,
            ).filter(scond, or_(PharmaSubstance.company_id == company_id,
                                PharmaSubstance.company_id.is_(None))).limit(60).all()]
            for p in base.filter(Product.id.in_(sub_pids or [0])).all():
                put(p, 4)

        if not ranked:
            return {"reply": f"'{q}' bo'yicha mahsulot topilmadi. Boshqa nom yoki shtrix-kod bilan qidirib ko'ring."}
        items = sorted(ranked.values(), key=lambda r: (r[0], len(r[1].name or ""), r[1].id))
        shown = [p for _, p in items[:limit]]
        ids = [p.id for p in shown]
        stock = _stock_totals(db, company_id, ids, _scope_wh_ids(db, user))
        units = _units_map(db, company_id, ids)
        sens = can_see_sensitive(user)
        lines = []
        for p in shown:
            row = [f"id={p.id}", p.name, f"shtrix-kod: {p.barcode}", f"narx: {_money(p.sale_price)}",
                   f"qoldiq: {_num(stock.get(p.id, 0))} {p.unit or 'dona'}"]
            if sens:
                row.append(f"tannarx: {_money(p.cost_price)}")
            if units.get(p.id):
                row.append("qadoq: " + ", ".join(f"{u.name}={_num(u.ratio)} {p.unit or 'dona'}" for u in units[p.id]))
            if getattr(p, "status", None) is not None and getattr(p.status, "value", p.status) not in ("active",):
                row.append(f"holati: {getattr(p.status, 'value', p.status)}")
            lines.append(" | ".join(row))
        exact = sum(1 for r, _ in items if r <= 1)
        head = f"Topildi: {len(items)} ta" + (f" (ko'rsatildi {len(shown)})" if len(items) > len(shown) else "")
        if exact == 1 and items[0][0] <= 1:
            head += ". Aniq mos: 1 ta (birinchi qator)"
        elif exact == 0:
            head += ". Aniq mos keladigan nom yo'q — foydalanuvchidan qaysi biri ekanini so'rang"
        return {"reply": head + "\n" + "\n".join(lines)}


@AIToolRegistry.register
class MatchCustomersTool(AITool):
    name = "match_customers"
    title = "Mijoz qidirilmoqda"
    description = ("Mijozni ismi yoki telefon raqami bo'yicha qidiradi: id, ism, telefon, joriy qarz. "
                   "Qarz amallaridan oldin mijoz id sini shu vosita bilan aniqlang; bir nechta mos kelsa so'rang.")
    required_permission = "customers.view"
    risk_level = "LOW"
    read_only = True
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Ism (bir qismi) yoki telefon"}},
        "required": ["query"],
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        from app.models.customer import Customer
        q = " ".join(str(kwargs.get("query") or "").split())
        if len(q) < 2:
            return {"reply": "Qidiruv so'zi juda qisqa."}
        digits = "".join(ch for ch in q if ch.isdigit())
        conds = [_name_cond([Customer.name], q)]
        if len(digits) >= 4:
            conds.append(Customer.phone.like(f"%{digits[-9:]}%"))
        rows = db.query(Customer).filter(Customer.company_id == company_id,
                                         or_(*[c for c in conds if c is not None])).order_by(
            func.length(Customer.name)).limit(10).all()
        if not rows:
            return {"reply": f"'{q}' bo'yicha mijoz topilmadi."}
        lines = [f"id={c.id} | {c.name} | tel: {c.phone or '-'} | qarz: {_debts_text(c.debt_balances, c.debt_balance)}"
                 + ("" if getattr(c, "is_active", True) else " | nofaol") for c in rows]
        return {"reply": f"Topildi: {len(rows)} ta\n" + "\n".join(lines)}


@AIToolRegistry.register
class MatchSuppliersTool(AITool):
    name = "match_suppliers"
    title = "Ta'minotchi qidirilmoqda"
    description = ("Ta'minotchini nomi, telefoni yoki INN bo'yicha qidiradi: id, nom, telefon, qarzimiz. "
                   "Xarid (kirim) amalidan oldin ta'minotchi id sini shu vosita bilan aniqlang.")
    required_permission = "suppliers.view"
    risk_level = "LOW"
    read_only = True
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Nom (bir qismi), telefon yoki INN"}},
        "required": ["query"],
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        from app.models.supplier import Supplier
        q = " ".join(str(kwargs.get("query") or "").split())
        if len(q) < 2:
            return {"reply": "Qidiruv so'zi juda qisqa."}
        digits = "".join(ch for ch in q if ch.isdigit())
        conds = [_name_cond([Supplier.name], q)]
        if len(digits) >= 4:
            conds += [Supplier.phone.like(f"%{digits[-9:]}%"), Supplier.inn == digits]
        rows = db.query(Supplier).filter(Supplier.company_id == company_id,
                                         or_(*[c for c in conds if c is not None])).limit(10).all()
        if not rows:
            return {"reply": f"'{q}' bo'yicha ta'minotchi topilmadi."}
        lines = [f"id={s.id} | {s.name} | tel: {s.phone or '-'} | qarzimiz: {_debts_text(s.debt_balances, s.debt_balance)}"
                 + ("" if s.is_active is not False else " | nofaol") for s in rows]
        return {"reply": f"Topildi: {len(rows)} ta\n" + "\n".join(lines)}


@AIToolRegistry.register
class GetSupplierDebtsTool(AITool):
    name = "get_supplier_debts"
    title = "Ta'minotchi qarzlari"
    description = ("Ta'minotchilarga qarzimiz: eng katta qarzlar ro'yxati va jami. Musbat — biz qarzdormiz, "
                   "manfiy — avans (ta'minotchi bizga qarzdor).")
    required_permission = "suppliers.view"
    risk_level = "LOW"
    read_only = True
    parameters = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "Nechta ta'minotchi (standart 15, ko'pi 30)"}},
        "required": [],
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        from app.models.supplier import Supplier
        try:
            limit = min(max(int(kwargs.get("limit") or 15), 1), 30)
        except (TypeError, ValueError):
            limit = 15
        base = db.query(Supplier).filter(Supplier.company_id == company_id)
        rows = base.filter(Supplier.debt_balance > 0).order_by(Supplier.debt_balance.desc()).limit(limit).all()
        total = db.query(func.coalesce(func.sum(Supplier.debt_balance), 0)).filter(
            Supplier.company_id == company_id, Supplier.debt_balance > 0).scalar()
        count = base.filter(Supplier.debt_balance > 0).count()
        adv = db.query(func.coalesce(func.sum(Supplier.debt_balance), 0)).filter(
            Supplier.company_id == company_id, Supplier.debt_balance < 0).scalar()
        if not rows:
            return {"reply": "Ta'minotchilarga qarz yo'q." + (f" Avanslar: {_money(-_d(adv))}." if _d(adv) < 0 else "")}
        lines = [f"{i}. id={s.id} | {s.name} | {_debts_text(s.debt_balances, s.debt_balance)}"
                 for i, s in enumerate(rows, 1)]
        tail = f"\nJami qarzimiz: {_money(total)} ({count} ta ta'minotchi, so'mga o'girilgan)."
        if _d(adv) < 0:
            tail += f" Berilgan avanslar: {_money(-_d(adv))}."
        return {"reply": "Ta'minotchilarga qarzimiz:\n" + "\n".join(lines) + tail}


@AIToolRegistry.register
class ListWarehousesTool(AITool):
    name = "list_warehouses"
    title = "Omborlar"
    description = "Korxonaning faol omborlari: id, nom, filial. Kirim/chiqimda ombor aniqlanmasa shu ro'yxatdan so'rang."
    required_permission = "inventory.view"
    risk_level = "LOW"
    read_only = True
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        from app.models.branch import Branch
        from app.models.warehouse import Warehouse
        wh_ids = _scope_wh_ids(db, user)
        q = db.query(Warehouse, Branch.name).outerjoin(Branch, Branch.id == Warehouse.branch_id).filter(
            Warehouse.company_id == company_id, Warehouse.is_active == True)  # noqa: E712
        if wh_ids is not None:
            q = q.filter(Warehouse.id.in_(wh_ids or [0]))
        rows = q.order_by(Warehouse.id).all()
        if not rows:
            return {"reply": "Faol ombor topilmadi."}
        return {"reply": "Omborlar:\n" + "\n".join(
            f"id={w.id} | {w.name}" + (f" | filial: {bn}" if bn else "") for w, bn in rows)}


@AIToolRegistry.register
class GetProductStockTool(AITool):
    name = "get_product_stock"
    title = "Qoldiq tekshirilmoqda"
    description = ("Bitta mahsulotning omborlar bo'yicha qoldig'i; dorixonada eng yaqin yaroqlilik muddati va "
                   "muddati o'tgan miqdor. product_id ni avval match_products bilan aniqlang.")
    required_permission = "inventory.view"
    risk_level = "LOW"
    read_only = True
    parameters = {
        "type": "object",
        "properties": {"product_id": {"type": "integer", "description": "Mahsulot id si"}},
        "required": ["product_id"],
    }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        from app.models.batch import Batch
        from app.models.inventory import StockLevel
        from app.models.warehouse import Warehouse
        p = _company_product(db, company_id, kwargs.get("product_id"))
        if not p:
            return {"reply": "Mahsulot topilmadi (id noto'g'ri yoki boshqa korxonaniki)."}
        wh_ids = _scope_wh_ids(db, user)
        q = db.query(Warehouse.id, Warehouse.name, func.coalesce(func.sum(StockLevel.quantity), 0)).join(
            StockLevel, StockLevel.warehouse_id == Warehouse.id,
        ).filter(StockLevel.product_id == p.id, Warehouse.company_id == company_id,
                 Warehouse.is_active == True)  # noqa: E712
        if wh_ids is not None:
            q = q.filter(Warehouse.id.in_(wh_ids or [0]))
        rows = q.group_by(Warehouse.id, Warehouse.name).order_by(Warehouse.id).all()
        unit = p.unit or "dona"
        total = sum((_d(r[2]) for r in rows), Decimal("0"))
        lines = [f"{p.name} (id={p.id}), narx {_money(p.sale_price)}"]
        if can_see_sensitive(user):
            lines[0] += f", tannarx {_money(p.cost_price)}"
        lines += [f"- {name} (ombor id={wid}): {_num(qty)} {unit}" for wid, name, qty in rows] or ["- qoldiq yo'q"]
        lines.append(f"Jami: {_num(total)} {unit}")
        units = _units_map(db, company_id, [p.id]).get(p.id) or []
        if units:
            lines.append("Qadoq: " + ", ".join(f"{u.name}={_num(u.ratio)} {unit}" for u in units))
        bq = db.query(Batch).filter(Batch.product_id == p.id, Batch.quantity > 0, Batch.expiry_date.isnot(None))
        if wh_ids is not None:
            bq = bq.filter(Batch.warehouse_id.in_(wh_ids or [0]))
        batches = bq.order_by(Batch.expiry_date).limit(50).all()
        if batches:
            from app.services.document_numbers import tashkent_today
            today = tashkent_today()
            expired = sum((_d(b.quantity) for b in batches if b.expiry_date.date() < today), Decimal("0"))
            fresh = [b for b in batches if b.expiry_date.date() >= today]
            if fresh:
                lines.append(f"Eng yaqin muddat: {fresh[0].expiry_date:%d.%m.%Y} ({_num(fresh[0].quantity)} {unit})")
            if expired > 0:
                lines.append(f"Muddati o'tgan: {_num(expired)} {unit}")
        return {"reply": "\n".join(lines)}


# ───────────────────────── amal vositalari (tasdiq bilan) ─────────────────────────

_ITEMS_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "maxItems": 60,
    "items": {
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "Mahsulot id si (match_products dan)"},
            "quantity": {"type": "number", "description": "Miqdor asosiy birlikda (dona/kg...). Quti berilsa "
                                                           "qadoq nisbatiga ko'paytiring"},
            "purchase_price": {"type": "number", "description": "Bir birlikning xarid narxi, so'm. Berilmasa "
                                                                "mahsulotning joriy tannarxi olinadi"},
            "expiry_date": {"type": "string", "description": "Yaroqlilik muddati YYYY-MM-DD (ixtiyoriy)"},
            "lot_number": {"type": "string", "description": "Seriya raqami (ixtiyoriy)"},
        },
        "required": ["product_id", "quantity"],
    },
}


def _resolve_receive_warehouse(db: Session, user, warehouse_id) -> tuple:
    """(ombor, xato) — /inventory/receive bilan bir xil qoida (berilmasa filialning standart ombori)."""
    from app.core.branch_context import build_branch_context
    from app.models.warehouse import Warehouse
    from app.services.warehouse_access import assert_warehouse_branch_access
    from app.services.warehouse_resolver import resolve_warehouse
    cid = user.company_id
    wh_q = db.query(Warehouse).filter(Warehouse.company_id == cid, Warehouse.is_active == True)  # noqa: E712
    try:
        if warehouse_id:
            w = wh_q.filter(Warehouse.id == int(warehouse_id)).first()
            if not w:
                return None, "Ombor topilmadi (list_warehouses bilan tekshiring)."
            assert_warehouse_branch_access(db, user, build_branch_context(db, user), w.id)
            return w, None
        ctx = build_branch_context(db, user)
        wid = resolve_warehouse(db, cid, branch_id=ctx.branch_id, purpose="receive", user=user)
        return wh_q.filter(Warehouse.id == wid).first(), None
    except HTTPException as e:
        if e.status_code == 400:
            return None, "Ombor aniqlanmadi: qaysi omborga ekanini foydalanuvchidan so'rang (list_warehouses)."
        return None, str(e.detail)


@AIToolRegistry.register
class ReceiveGoodsTool(AITool):
    name = "receive_goods"
    title = "Kirim tayyorlanmoqda"
    description = (
        "Omborga tovar kirimi (prixod). supplier_id berilsa — ta'minotchidan xarid sifatida qabul qilinadi va "
        "ta'minotchiga qarzimiz shu summaga oshadi (Xaridlar bo'limidagi kabi); berilmasa — oddiy kirim, qarz "
        "o'zgarmaydi. Mahsulot va ta'minotchi id larini avval qidiruv vositalari bilan aniqlang; bazada yo'q "
        "mahsulotni avval add_product bilan qo'shing."
    )
    required_permission = "inventory.receive"
    risk_level = "MEDIUM"
    requires_confirmation = True
    allowed_roles = STOCK_ROLES
    parameters = {
        "type": "object",
        "properties": {
            "items": _ITEMS_SCHEMA,
            "warehouse_id": {"type": "integer", "description": "Ombor id si (ixtiyoriy: berilmasa standart ombor)"},
            "supplier_id": {"type": "integer", "description": "Ta'minotchi id si (ixtiyoriy)"},
            "note": {"type": "string", "description": "Izoh (masalan faktura raqami)"},
        },
        "required": ["items"],
    }

    def _plan(self, db: Session, user, kwargs) -> dict:
        from app.models.supplier import Supplier
        cid = user.company_id
        w, err = _resolve_receive_warehouse(db, user, kwargs.get("warehouse_id"))
        if err:
            return {"error": err}
        supplier = None
        if kwargs.get("supplier_id"):
            supplier = db.query(Supplier).filter(Supplier.id == int(kwargs["supplier_id"]),
                                                 Supplier.company_id == cid).first()
            if not supplier:
                return {"error": "Ta'minotchi topilmadi (match_suppliers bilan tekshiring)."}
        items, lines, total = [], [], Decimal("0")
        for n, it in enumerate(kwargs.get("items") or [], 1):
            p = _company_product(db, cid, it.get("product_id"))
            if not p:
                return {"error": f"{n}-qator: mahsulot id={it.get('product_id')} topilmadi."}
            qty = _d(it.get("quantity"))
            if qty <= 0:
                return {"error": f"{n}-qator ({p.name}): miqdor musbat bo'lishi kerak."}
            price = _d(it.get("purchase_price")) if it.get("purchase_price") is not None else _d(p.cost_price)
            if price < 0:
                return {"error": f"{n}-qator ({p.name}): narx manfiy bo'lmasin."}
            try:
                exp = _parse_date(it.get("expiry_date"))
            except ValueError as e:
                return {"error": f"{n}-qator ({p.name}): {e}"}
            lot = (str(it.get("lot_number") or "").strip() or None)
            s = qty * price
            total += s
            extra = (f", muddat {exp:%d.%m.%Y}" if exp else "") + (f", seriya {lot}" if lot else "")
            lines.append(f"{p.name}: {_num(qty)} {p.unit or 'dona'} x {_money(price)} = {_money(s)}{extra}")
            items.append({"product_id": p.id, "quantity": float(qty), "purchase_price": float(price),
                          "expiry_date": exp.isoformat() if exp else None, "lot_number": lot})
        if not items:
            return {"error": "Kamida bitta mahsulot kerak."}
        return {"warehouse": w, "supplier": supplier, "items": items, "lines": lines, "total": total}

    def preview(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        plan = self._plan(db, user, kwargs)
        if plan.get("error"):
            return plan
        w, sup = plan["warehouse"], plan["supplier"]
        summary = (f"Xarid: {sup.name} -> {w.name}" if sup else f"Kirim: {w.name}") + f", {len(plan['items'])} ta mahsulot"
        lines = list(plan["lines"])
        if sup:
            lines.append(f"Ta'minotchiga qarzimiz {_money(plan['total'])} ga oshadi")
        args = {"items": plan["items"], "warehouse_id": w.id, "supplier_id": sup.id if sup else None,
                "note": (kwargs.get("note") or None)}
        return {"summary": summary, "lines": lines, "total": _money(plan["total"]), "arguments": args}

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        denied = _check_role(self, user)
        if denied:
            return denied
        plan = self._plan(db, user, kwargs)
        if plan.get("error"):
            return {"reply": f"Amal bajarilmadi: {plan['error']}", "error": True}
        w, sup, note = plan["warehouse"], plan["supplier"], (kwargs.get("note") or None)
        ctx = _branch_ctx(db, user)
        try:
            if sup:
                from app.models.purchase_order import POStatus
                from app.schemas.purchase_order import POCreate, POItemCreate
                from app.services.purchase_order_service import create_purchase_order
                data = POCreate(
                    supplier_id=sup.id, warehouse_id=w.id, status=POStatus.received, note=note or "E-code AI",
                    items=[POItemCreate(
                        product_id=i["product_id"], qty_ordered=Decimal(str(i["quantity"])),
                        unit_cost=Decimal(str(i["purchase_price"])),
                        expiry_date=datetime.fromisoformat(i["expiry_date"]) if i["expiry_date"] else None,
                        lot_number=i["lot_number"],
                    ) for i in plan["items"]],
                )
                po = create_purchase_order(db, data, user)
                warnings = list(getattr(po, "receive_warnings", None) or [])
                number = po.number
                db.commit()
                db.refresh(sup)
                reply = (f"Xarid {number} qabul qilindi: {len(plan['items'])} ta mahsulot, jami {_money(plan['total'])}, "
                         f"ombor: {w.name}. {sup.name} oldidagi qarzimiz endi {_debts_text(sup.debt_balances, sup.debt_balance)}.")
            else:
                from app.routers.inventory import receive_goods as ui_receive_goods
                from app.schemas.inventory import StockReceiveItem, StockReceiveRequest
                data = StockReceiveRequest(
                    warehouse_id=w.id, note=note,
                    items=[StockReceiveItem(
                        product_id=i["product_id"], quantity=Decimal(str(i["quantity"])),
                        purchase_price=Decimal(str(i["purchase_price"])),
                        expiry_date=date.fromisoformat(i["expiry_date"]) if i["expiry_date"] else None,
                        lot_number=i["lot_number"], reason=note,
                    ) for i in plan["items"]],
                )
                res = ui_receive_goods(data=data, db=db, current_user=user, ctx=ctx)
                warnings = list((res or {}).get("warnings") or [])
                reply = (f"Kirim saqlandi: {len(plan['items'])} ta mahsulot, jami {_money(plan['total'])}, "
                         f"ombor: {w.name}.")
        except Exception as e:  # noqa: BLE001 — xato matni foydalanuvchiga qaytadi
            return _fail(db, e)
        if warnings:
            reply += " Ogohlantirishlar: " + "; ".join(warnings[:10])
        return {"reply": reply}


@AIToolRegistry.register
class StockOutTool(AITool):
    name = "stock_out"
    title = "Chiqim tayyorlanmoqda"
    description = (
        "Ombordan tovar chiqimi (spisanie): brak, yo'qotish, namuna, qaytarma yoki boshqa sabab bilan. "
        "Sotuv EMAS. Mahsulot id larini avval match_products bilan aniqlang."
    )
    required_permission = "inventory.chiqim"
    risk_level = "MEDIUM"
    requires_confirmation = True
    allowed_roles = STOCK_ROLES
    parameters = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array", "minItems": 1, "maxItems": 60,
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer"},
                        "quantity": {"type": "number", "description": "Miqdor asosiy birlikda"},
                    },
                    "required": ["product_id", "quantity"],
                },
            },
            "type": {"type": "string", "enum": ["brak", "yoqotish", "namunaviy", "qaytarma", "boshqa"],
                     "description": "Chiqim turi: brak (yaroqsiz), yoqotish, namunaviy (namuna), qaytarma "
                                    "(ta'minotchiga qaytarish), boshqa"},
            "reason": {"type": "string", "description": "Sabab / izoh"},
            "warehouse_id": {"type": "integer", "description": "Ombor id si (ixtiyoriy)"},
        },
        "required": ["items", "type"],
    }
    _TYPES = {"brak": "Brak (yaroqsiz)", "yoqotish": "Yo'qotish", "namunaviy": "Namuna",
              "qaytarma": "Qaytarma", "boshqa": "Boshqa"}

    def _plan(self, db: Session, user, kwargs) -> dict:
        from app.models.inventory import StockLevel
        from app.services.inventory_service import resolve_chiqim_warehouse
        cid = user.company_id
        ctype = kwargs.get("type") or "boshqa"
        if ctype not in self._TYPES:
            return {"error": f"Chiqim turi noto'g'ri: {ctype}"}
        try:
            wh_id = resolve_chiqim_warehouse(db, user, kwargs.get("warehouse_id"))
        except HTTPException as e:
            if e.status_code == 400:
                return {"error": "Ombor aniqlanmadi: qaysi ombordan ekanini so'rang (list_warehouses)."}
            return {"error": str(e.detail)}
        items, lines = [], []
        for n, it in enumerate(kwargs.get("items") or [], 1):
            p = _company_product(db, cid, it.get("product_id"))
            if not p:
                return {"error": f"{n}-qator: mahsulot id={it.get('product_id')} topilmadi."}
            qty = _d(it.get("quantity"))
            if qty <= 0:
                return {"error": f"{n}-qator ({p.name}): miqdor musbat bo'lishi kerak."}
            have = _d(db.query(func.coalesce(func.sum(StockLevel.quantity), 0)).filter(
                StockLevel.product_id == p.id, StockLevel.warehouse_id == wh_id).scalar())
            warn = f" (omborda {_num(have)}, yetmaydi)" if have < qty else f" (omborda {_num(have)})"
            lines.append(f"{p.name}: {_num(qty)} {p.unit or 'dona'}{warn}")
            items.append({"product_id": p.id, "quantity": float(qty)})
        if not items:
            return {"error": "Kamida bitta mahsulot kerak."}
        return {"warehouse_id": wh_id, "type": ctype, "items": items, "lines": lines}

    def preview(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        plan = self._plan(db, user, kwargs)
        if plan.get("error"):
            return plan
        reason = (kwargs.get("reason") or "").strip() or None
        summary = f"Chiqim ({self._TYPES[plan['type']]}): {_warehouse_label(db, plan['warehouse_id'])}, {len(plan['items'])} ta mahsulot"
        lines = list(plan["lines"]) + ([f"Sabab: {reason}"] if reason else [])
        return {"summary": summary, "lines": lines, "total": None,
                "arguments": {"items": plan["items"], "type": plan["type"], "reason": reason,
                              "warehouse_id": plan["warehouse_id"]}}

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        denied = _check_role(self, user)
        if denied:
            return denied
        plan = self._plan(db, user, kwargs)
        if plan.get("error"):
            return {"reply": f"Amal bajarilmadi: {plan['error']}", "error": True}
        _branch_ctx(db, user)
        reason = (kwargs.get("reason") or "").strip() or "E-code AI"
        try:
            from app.routers.inventory import create_chiqim as ui_create_chiqim
            from app.schemas.inventory import ChiqimBatchItem, ChiqimBatchRequest
            data = ChiqimBatchRequest(warehouse_id=plan["warehouse_id"], items=[
                ChiqimBatchItem(product_id=i["product_id"], quantity=Decimal(str(i["quantity"])),
                                type=plan["type"], reason=reason) for i in plan["items"]])
            res = ui_create_chiqim(data=data, db=db, current_user=user)
        except Exception as e:  # noqa: BLE001
            return _fail(db, e)
        return {"reply": f"Chiqim saqlandi (hujjat {res.get('reference_id')}): {len(plan['items'])} ta mahsulot, "
                         f"ombor: {_warehouse_label(db, plan['warehouse_id'])}."}


def _company_customer(db: Session, company_id: int, customer_id):
    from app.models.customer import Customer
    try:
        cid = int(customer_id)
    except (TypeError, ValueError):
        return None
    return db.query(Customer).filter(Customer.id == cid, Customer.company_id == company_id).first()


@AIToolRegistry.register
class AdjustCustomerDebtTool(AITool):
    name = "adjust_customer_debt"
    title = "Qarz tuzatish tayyorlanmoqda"
    description = (
        "Mijoz qarzini qo'lda tuzatish (Mijozlar sahifasidagi 'Qarzni tuzatish' bilan bir xil): delta musbat — "
        "qarz oshadi (nasiya qo'shish), manfiy — kamayadi. Pul to'lovi bo'lsa accept_debt_payment ishlating. "
        "Sabab majburiy. Mijoz id sini avval match_customers bilan aniqlang."
    )
    required_permission = "customers.edit_debt"
    risk_level = "HIGH"
    requires_confirmation = True
    allowed_roles = LEADER_ROLES
    parameters = {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer"},
            "delta": {"type": "number", "description": "O'zgarish summasi: + qarz oshadi, - kamayadi"},
            "currency": {"type": "string", "description": "Valyuta kodi, standart UZS"},
            "reason": {"type": "string", "description": "Sabab (majburiy)"},
        },
        "required": ["customer_id", "delta", "reason"],
    }

    def _plan(self, db: Session, user, kwargs) -> dict:
        c = _company_customer(db, user.company_id, kwargs.get("customer_id"))
        if not c:
            return {"error": "Mijoz topilmadi (match_customers bilan tekshiring)."}
        delta = _d(kwargs.get("delta"))
        if delta == 0:
            return {"error": "O'zgarish summasi 0 bo'lmasin."}
        reason = (kwargs.get("reason") or "").strip()
        if not reason:
            return {"error": "Tuzatish sababi kerak — foydalanuvchidan so'rang."}
        cur = (kwargs.get("currency") or "UZS").strip().upper() or "UZS"
        old = _d((c.debt_balances or {}).get(cur, c.debt_balance if cur == (c.debt_currency or "UZS") else 0))
        new = old + delta
        if new < Decimal("-0.005"):
            return {"error": f"Qarz manfiy bo'lib qoladi: hozirgi qarz {_num(old)} {cur}, ayirish {_num(-delta)} {cur}."}
        return {"customer": c, "delta": delta, "currency": cur, "reason": reason, "old": old, "new": new}

    def preview(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        plan = self._plan(db, user, kwargs)
        if plan.get("error"):
            return plan
        c, cur = plan["customer"], plan["currency"]
        sign = "+" if plan["delta"] > 0 else "-"
        return {
            "summary": f"Qarz tuzatish: {c.name}",
            "lines": [f"Hozirgi qarz: {_num(plan['old'])} {cur}", f"O'zgarish: {sign}{_num(abs(plan['delta']))} {cur}",
                      f"Yangi qarz: {_num(plan['new'])} {cur}", f"Sabab: {plan['reason']}"],
            "total": f"{sign}{_num(abs(plan['delta']))} {cur}",
            "arguments": {"customer_id": c.id, "delta": float(plan["delta"]), "currency": cur, "reason": plan["reason"]},
        }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        denied = _check_role(self, user)
        if denied:
            return denied
        plan = self._plan(db, user, kwargs)
        if plan.get("error"):
            return {"reply": f"Amal bajarilmadi: {plan['error']}", "error": True}
        try:
            from app.routers.customers import DebtAdjust, DebtChange, adjust_customer_debt
            cust = adjust_customer_debt(
                customer_id=plan["customer"].id,
                data=DebtAdjust(reason=f"{plan['reason']} (E-code AI)",
                                changes=[DebtChange(currency=plan["currency"], delta=plan["delta"])]),
                db=db, current_user=user,
            )
        except Exception as e:  # noqa: BLE001
            return _fail(db, e)
        return {"reply": f"{cust.name}: qarz tuzatildi. Yangi qarz: {_debts_text(cust.debt_balances, cust.debt_balance)}."}


@AIToolRegistry.register
class AcceptDebtPaymentTool(AITool):
    name = "accept_debt_payment"
    title = "Qarz to'lovi tayyorlanmoqda"
    description = (
        "Mijozdan qarz to'lovini qabul qilish (kassaga pul tushadi, qarz kamayadi) — Mijozlar sahifasidagi "
        "'Qarzni to'lash' bilan bir xil. Mijoz id sini avval match_customers bilan aniqlang."
    )
    required_permission = "customers.payment"
    risk_level = "HIGH"
    requires_confirmation = True
    allowed_roles = LEADER_ROLES
    parameters = {
        "type": "object",
        "properties": {
            "customer_id": {"type": "integer"},
            "amount": {"type": "number", "description": "To'langan summa, so'm"},
            "payment_type": {"type": "string", "enum": ["cash", "card"], "description": "cash (naqd) yoki card (karta)"},
            "note": {"type": "string", "description": "Izoh (ixtiyoriy)"},
        },
        "required": ["customer_id", "amount"],
    }

    def _plan(self, db: Session, user, kwargs) -> dict:
        c = _company_customer(db, user.company_id, kwargs.get("customer_id"))
        if not c:
            return {"error": "Mijoz topilmadi (match_customers bilan tekshiring)."}
        amount = _d(kwargs.get("amount"))
        if amount <= 0:
            return {"error": "To'lov summasi musbat bo'lishi kerak."}
        ptype = kwargs.get("payment_type") or "cash"
        if ptype not in ("cash", "card"):
            return {"error": "To'lov turi cash yoki card bo'lishi kerak."}
        debt = _d(c.debt_balance)
        if amount > debt + Decimal("0.5"):
            return {"error": f"To'lov qarzdan katta: qarz {_money(debt)}, to'lov {_money(amount)}."}
        return {"customer": c, "amount": amount, "payment_type": ptype, "debt": debt,
                "note": (kwargs.get("note") or "").strip() or None}

    def preview(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        plan = self._plan(db, user, kwargs)
        if plan.get("error"):
            return plan
        c = plan["customer"]
        return {
            "summary": f"Qarz to'lovi: {c.name}",
            "lines": [f"Hozirgi qarz: {_money(plan['debt'])}",
                      f"To'lov: {_money(plan['amount'])} ({'naqd' if plan['payment_type'] == 'cash' else 'karta'})",
                      f"Qoladi: {_money(plan['debt'] - plan['amount'])}"],
            "total": _money(plan["amount"]),
            "arguments": {"customer_id": c.id, "amount": float(plan["amount"]),
                          "payment_type": plan["payment_type"], "note": plan["note"]},
        }

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        denied = _check_role(self, user)
        if denied:
            return denied
        plan = self._plan(db, user, kwargs)
        if plan.get("error"):
            return {"reply": f"Amal bajarilmadi: {plan['error']}", "error": True}
        _branch_ctx(db, user)
        try:
            from app.routers.customers import DebtUpdate, pay_debt
            res = pay_debt(customer_id=plan["customer"].id, data=DebtUpdate(
                amount=plan["amount"], currency="UZS", payment_type=plan["payment_type"],
                reason=plan["note"] or "Qarz to'lovi (E-code AI)"), db=db, current_user=user)
        except Exception as e:  # noqa: BLE001
            return _fail(db, e)
        return {"reply": f"{plan['customer'].name}: {_money(plan['amount'])} to'lov qabul qilindi. "
                         f"Qolgan qarz: {_money(res.get('remaining_debt'))}."}


@AIToolRegistry.register
class AddProductTool(AITool):
    name = "add_product"
    title = "Yangi mahsulot tayyorlanmoqda"
    description = (
        "Bazaga yangi mahsulot qo'shish (Mahsulotlar sahifasidagi kabi, qoldiqsiz). Avval match_products bilan "
        "bunday mahsulot yo'qligini tekshiring. Qoldiq kerak bo'lsa keyin receive_goods bilan kirim qiling."
    )
    required_permission = "products.create"
    risk_level = "MEDIUM"
    requires_confirmation = True
    allowed_roles = STOCK_ROLES
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Mahsulot nomi (to'liq)"},
            "sale_price": {"type": "number", "description": "Sotuv narxi, so'm"},
            "cost_price": {"type": "number", "description": "Tannarx (xarid narxi), so'm (ixtiyoriy)"},
            "unit": {"type": "string", "enum": list(_UNITS), "description": "O'lchov birligi (standart dona)"},
            "barcode": {"type": "string", "description": "Shtrix-kod (ixtiyoriy; berilmasa yaratiladi)"},
        },
        "required": ["name", "sale_price"],
    }

    def _plan(self, db: Session, user, kwargs) -> dict:
        from app.models.product import Product
        cid = user.company_id
        name = " ".join(str(kwargs.get("name") or "").split())
        if len(name) < 2:
            return {"error": "Mahsulot nomi kerak."}
        sale = _d(kwargs.get("sale_price"))
        cost = _d(kwargs.get("cost_price"))
        if sale <= 0:
            return {"error": "Sotuv narxi musbat bo'lishi kerak."}
        if cost < 0:
            return {"error": "Tannarx manfiy bo'lmasin."}
        unit = kwargs.get("unit") or "dona"
        barcode = str(kwargs.get("barcode") or "").strip() or None
        base = db.query(Product).filter(Product.company_id == cid, Product.is_deleted == False)  # noqa: E712
        dup = base.filter(func.lower(Product.name) == name.lower()).first()
        if dup:
            return {"error": f"'{dup.name}' nomli mahsulot allaqachon bor (id={dup.id})."}
        if barcode:
            dup = base.filter(Product.barcode == barcode).first()
            if dup:
                return {"error": f"Shtrix-kod {barcode} allaqachon '{dup.name}' (id={dup.id}) da."}
        return {"name": name, "sale_price": sale, "cost_price": cost, "unit": unit, "barcode": barcode}

    def preview(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        plan = self._plan(db, user, kwargs)
        if plan.get("error"):
            return plan
        lines = [f"Nomi: {plan['name']}", f"Sotuv narxi: {_money(plan['sale_price'])}",
                 f"Birlik: {plan['unit']}", f"Shtrix-kod: {plan['barcode'] or 'avtomatik'}"]
        if plan["cost_price"] > 0:
            lines.insert(2, f"Tannarx: {_money(plan['cost_price'])}")
        return {"summary": f"Yangi mahsulot: {plan['name']}", "lines": lines, "total": None,
                "arguments": {"name": plan["name"], "sale_price": float(plan["sale_price"]),
                              "cost_price": float(plan["cost_price"]), "unit": plan["unit"], "barcode": plan["barcode"]}}

    def execute(self, db: Session, company_id: int, user: User, **kwargs) -> dict:
        denied = _check_role(self, user)
        if denied:
            return denied
        plan = self._plan(db, user, kwargs)
        if plan.get("error"):
            return {"reply": f"Amal bajarilmadi: {plan['error']}", "error": True}
        ctx = _branch_ctx(db, user)
        try:
            from starlette.requests import Request
            from app.routers.products import create_product as ui_create_product
            from app.schemas.product import ProductCreate
            from app.services.ai_tools_crud import _gen_barcode
            barcode = plan["barcode"] or _gen_barcode(db)
            data = ProductCreate(name=plan["name"], barcode=barcode, sale_price=plan["sale_price"],
                                 cost_price=plan["cost_price"], unit=plan["unit"])
            req = Request({"type": "http", "method": "POST", "path": "/ai/assistant", "headers": [], "query_string": b""})
            out = ui_create_product(data=data, request=req, db=db, current_user=user, ctx=ctx)
        except Exception as e:  # noqa: BLE001
            return _fail(db, e)
        pid = getattr(out, "id", None) if not isinstance(out, dict) else out.get("id")
        return {"reply": f"Mahsulot qo'shildi: {plan['name']} (id={pid}), shtrix-kod {barcode}, "
                         f"narx {_money(plan['sale_price'])}."}
