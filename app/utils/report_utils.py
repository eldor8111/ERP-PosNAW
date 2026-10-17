"""Hisobotlar uchun umumiy yordamchilar: vaqt oralig'i, sotuv/qaytarish
filtrlari, filial va valyuta ifodalari.

Ma'lumot saqlash qoidalari (barcha hisobotlar shunga tayanadi):
- Sale.total_amount, Sale.discount_amount — asosiy valyutada (UZS).
  Sotuv valyutasidagi qiymat = total_amount / Sale.exchange_rate.
- SaleItem.subtotal / unit_price / discount — mahsulotning o'z valyutasida
  (SaleItem.currency_code); UZS qiymati = subtotal * SaleItem.exchange_rate.
- SaleItem.cost_price — UZS (FIFO partiya tannarxi).
- Sotuv hujjati raqami "S...", qaytarish hujjati raqami "R..." bilan boshlanadi.
  Qaytarilgan asl sotuv "partial_refund"/"refunded" statusini oladi, lekin u
  haqiqiy sotuv bo'lib qoladi — qaytarilgan summa "R" hujjatida alohida turadi.
  Shuning uchun asl sotuv + (−qaytarish hujjati) = sof natija.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, case, func, not_, or_, select
from sqlalchemy.orm import Session

from app.models.sale import Sale, SaleItem, SaleStatus

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Asia/Tashkent")
except Exception:  # tzdata topilmasa — Toshkentda yozgi vaqt yo'q, UTC+5
    LOCAL_TZ = timezone(timedelta(hours=5))


# ─── Vaqt oralig'i ───────────────────────────────────────────────────────────
# Chegaralar Toshkent vaqti bilan tz-aware beriladi. Postgres ularni saqlangan
# vaqt bilan sessiya zonasi orqali solishtiradi, shuning uchun kun 00:00 da
# boshlanadi (avval UTC yarim tuni, ya'ni Toshkent 05:00 edi).

def local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


def local_day_start(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=LOCAL_TZ)


def _today_range():
    """Bugungi kun (Toshkent vaqti) boshlanishi va tugashi."""
    today = local_today()
    return local_day_start(today), local_day_start(today + timedelta(days=1))


def _date_range(date_from: Optional[date], date_to: Optional[date]):
    start = local_day_start(date_from) if date_from else datetime(2000, 1, 1, tzinfo=LOCAL_TZ)
    end = local_day_start(date_to + timedelta(days=1)) if date_to else datetime(2100, 1, 1, tzinfo=LOCAL_TZ)
    return start, end


def _to_date(value) -> Optional[date]:
    """'YYYY-MM-DD' (str), `date` yoki `datetime` -> `date`; bo'sh -> None; noto'g'ri satr -> 400."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Sana noto'g'ri: YYYY-MM-DD ko'rinishida kiriting")


def date_bounds(date_from, date_to):
    """Sana filtri chegaralari — BARCHA sahifalar (Moliya, Kassa tarixi, Hisobotlar) uchun yagona funksiya (T2.8).

    Yarim ochiq `[start, end)` oraliq, Toshkent vaqtida (tz-aware): `start` = `date_from` 00:00,
    `end` = `date_to` dan KEYINGI kun 00:00 (23:59:59 yopiq chegarasi emas, shuning uchun
    23:59:59.999999 dagi yozuv ham tushadi). Bo'sh chegara — juda erta/kech sana.
    Filtr: `col >= start` va `col < end`. Bir xil `date_from == date_to` bitta kunni beradi.
    """
    return _date_range(_to_date(date_from), _to_date(date_to))


# ─── Sotuv / qaytarish hujjatlari ────────────────────────────────────────────

SALE_DOC_STATUSES = (SaleStatus.completed, SaleStatus.partial_refund, SaleStatus.refunded)


def is_return_doc():
    """Qaytarish hujjati (R... raqamli Sale)."""
    return Sale.number.like("R%")


def sale_doc_filter():
    """Haqiqiy sotuvlar — keyinchalik qisman/to'liq qaytarilganlari ham."""
    return and_(not_(is_return_doc()), Sale.status.in_(SALE_DOC_STATUSES))


def return_doc_filter():
    return and_(is_return_doc(), Sale.status == SaleStatus.refunded)


def sale_or_return_filter():
    return or_(sale_doc_filter(), return_doc_filter())


def doc_sign():
    """Sotuv +1, qaytarish hujjati −1."""
    return case((is_return_doc(), -1), else_=1)


# ─── Ichki (daromad bo'lmagan) tranzaksiyalar ────────────────────────────────
# Eski smena inkassatsiyasi Transaction(income, reference_type="shift") bo'lib yozilgan:
# bu pul sotuvda allaqachon "sale" sifatida hisoblangan. Qatorlar audit uchun qoladi,
# lekin kirim/chiqim, kassa balansi va P&L dan chiqariladi (qora ro'yxat — oq ro'yxat
# boshqa joylarda yozilgan haqiqiy kirimlarni yo'qotishi mumkin).
INTERNAL_TX_REFS = ("shift",)
OTHER_INCOME_EXCLUDED_REFS = (
    "sale", "sale_payment", "customer_debt_payment", "customer_payment",
) + INTERNAL_TX_REFS


def tx_not_internal():
    """`Transaction` filtri: ichki harakat (smena inkassatsiyasi) bo'lmagan yozuvlar."""
    from app.models.moliya import Transaction
    return or_(
        Transaction.reference_type.is_(None),
        Transaction.reference_type.notin_(INTERNAL_TX_REFS),
    )


def tx_cash_flow_filter():
    """`Transaction` filtri: haqiqiy pul oqimi.

    `tx_not_internal()` + naqd bo'lmagan to'lov turlari (qarz/keshbek) chiqariladi.
    Eski sotuvlarda qarz qatori ham kirim bo'lib yozilgan — ular bazadan o'chirilmaydi
    (reference_type='sale' bo'yicha sotuvni o'chirish/tahrirlash ularga tayanadi),
    faqat hisobotdan yashiriladi. `payment_type` NULL bo'lgan yozuvlar saqlanadi.
    """
    from app.models.moliya import Transaction
    return and_(
        tx_not_internal(),
        or_(
            Transaction.payment_type.is_(None),
            Transaction.payment_type.notin_(("debt", "cashback")),
        ),
    )


# ─── Valyuta ifodalari ───────────────────────────────────────────────────────

def sale_rate():
    return func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)


def item_rate():
    return func.coalesce(func.nullif(SaleItem.exchange_rate, 0), 1)


def item_revenue_uzs():
    """Sotuv qatorining UZS dagi tushumi (qator chegirmasi ayirilgan)."""
    return SaleItem.subtotal * item_rate()


def item_cost_uzs():
    return SaleItem.cost_price * SaleItem.quantity


def currency_code_map(db: Session, company_id: int) -> dict:
    """{currency_id: code} — Sale.currency_id ni kodga aylantirish uchun."""
    from app.models.currency import Currency
    rows = (
        db.query(Currency.id, Currency.code)
        .filter(or_(Currency.company_id == company_id, Currency.company_id.is_(None)))
        .all()
    )
    return {r.id: (r.code or "UZS").upper() for r in rows}


def currency_rate_map(db: Session, company_id: int) -> dict:
    """{code: joriy kurs} — qarzlarni UZS ekvivalentida saralash uchun.

    T2.7: bir xil kod uchun korxona kursi, u bo'lmasa global (NULL) kurs — har safar bir xil
    (`currency_service.rate_map`)."""
    from app.services.currency_service import rate_map
    return {code: float(rate) for code, rate in rate_map(db, company_id).items()}


# ─── Davr xulosasi (Telegram/AI hisobotlari uchun) ───────────────────────────

def sales_summary(db: Session, company_id: int, start: datetime, end: Optional[datetime] = None,
                  wh_ids: Optional[list] = None, sale_filter=None) -> dict:
    """Davr bo'yicha sotuv xulosasi, hammasi UZS da.

    count/gross — sotuv hujjatlari (qisman/to'liq qaytarilganlari ham),
    returns — qaytarish hujjatlari, net = gross − returns.
    paid_* va paid_amount sotuv valyutasida saqlanadi, shuning uchun kursga ko'paytiriladi.
    `wh_ids` berilsa (T2.4) — faqat shu omborlar sotuvlari (None — filtr yo'q, bo'sh ro'yxat — hech narsa).
    `sale_filter` — qo'shimcha SQL sharti (masalan `sale_branch_filter(...)`: T1.9 filial snapshot'i).
    """
    base = [Sale.company_id == company_id, Sale.created_at >= start]
    if end is not None:
        base.append(Sale.created_at < end)
    if wh_ids is not None:
        base.append(Sale.warehouse_id.in_(list(wh_ids)))
    if sale_filter is not None:
        base.append(sale_filter)
    rate = sale_rate()
    outstanding = Sale.total_amount - Sale.paid_amount * rate
    sales = db.query(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.total_amount), 0),
        func.coalesce(func.sum(func.coalesce(Sale.paid_cash, 0) * rate), 0),
        func.coalesce(func.sum(func.coalesce(Sale.paid_card, 0) * rate), 0),
        func.coalesce(func.sum(Sale.discount_amount), 0),
        func.coalesce(func.sum(case((outstanding > 0.01, outstanding), else_=0)), 0),
    ).filter(*base, sale_doc_filter()).one()
    returns = db.query(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.total_amount), 0),
    ).filter(*base, return_doc_filter()).one()

    gross = float(sales[1] or 0)
    returns_total = float(returns[1] or 0)
    return {
        "count": int(sales[0] or 0),
        "gross": gross,
        "cash": float(sales[2] or 0),
        "card": float(sales[3] or 0),
        "discount": float(sales[4] or 0),
        "debt": float(sales[5] or 0),
        "returns_count": int(returns[0] or 0),
        "returns": returns_total,
        "net": gross - returns_total,
    }


def day_sales_summary(db: Session, company_id: int, day: date,
                      wh_ids: Optional[list] = None, sale_filter=None) -> dict:
    """Kunlik xulosa. `wh_ids`/`sale_filter` — `sales_summary` dagi kabi (T2.9: AI filial doirasi)."""
    start, end = _date_range(day, day)
    return sales_summary(db, company_id, start, end, wh_ids=wh_ids, sale_filter=sale_filter)


def low_stock_product_count(db: Session, company_id: int, warehouse_ids: Optional[list] = None,
                            default_threshold: int = 10) -> int:
    """Zaxirasi kam MAHSULOTLAR soni (har mahsulot bir marta; StockLevel qatorlari emas).

    Faqat faol omborlar, `is_deleted == False` va `status == active` mahsulotlar. Mahsulot qoldig'i
    (omborlar bo'yicha yig'indi) chegaradan kam bo'lsa sanaladi; chegara — `Product.min_stock`
    (> 0 bo'lsa), aks holda `default_threshold`. `warehouse_ids` berilsa — faqat shu omborlar
    (bo'sh ro'yxat — 0)."""
    from app.models.inventory import StockLevel
    from app.models.product import Product, ProductStatus
    from app.models.warehouse import Warehouse

    if warehouse_ids is not None and not list(warehouse_ids):
        return 0
    qty = func.sum(StockLevel.quantity)
    threshold = case((Product.min_stock > 0, Product.min_stock), else_=default_threshold)
    q = (
        db.query(StockLevel.product_id)
        .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        .join(Product, Product.id == StockLevel.product_id)
        .filter(
            Warehouse.company_id == company_id,
            Warehouse.is_active.isnot(False),
            Product.company_id == company_id,
            Product.is_deleted.isnot(True),
            Product.status == ProductStatus.active,
        )
    )
    if warehouse_ids is not None:
        q = q.filter(Warehouse.id.in_(list(warehouse_ids)))
    sub = q.group_by(StockLevel.product_id, Product.min_stock).having(qty < threshold).subquery()
    return int(db.query(func.count()).select_from(sub).scalar() or 0)


# ─── Filial ──────────────────────────────────────────────────────────────────

def branch_warehouse_ids(db: Session, company_id: int, branch_id: Optional[int]) -> Optional[list]:
    """Filial omborlari ID lari. branch_id berilmasa None (filtr qo'llanmaydi).

    `branch_id == UNASSIGNED_BRANCH` (-1) — filialsiz guruh: `Warehouse.branch_id IS NULL` omborlar (T2.2)."""
    if not branch_id:
        return None
    from app.models.warehouse import Warehouse
    from app.services.pnl_service import UNASSIGNED_BRANCH
    cond = Warehouse.branch_id.is_(None) if branch_id == UNASSIGNED_BRANCH else Warehouse.branch_id == branch_id
    rows = (
        db.query(Warehouse.id)
        .filter(cond, Warehouse.company_id == company_id)
        .all()
    )
    return [r[0] for r in rows]


def resolve_dashboard_scope(db: Session, user, ctx, branch_id: Optional[int] = None):
    """Dashboard filial doirasi (T2.4): `(filial_id, ombor_idlari)`.

    - aniq `branch_id`: begona korxona filiali — 404; cheklangan xodim (ruxsat etilgan filiallari bor)
      uchun ruxsatsiz filial — 403;
    - berilmasa: joriy kontekst (X-Branch-Id / biriktirilgan filial), yoki ruxsat etilgan filiallar omborlari;
    - hech narsa cheklanmagan bo'lsa `(None, None)` — butun korxona.
    """
    from fastapi import HTTPException
    from app.core.branch_context import BRANCH_FORBIDDEN, BRANCH_NOT_FOUND
    from app.models.branch import Branch
    from app.models.warehouse import Warehouse

    cid = getattr(user, "company_id", None)
    if branch_id:
        if cid is not None:  # korxonasiz super_admin uchun tekshiruv yo'q
            ok = db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == cid).first()
            if not ok:
                raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
        allowed = getattr(ctx, "allowed_branch_ids", None)
        if allowed is not None and branch_id not in allowed:
            raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
        return branch_id, branch_warehouse_ids(db, cid, branch_id)
    ctx_branch = getattr(ctx, "branch_id", None)
    if ctx_branch:
        return ctx_branch, branch_warehouse_ids(db, cid, ctx_branch)
    allowed = getattr(ctx, "allowed_branch_ids", None)
    if allowed is not None:
        if not allowed:
            return None, []
        rows = db.query(Warehouse.id).filter(
            Warehouse.company_id == cid, Warehouse.branch_id.in_(list(allowed)),
        ).all()
        return None, [r[0] for r in rows]
    return None, None


def sale_branch_filter(branch_id: Optional[int], db: Optional[Session] = None, company_id: Optional[int] = None):
    """Sotuv filial filtri (T1.9): `Sale.branch_id` snapshot'i bo'yicha (ombor hozirgi filiali emas).

    branch_id berilmasa None (filtr qo'llanmaydi). Stock/partiya hisobotlari uchun
    `branch_warehouse_ids` qoladi.

    T2.2: `branch_id == UNASSIGNED_BRANCH` (-1) — filialsiz sotuvlar: `Sale.branch_id IS NULL` va ombori
    yo'q yoki ombori filialsiz. `db` va `company_id` berilsa, snapshot'i bo'sh eski sotuvlar ombor filiali
    bo'yicha hisoblanadi (summa: sigma(filiallar) + filialsiz = butun korxona)."""
    if not branch_id:
        return None
    from app.models.sale import Sale
    from app.models.warehouse import Warehouse
    from app.services.pnl_service import UNASSIGNED_BRANCH

    if branch_id == UNASSIGNED_BRANCH:
        no_branch_wh = (
            select(Warehouse.id).where(Warehouse.branch_id.is_(None))
            if company_id is None
            else select(Warehouse.id).where(Warehouse.branch_id.is_(None), Warehouse.company_id == company_id)
        )
        return and_(
            Sale.branch_id.is_(None),
            or_(Sale.warehouse_id.is_(None), Sale.warehouse_id.in_(no_branch_wh)),
        )
    if db is None or company_id is None:
        return Sale.branch_id == branch_id
    # Snapshot yo'q (eski) sotuv — ombori hozirgi filiali bo'yicha
    wh_ids = select(Warehouse.id).where(Warehouse.branch_id == branch_id, Warehouse.company_id == company_id)
    return or_(
        Sale.branch_id == branch_id,
        and_(Sale.branch_id.is_(None), Sale.warehouse_id.in_(wh_ids)),
    )


# ─── Qarz balanslari ─────────────────────────────────────────────────────────

def normalize_balances(balances, debt_balance, debt_currency) -> dict:
    """Mijoz/ta'minotchi qarzini valyuta bo'yicha dict ga keltiradi.

    Asosiy manba — debt_balances JSON (Mijozlar va Moliya sahifalari ham shuni
    ishlatadi); u bo'sh bo'lsa eski debt_balance/debt_currency olinadi.
    """
    result: dict = {}
    for code, amt in dict(balances or {}).items():
        try:
            value = float(amt or 0)
        except (TypeError, ValueError):
            continue
        key = str(code).strip().upper() or "UZS"
        result[key] = result.get(key, 0.0) + value
    if not result and float(debt_balance or 0) > 0:
        key = (debt_currency or "UZS").strip().upper() or "UZS"
        result = {key: float(debt_balance)}
    return result


def load_debtors(db: Session, model, company_id: int) -> list:
    """Qarzdor mijoz/ta'minotchilar: [(obyekt, {valyuta: musbat qarz})]."""
    from sqlalchemy import String, cast

    rows = (
        db.query(model)
        .filter(
            model.company_id == company_id,
            or_(
                model.debt_balance > 0,
                cast(model.debt_balances, String).notin_(["{}", "null"]),
            ),
        )
        .all()
    )
    result = []
    for obj in rows:
        balances = normalize_balances(obj.debt_balances, obj.debt_balance, getattr(obj, "debt_currency", None))
        positive = {code: round(amt, 2) for code, amt in balances.items() if amt > 0.009}
        if positive:
            result.append((obj, positive))
    return result


def load_debtors_by_branch(db: Session, company_id: int, branch_id: Optional[int] = None, branch_ids=None) -> list:
    """Qarzdor mijozlar filial kesimida (T2.6, `customer_debt_log` jurnalidan): [(mijoz, filial_id, {valyuta: qarz})].

    `branch_id` — aniq filial (`-1` — filialsiz), `branch_ids` — ruxsat etilgan filiallar to'plami;
    ikkalasi ham berilmasa barcha filiallar. Bir mijoz bir necha filialda qarzdor bo'lsa, har filial alohida qator."""
    from app.services.customer_ledger import debt_by_branch
    data = debt_by_branch(db, company_id, branch_id, branch_ids)
    return [(r["customer"], r["branch_id"], r["debts"]) for r in data["customers"]]


# ─── Savdo rejasi: oy chegaralari va filial bo'yicha sof sotuv (T4.7) ─────────

def month_range(month_start: date):
    """Oy (Toshkent vaqti) yarim ochiq oralig'i: `[oy 1-kuni 00:00, keyingi oy 1-kuni 00:00)`."""
    nxt = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return local_day_start(month_start), local_day_start(nxt)


def days_in_month(month_start: date) -> int:
    return ((month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - month_start).days


def net_sales_by_branch(db: Session, company_id: int, start: datetime, end: datetime,
                        by_seller: bool = False) -> dict:
    """Davr sof savdosi (UZS; qaytarishlar ayirilgan, bekor/kutilayotgan kirmaydi): `{filial_id: summa}`.

    `by_seller=True` — `{(filial_id, cashier_id): summa}`. Filial = sotuv snapshot'i (`Sale.branch_id`),
    bo'lmasa ombor filiali (T1.9 gacha yozilgan eski sotuvlar). Filiali aniqlanmagan sotuvlar `None` kalitida.
    Qoida `/sales-report/cashier-report` bilan bir xil (`sale_or_return_filter` + `doc_sign`)."""
    from app.models.warehouse import Warehouse

    branch = func.coalesce(Sale.branch_id, Warehouse.branch_id)
    cols = [branch.label("bid")]
    if by_seller:
        cols.append(Sale.cashier_id.label("uid"))
    q = (
        db.query(*cols, func.coalesce(func.sum(doc_sign() * Sale.total_amount), 0).label("net"))
        .select_from(Sale)
        .outerjoin(Warehouse, Warehouse.id == Sale.warehouse_id)
        .filter(Sale.company_id == company_id, Sale.created_at >= start, Sale.created_at < end,
                sale_or_return_filter())
        .group_by(*cols)
    )
    out: dict = {}
    for r in q.all():
        key = (r.bid, r.uid) if by_seller else r.bid
        out[key] = out.get(key, 0.0) + float(r.net or 0)
    return out


def plan_percent(fact: float, target: Optional[float]) -> Optional[float]:
    """Bajarilish foizi (2 xona); reja yo'q yoki 0 bo'lsa None."""
    if target is None or not float(target):
        return None
    return round(float(fact) / float(target) * 100, 2)


def plan_summary(db: Session, company_id: int, month_start: date, branch_ids: Optional[list] = None) -> dict:
    """`{target, fact, percent}` — oy bo'yicha filial rejalari yig'indisi va sof sotuv fakti.

    `branch_ids=None` — butun korxona (fakt: barcha sotuvlar), ro'yxat — faqat shu filiallar.
    Reja qo'yilmagan bo'lsa `target=None`, `percent=None`."""
    from app.models.sales_target import SalesTarget

    tq = db.query(func.sum(SalesTarget.revenue_target), func.count(SalesTarget.id)).filter(
        SalesTarget.company_id == company_id,
        SalesTarget.period_month == month_start,
        SalesTarget.user_id.is_(None),
    )
    if branch_ids is not None:
        tq = tq.filter(SalesTarget.branch_id.in_(list(branch_ids)))
    total, cnt = tq.one()
    target = float(total) if cnt else None
    start, end = month_range(month_start)
    by_branch = net_sales_by_branch(db, company_id, start, end)
    if branch_ids is None:
        fact = sum(by_branch.values())
    else:
        wanted = set(branch_ids)
        fact = sum(v for k, v in by_branch.items() if k in wanted)
    fact = round(fact, 2)
    return {"target": target, "fact": fact, "percent": plan_percent(fact, target)}
