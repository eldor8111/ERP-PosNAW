"""Mijoz qarzi (debitorlik) — yagona servis va harakatlar jurnali (T2.6).

Qoidalar (ta'minotchi uchun `supplier_ledger` namunasida):
- Qarzning yagona manbai: `Customer.debt_balances` {valyuta: summa} (musbat — mijoz qarzdor).
  `Customer.debt_balance` — shu balanslarning joriy kurs bo'yicha UZS ekvivalenti (hosila maydon).
  Ularni to'g'ridan-to'g'ri o'zgartirmang — `add_debt`, `set_balances`, `pay_debt`, `reverse_payment`,
  `write_off` dan foydalaning.
- Har bir o'zgarish `customer_debt_log` jurnaliga yoziladi (kim, qaysi filial, nima uchun).
  Invariant: har bir mijoz va valyuta uchun `SUM(delta)` = `debt_balances[valyuta]` (`reconcile` tekshiradi).
- Filial: qarz harakati `branch_id` ga (sotuv filiali; sotuvsiz bo'lsa mijoz filiali) bog'lanadi;
  to'lovda pul tushgan kassa filiali `cash_branch_id` da turadi.
- To'lov: avval to'lov valyutasidagi qarz, so'ng boshqa valyutalar (kurs bo'yicha); sotuvlarga FIFO
  (`Sale.paid_amount` SOTUV valyutasida, `Sale.total_amount` esa UZS da saqlanadi). Qarzdan ortiq to'lov
  rad etiladi (avans saqlanmaydi). Kassa topilmasa qarz o'zgartirilishidan OLDIN 400.
"""
# pyright: reportMissingImports=false
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException  # type: ignore
from sqlalchemy import func, not_  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy.orm.attributes import flag_modified  # type: ignore

from app.models.customer_debt_log import CustomerDebtLog

ZERO = Decimal("0")
ONE = Decimal("1")
EPS = Decimal("0.005")
TINY = Decimal("0.00005")
PAY_TOLERANCE_UZS = Decimal("1")          # to'lov qarzdan shuncha so'mgacha oshsa yumaloqlash deb olinadi

ERR_NOT_POSITIVE = "To'lov miqdori musbat bo'lishi kerak"
ERR_NO_WALLET = "Ochiq kassa topilmadi"
ERR_TOO_MUCH = "To'lov qarzdan ko'p"
ERR_CUSTOMER = "Mijoz topilmadi"
ERR_BRANCH = "Filial topilmadi"
WRITEOFF_REASON_MIN = 5

# Qarz to'lovi qabul qilinadigan haqiqiy to'lov turlari (qarz/keshbek/aralash emas).
# DIQQAT: "bank_transfer" ni olib tashlamang — KirimTolovlar.jsx (PAYMENT_TYPES) va finance.py uni ishlatadi.
CASH_PAYMENT_TYPES = ("cash", "card", "uzcard", "humo", "transfer", "bank", "bank_transfer", "click", "payme", "visa", "uzum")

# Jurnal turlari: hisobotda "to'lov" deb sanaladiganlar
PAYMENT_KINDS = ("payment", "reversal")


def _d(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def _code(currency) -> str:
    return (str(currency or "UZS")).strip().upper() or "UZS"


def _get(obj, key, default=None):
    """dict yoki obyekt (pydantic) dan maydon."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _rates(db: Session, company_id: Optional[int]) -> dict:
    from app.services.currency_service import rate_map
    return rate_map(db, company_id)


def _rate(rates: dict, code: str) -> Decimal:
    r = rates.get(_code(code))
    r = _d(r) if r else ONE
    return r if r > 0 else ONE


# ─── Balans ──────────────────────────────────────────────────────────────────

def balances(customer) -> dict:
    """Valyuta bo'yicha balanslar {kod: Decimal} (eski debt_balance/debt_currency dan ko'chirish bilan)."""
    result: dict = {}
    for code, amt in dict(customer.debt_balances or {}).items():
        key = _code(code)
        result[key] = result.get(key, ZERO) + _d(amt)
    if not result and _d(customer.debt_balance) > 0:
        result[_code(getattr(customer, "debt_currency", None))] = _d(customer.debt_balance)
    return result


def _save(db: Session, customer, bal: dict, rates: Optional[dict] = None) -> None:
    """Balanslarni yozadi; `debt_balance` — joriy kurs bo'yicha UZS ekvivalenti (hosila maydon)."""
    rates = rates if rates is not None else _rates(db, customer.company_id)
    cleaned = {}
    for code, amt in bal.items():
        amt = _d(amt)
        if abs(amt) >= EPS:
            cleaned[_code(code)] = float(round(amt, 4))
    customer.debt_balances = cleaned
    flag_modified(customer, "debt_balances")
    total = sum((_d(v) * _rate(rates, c) for c, v in cleaned.items()), ZERO)
    customer.debt_balance = round(total, 2)
    customer.debt_currency = "UZS"


def recompute_total(db: Session, customer, rates: Optional[dict] = None) -> None:
    """`debt_balance` ni `debt_balances` + joriy kurs bo'yicha qayta hisoblaydi (kurs o'zgarganda)."""
    _save(db, customer, balances(customer), rates)


# ─── Filial va jurnal ────────────────────────────────────────────────────────

def _sale_branch(db: Session, sale) -> Optional[int]:
    if sale is None:
        return None
    if getattr(sale, "branch_id", None):
        return sale.branch_id
    if getattr(sale, "warehouse_id", None):
        from app.models.warehouse import Warehouse
        row = db.query(Warehouse.branch_id).filter(Warehouse.id == sale.warehouse_id).first()
        return row[0] if row else None
    return None


def _user_branch(db: Session, user) -> Optional[int]:
    if user is None:
        return None
    try:
        from app.core.branch_context import effective_branch_id
        return effective_branch_id(db, user)
    except Exception:  # noqa: BLE001 — jurnal yozuvi filial aniqlay olmagani uchun to'xtamasin
        return None


def _resolve_branch(db: Session, customer, user, branch_id, sale) -> Optional[int]:
    """Qarz tegishli filial: aniq berilgan -> sotuv filiali -> mijoz filiali -> amalni bajargan xodim filiali.
    `0` hech qachon qaytarilmaydi."""
    return branch_id or _sale_branch(db, sale) or customer.branch_id or _user_branch(db, user) or None


def _log(
    db: Session, customer, *, kind: str, currency: str, delta, rate, user=None,
    branch_id: Optional[int] = None, cash_branch_id: Optional[int] = None,
    sale=None, sale_id: Optional[int] = None, tx=None, transaction_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> CustomerDebtLog:
    delta = _d(delta)
    rate = _d(rate) if rate else ONE
    if sale is not None and sale_id is None:
        if getattr(sale, "id", None) is None:
            db.flush()          # Sale hali yaratilmagan bo'lsa — id olish uchun
        sale_id = getattr(sale, "id", None)
    if tx is not None and transaction_id is None:
        if getattr(tx, "id", None) is None:
            db.flush()
        transaction_id = getattr(tx, "id", None)
    row = CustomerDebtLog(
        company_id=customer.company_id, customer_id=customer.id,
        branch_id=branch_id or None, cash_branch_id=cash_branch_id or None,
        user_id=getattr(user, "id", None), kind=kind, currency=_code(currency),
        delta=round(delta, 4), delta_uzs=round(delta * rate, 4), rate=round(rate, 4),
        sale_id=sale_id, transaction_id=transaction_id,
        reason=(reason or None),
    )
    db.add(row)
    return row


def add_debt(
    db: Session, customer, *, currency: str, amount, kind: str, user=None,
    branch_id: Optional[int] = None, sale=None, tx=None, reason: Optional[str] = None,
    cash_branch_id: Optional[int] = None, allow_negative: bool = False,
    rates: Optional[dict] = None,
) -> Optional[CustomerDebtLog]:
    """Mijoz qarzini o'zgartiradi (`amount` > 0 — qarz oshadi, < 0 — kamayadi) va jurnalga yozadi.

    Balans manfiyga tushmaydi (`allow_negative=False`): jurnalga haqiqatan o'zgargan summa yoziladi,
    shuning uchun `SUM(delta)` = balans invarianti buzilmaydi. O'zgarish bo'lmasa None qaytaradi.
    Sotuv yaratishda `sale` `db.add()` qilingan bo'lishi kerak (jurnal yozuvi flush'dan keyin bog'lanadi).
    """
    amount = _d(amount)
    if abs(amount) < TINY:
        return None
    code = _code(currency)
    rates = rates if rates is not None else _rates(db, customer.company_id)
    bal = balances(customer)
    old = bal.get(code, ZERO)
    new = old + amount
    if new < 0 and not allow_negative:
        new = ZERO
    actual = new - old
    if abs(actual) < TINY:
        return None
    bal[code] = new
    _save(db, customer, bal, rates)
    return _log(
        db, customer, kind=kind, currency=code, delta=actual, rate=_rate(rates, code), user=user,
        branch_id=_resolve_branch(db, customer, user, branch_id, sale), cash_branch_id=cash_branch_id,
        sale=sale, tx=tx, reason=reason,
    )


def log_opening(db: Session, customer, *, user=None, reason: Optional[str] = None) -> list:
    """Mijoz allaqachon qarz bilan yaratilgan (balans yozilgan) — shuni `opening` qatorlari bilan jurnalga olish."""
    rates = _rates(db, customer.company_id)
    rows = []
    for code, amt in balances(customer).items():
        if amt > EPS:
            rows.append(_log(
                db, customer, kind="opening", currency=code, delta=amt, rate=_rate(rates, code), user=user,
                branch_id=_resolve_branch(db, customer, user, None, None), reason=reason,
            ))
    return rows


def set_balances(
    db: Session, customer, new_balances: dict, user=None, reason: Optional[str] = None,
    kind: str = "edit", branch_id: Optional[int] = None,
) -> list:
    """Qarzni qo'lda belgilangan qiymatga keltiradi: har bir valyuta bo'yicha farq jurnalga yoziladi.
    Manfiy qiymat 400. Qaytaradi: yozilgan jurnal qatorlari."""
    rates = _rates(db, customer.company_id)
    old = balances(customer)
    new = {_code(k): _d(v) for k, v in (new_balances or {}).items()}
    for code, val in new.items():
        if val < -EPS:
            raise HTTPException(status_code=400, detail=f"Qarz manfiy bo'lishi mumkin emas ({code})")
    rows = []
    merged = dict(old)
    for code in sorted(set(old) | set(new)):
        target = new.get(code, ZERO)
        if target < EPS:
            target = ZERO
        diff = target - old.get(code, ZERO)
        if abs(diff) < TINY:
            continue
        merged[code] = target
        rows.append(_log(
            db, customer, kind=kind, currency=code, delta=diff, rate=_rate(rates, code), user=user,
            branch_id=_resolve_branch(db, customer, user, branch_id, None), reason=reason,
        ))
    _save(db, customer, merged, rates)
    return rows


# ─── FIFO ────────────────────────────────────────────────────────────────────

def _apply_fifo(db: Session, customer, amount_uzs) -> list:
    """To'lovni mijozning eng eski to'lanmagan sotuvlariga taqsimlaydi. Qaytaradi: [(sale, uzs, paid_delta)].

    BIRLIKLAR: `Sale.total_amount` — UZS, `Sale.paid_amount` — SOTUV valyutasida (`exchange_rate` ga bo'lingan).
    Shuning uchun to'lanmagan qoldiq (UZS) = total_amount - paid_amount * rate, qo'llash esa
    paid_amount += uzs / rate."""
    from app.models.sale import Sale, SaleStatus
    from app.utils.report_utils import is_return_doc, sale_rate

    remaining = _d(amount_uzs)
    result = []
    if remaining <= EPS:
        return result
    sales = db.query(Sale).filter(
        Sale.customer_id == customer.id,
        Sale.company_id == customer.company_id,
        Sale.status.in_((SaleStatus.completed, SaleStatus.partial_refund)),
        not_(is_return_doc()),
        Sale.total_amount - Sale.paid_amount * sale_rate() > 0.01,
    ).order_by(Sale.created_at.asc(), Sale.id.asc()).with_for_update().all()
    for sale in sales:
        if remaining <= EPS:
            break
        rate = _d(sale.exchange_rate) or ONE
        if rate <= 0:
            rate = ONE
        paid = _d(sale.paid_amount)
        outstanding_uzs = _d(sale.total_amount) - paid * rate
        if outstanding_uzs <= Decimal("0.01"):
            continue
        take = min(outstanding_uzs, remaining)
        paid_delta = take / rate
        sale.paid_amount = paid + paid_delta
        result.append((sale, take, paid_delta))
        remaining -= take
    return result


def allocate_fifo(db: Session, customer, amount_uzs) -> list:
    """FIFO taqsimot: [(sale_id, uzs)]. `Sale.paid_amount` to'g'ri birlikda yangilanadi."""
    return [(s.id, take) for s, take, _ in _apply_fifo(db, customer, amount_uzs)]


# ─── Qarz to'lovi ────────────────────────────────────────────────────────────

def _apply_to_buckets(bal: dict, code: str, amount: Decimal, pay_rate: Decimal, rates: dict):
    """To'lovni `bal` (nusxa) chelaklariga qo'llaydi: avval to'lov valyutasi, so'ng boshqalari (kurs bo'yicha).
    Qaytaradi: ({valyuta: kamaygan summa}, qoplanmay qolgan UZS)."""
    alloc: dict = {}
    remaining = amount
    own = bal.get(code, ZERO)
    if own > 0:
        take = min(own, remaining)
        bal[code] = own - take
        alloc[code] = take
        remaining -= take
    remaining_uzs = remaining * pay_rate
    if remaining_uzs > Decimal("0.001"):
        for other, debt in list(bal.items()):
            if remaining_uzs <= Decimal("0.001"):
                break
            if other == code or debt <= 0:
                continue
            r = _rate(rates, other)
            cover_uzs = min(remaining_uzs, debt * r)
            cover = cover_uzs / r
            bal[other] = debt - cover
            alloc[other] = alloc.get(other, ZERO) + cover
            remaining_uzs -= cover_uzs
    return alloc, remaining_uzs


def _split_exact(total: Decimal, shares: list) -> list:
    """`total` ni `shares` [(kalit, og'irlik)] bo'yicha 4 xonagacha bo'ladi; oxirgisi qoldiqni oladi (yig'indi aniq)."""
    out = []
    weight = sum((w for _, w in shares), ZERO)
    left = round(total, 4)
    for i, (key, w) in enumerate(shares):
        if i == len(shares) - 1 or weight <= 0:
            part = left
        else:
            part = round(total * w / weight, 4)
            left -= part
        out.append((key, part))
        if weight <= 0:
            break
    return out


def _norm_payments(db: Session, user, payments) -> list:
    """To'lov ro'yxatini tekshiradi: summa > 0, to'lov turi haqiqiy, valyuta korxonada faol."""
    from app.services.currency_service import require_active_currency
    items = []
    for p in (payments or []):
        amount = _d(_get(p, "amount"))
        if amount <= 0:
            raise HTTPException(status_code=400, detail=ERR_NOT_POSITIVE)
        ptype = _get(p, "payment_type") or "cash"
        if ptype not in CASH_PAYMENT_TYPES:
            raise HTTPException(status_code=400, detail=f"To'lov turi noto'g'ri: {ptype}")
        code = require_active_currency(db, user.company_id, _get(p, "currency"))
        rate = _get(p, "rate")
        items.append({"amount": amount, "currency": code, "payment_type": ptype,
                      "rate": _d(rate) if rate else None})
    if not items:
        raise HTTPException(status_code=400, detail=ERR_NOT_POSITIVE)
    return items


def pay_debt(
    db: Session, customer, *, user, payments, wallet_id: Optional[int] = None,
    reason: Optional[str] = None, branch_id: Optional[int] = None,
) -> dict:
    """Mijoz qarzini to'lash — YAGONA implementatsiya (Mijozlar, Moliya, AI va agent ilovasi).

    Tartib: tekshiruvlar (summa, tur, valyuta, kassa, qarzdan ortiqcha emasligi) hech narsa o'zgarmasdan
    OLDIN; so'ng valyuta kaskadi, sotuvlarga FIFO, kassa yozuvi (`cash_service.post_cash`) va jurnal.
    `payments`: [{amount, currency, payment_type, rate}] (dict yoki obyekt). Commit chaqiruvchida.
    """
    from app.core.audit import log_action
    from app.core.branch_context import effective_branch_id
    from app.services import cash_service
    from app.services.customer_service import lock_customer
    from app.services.wallet_resolver import resolve_wallet

    if customer is None or customer.company_id != getattr(user, "company_id", None):
        raise HTTPException(status_code=404, detail=ERR_CUSTOMER)
    lock_customer(db, customer.id, customer.company_id)          # qulf tartibi: mijoz -> hamyon
    items = _norm_payments(db, user, payments)

    wallet = resolve_wallet(
        db, user, branch_id=branch_id or effective_branch_id(db, user), purpose="debt_payment",
        requested_wallet_id=wallet_id, for_update=True,
    )
    if wallet is None:
        raise HTTPException(status_code=400, detail=ERR_NO_WALLET)

    rates = _rates(db, customer.company_id)
    old_balances = {k: float(v) for k, v in balances(customer).items()}
    old_total = float(customer.debt_balance or 0)
    bal = balances(customer)

    # 1) Reja: qarzdan ortiq to'lov bo'lsa hech narsa o'zgarmasdan 400
    plan = []
    for it in items:
        pay_rate = it["rate"] if it["rate"] and it["rate"] > 0 else _rate(rates, it["currency"])
        alloc, left_uzs = _apply_to_buckets(bal, it["currency"], it["amount"], pay_rate, rates)
        if left_uzs > PAY_TOLERANCE_UZS:
            raise HTTPException(status_code=400, detail=ERR_TOO_MUCH)
        applied_uzs = sum(
            (a * (pay_rate if c == it["currency"] else _rate(rates, c)) for c, a in alloc.items()), ZERO,
        )
        plan.append((it, alloc, applied_uzs))

    # 2) Bajarish
    tx_ids, allocations = [], []
    base_desc = (reason or "").strip() or f"Mijoz to'lovi: {customer.name}"
    for it, alloc, applied_uzs in plan:
        fifo = _apply_fifo(db, customer, applied_uzs)
        fifo_total = sum((take for _, take, _ in fifo), ZERO)

        # Qarz egasi filiallar: FIFO sotuvlar filiali; sotuvga bog'lanmagan qoldiq — mijoz filiali
        shares: dict = defaultdict(lambda: ZERO)
        for sale, take, _ in fifo:
            shares[_sale_branch(db, sale)] += take
        if applied_uzs - fifo_total > EPS:
            shares[_resolve_branch(db, customer, user, None, None)] += applied_uzs - fifo_total
        share_list = list(shares.items()) or [(_resolve_branch(db, customer, user, None, None), ONE)]

        desc = base_desc if it["currency"] == "UZS" else f"{base_desc} ({it['amount']} {it['currency']})"
        alloc_meta = {
            "sales": {str(s.id): str(round(pd, 6)) for s, _, pd in fifo},
            "sales_uzs": {str(s.id): str(round(take, 2)) for s, take, _ in fifo},
            "buckets": {c: str(round(a, 6)) for c, a in alloc.items()},
        }
        tx = cash_service.post_cash(
            db, user=user, wallet=wallet, direction="in", amount=it["amount"], currency=it["currency"],
            payment_type=it["payment_type"], reference_type="customer_payment", reference_id=customer.id,
            description=desc, meta={"allocation": alloc_meta},
        )
        for code, amt in alloc.items():
            for br, part in _split_exact(amt, share_list):
                if abs(part) < TINY:
                    continue
                _log(
                    db, customer, kind="payment", currency=code, delta=-part, rate=_rate(rates, code),
                    user=user, branch_id=br, cash_branch_id=tx.branch_id, tx=tx, reason=reason,
                )
        tx_ids.append(tx.id)
        allocations.append({
            "transaction_id": tx.id, "currency": it["currency"], "amount": float(it["amount"]),
            "buckets": {c: float(round(a, 4)) for c, a in alloc.items()},
            "sales": [{"sale_id": s.id, "uzs": float(round(take, 2))} for s, take, _ in fifo],
        })

    _save(db, customer, bal, rates)
    log_action(
        db, "CUSTOMER_DEBT_PAY", "customer", customer.id, user_id=user.id, company_id=customer.company_id,
        old_values={"debt_balance": old_total, "debt_balances": old_balances},
        new_values={
            "payments": [{"amount": float(it["amount"]), "currency": it["currency"],
                          "payment_type": it["payment_type"]} for it, _, _ in plan],
            "wallet_id": wallet.id, "reason": reason, "transaction_ids": tx_ids,
            "debt_balance": float(customer.debt_balance or 0), "debt_balances": dict(customer.debt_balances or {}),
        },
    )
    return {
        "transaction_ids": tx_ids, "allocation": allocations, "wallet_id": wallet.id,
        "remaining_debt": float(customer.debt_balance or 0), "debt_balances": dict(customer.debt_balances or {}),
    }


def reverse_payment(db: Session, tx, user=None) -> bool:
    """`pay_debt` tranzaksiyasi o'chirilganda/bekor qilinganda qarzni AYNAN qaytaradi.

    Jurnal qatorlari (`transaction_id = tx.id`, `kind='payment'`) bo'yicha har bir valyuta va filialga
    qarz qaytadi (`kind='reversal'`), `meta.allocation.sales` bo'yicha `Sale.paid_amount` qaytadi.
    `meta` yo'q eski yozuvlarda summa `tx.currency_code` chelagiga qaytadi, `Sale.paid_amount` ga tegilmaydi.
    Takroriy chaqiruv xavfsiz (ikkinchi marta hech narsa qilmaydi). Qaytaradi: qarz qaytarilgan bo'lsa True."""
    from app.models.sale import Sale
    from app.services.customer_service import lock_customer

    if tx is None or tx.reference_type != "customer_payment" or not tx.reference_id:
        return False
    customer = lock_customer(db, tx.reference_id, tx.company_id, allow_inactive=True, required=False)
    if customer is None:
        return False
    if db.query(CustomerDebtLog.id).filter(
        CustomerDebtLog.transaction_id == tx.id, CustomerDebtLog.kind == "reversal",
    ).first():
        return False
    rates = _rates(db, customer.company_id)
    bal = balances(customer)
    rows = db.query(CustomerDebtLog).filter(
        CustomerDebtLog.transaction_id == tx.id, CustomerDebtLog.kind == "payment",
    ).all()
    alloc = (tx.meta or {}).get("allocation") if isinstance(tx.meta, dict) else None

    if rows:
        for r in rows:
            code = _code(r.currency)
            back = -_d(r.delta)
            bal[code] = bal.get(code, ZERO) + back
            _log(
                db, customer, kind="reversal", currency=code, delta=back, rate=_rate(rates, code), user=user,
                branch_id=r.branch_id, cash_branch_id=r.cash_branch_id, tx=tx,
                reason=f"To'lov bekor qilindi (tranzaksiya #{tx.id})",
            )
    elif alloc and alloc.get("buckets"):
        for code, amt in alloc["buckets"].items():
            code = _code(code)
            bal[code] = bal.get(code, ZERO) + _d(amt)
            _log(
                db, customer, kind="reversal", currency=code, delta=_d(amt), rate=_rate(rates, code), user=user,
                branch_id=_resolve_branch(db, customer, user, None, None), cash_branch_id=tx.branch_id, tx=tx,
                reason=f"To'lov bekor qilindi (tranzaksiya #{tx.id})",
            )
    else:   # eski yozuv (meta yo'q): to'lov valyutasi chelagiga qaytadi
        code = _code(tx.currency_code)
        bal[code] = bal.get(code, ZERO) + _d(tx.amount)
        _log(
            db, customer, kind="reversal", currency=code, delta=_d(tx.amount), rate=_rate(rates, code), user=user,
            branch_id=_resolve_branch(db, customer, user, None, None), cash_branch_id=tx.branch_id, tx=tx,
            reason=f"To'lov bekor qilindi (tranzaksiya #{tx.id})",
        )

    for sale_id, paid_delta in ((alloc or {}).get("sales") or {}).items():
        sale = db.query(Sale).filter(Sale.id == int(sale_id), Sale.company_id == customer.company_id).first()
        if sale is not None:
            sale.paid_amount = max(ZERO, _d(sale.paid_amount) - _d(paid_delta))
    _save(db, customer, bal, rates)
    return True


def write_off(db: Session, customer, *, user, amount, currency: str, reason: Optional[str]) -> list:
    """Qarzni hisobdan chiqarish (kassa harakatisiz). Sabab kamida 5 belgi; summa shu valyutadagi qarzdan oshmasin.
    Sotuvlarga FIFO qo'llanadi (ular "to'lanmagan" bo'lib qolmasin)."""
    from app.core.audit import log_action
    from app.services.customer_service import lock_customer

    if customer is None or customer.company_id != getattr(user, "company_id", None):
        raise HTTPException(status_code=404, detail=ERR_CUSTOMER)
    lock_customer(db, customer.id, customer.company_id)
    reason = (reason or "").strip()
    if len(reason) < WRITEOFF_REASON_MIN:
        raise HTTPException(status_code=400, detail=f"Sabab kamida {WRITEOFF_REASON_MIN} ta belgidan iborat bo'lishi kerak")
    amount = _d(amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Hisobdan chiqarish summasi musbat bo'lishi kerak")
    code = _code(currency)
    rates = _rates(db, customer.company_id)
    bal = balances(customer)
    if amount > bal.get(code, ZERO) + EPS:
        raise HTTPException(status_code=400, detail="Hisobdan chiqarish summasi qarzdan ko'p")
    old = {k: float(v) for k, v in bal.items()}

    fifo = _apply_fifo(db, customer, amount * _rate(rates, code))
    shares: dict = defaultdict(lambda: ZERO)
    for sale, take, _ in fifo:
        shares[_sale_branch(db, sale)] += take
    left = amount * _rate(rates, code) - sum((t for _, t, _ in fifo), ZERO)
    home = _resolve_branch(db, customer, user, None, None)
    if left > EPS:
        shares[home] += left
    if not shares:
        shares[home] = ONE
    rows = []
    for br, part in _split_exact(amount, list(shares.items())):
        if abs(part) < TINY:
            continue
        rows.append(_log(
            db, customer, kind="writeoff", currency=code, delta=-part, rate=_rate(rates, code),
            user=user, branch_id=br, reason=reason,
        ))
    bal[code] = bal.get(code, ZERO) - amount
    _save(db, customer, bal, rates)
    log_action(
        db, "CUSTOMER_DEBT_WRITEOFF", "customer", customer.id, user_id=user.id, company_id=customer.company_id,
        old_values={"debt_balances": old},
        new_values={"amount": str(amount), "currency": code, "reason": reason,
                    "debt_balances": dict(customer.debt_balances or {})},
    )
    return rows


# ─── Jurnal va invariant ─────────────────────────────────────────────────────

def reconcile(db: Session, company_id: int, *, dry_run: bool = True, user=None, customer_id: Optional[int] = None) -> list:
    """Invariant tekshiruvi: har mijoz va valyuta uchun `SUM(delta)` = `debt_balances[valyuta]`.
    Qaytaradi: farqlar ro'yxati. `dry_run=False` bo'lsa farq `kind='recalc'` qatori bilan tuzatiladi
    (balansga tegilmaydi — jurnal balansga moslashadi)."""
    from app.models.customer import Customer

    sums: dict = defaultdict(lambda: ZERO)
    q = db.query(CustomerDebtLog.customer_id, CustomerDebtLog.currency, func.sum(CustomerDebtLog.delta)).filter(
        CustomerDebtLog.company_id == company_id,
    )
    if customer_id:
        q = q.filter(CustomerDebtLog.customer_id == customer_id)
    for cid, cur, total in q.group_by(CustomerDebtLog.customer_id, CustomerDebtLog.currency).all():
        sums[(cid, _code(cur))] = _d(total)

    cq = db.query(Customer).filter(Customer.company_id == company_id)
    if customer_id:
        cq = cq.filter(Customer.id == customer_id)
    rates = _rates(db, company_id)
    logged_codes: dict = defaultdict(set)
    for (cid, cur) in sums:
        logged_codes[cid].add(cur)
    diffs = []
    for c in cq.all():
        bal = balances(c)
        for code in sorted(set(bal) | logged_codes.get(c.id, set())):
            have = bal.get(code, ZERO)
            if have < EPS:
                have = ZERO
            logged = sums.get((c.id, code), ZERO)
            diff = have - logged
            if abs(diff) <= EPS:
                continue
            diffs.append({
                "customer_id": c.id, "customer_name": c.name, "currency": code,
                "journal": float(round(logged, 4)), "balance": float(round(have, 4)),
                "diff": float(round(diff, 4)),
            })
            if not dry_run:
                _log(
                    db, c, kind="recalc", currency=code, delta=diff, rate=_rate(rates, code), user=user,
                    branch_id=_resolve_branch(db, c, user, None, None), reason="Jurnalni balansga moslashtirish",
                )
    return diffs


# ─── Hisobotlar: filial kesimida qarz ────────────────────────────────────────

def _net_negatives(parts: dict) -> dict:
    """Filial ulushlaridagi manfiylarni musbatlar hisobiga yopadi (jami o'zgarmaydi)."""
    neg = sum((-v for v in parts.values() if v < 0), ZERO)
    res = {b: v for b, v in parts.items() if v > 0}
    if neg <= 0:
        return res
    for b in sorted(res, key=lambda k: res[k], reverse=True):
        if neg <= 0:
            break
        take = min(res[b], neg)
        res[b] -= take
        neg -= take
    return {b: v for b, v in res.items() if v > 0}


def _agg(rows: list, rates: dict, branch_id, name) -> dict:
    total: dict = {}
    uzs = ZERO
    custs = set()
    for r in rows:
        custs.add(r["customer"].id)
        for code, amt in r["debts"].items():
            total[code] = total.get(code, ZERO) + _d(amt)
            uzs += _d(amt) * _rate(rates, code)
    return {
        "branch_id": branch_id, "branch_name": name,
        "total_debt": {c: float(round(v, 2)) for c, v in total.items()},
        "debt_uzs": float(round(uzs, 2)), "debtor_count": len(custs),
    }


def debt_by_branch(db: Session, company_id: int, branch_id: Optional[int] = None, branch_ids=None) -> dict:
    """Mijoz qarzi filial kesimida (jurnal asosida).

    Mijozning haqiqiy qarzi (`debt_balances`) filiallarga jurnal yig'indisi (`SUM(delta)` filial bo'yicha) bilan
    bo'linadi; jurnalda aks etmagan qoldiq (eski/ko'chirilmagan yozuv) mijoz filialiga (yo'q bo'lsa
    `unassigned`) yoziladi — shuning uchun filiallar yig'indisi + `unassigned` har doim butun qarzga teng.
    Filial ulushidagi manfiylar boshqa filial musbatlari hisobiga yopiladi.

    `branch_id`: aniq filial; `-1` — filialsiz; `branch_ids` — ruxsat etilgan filiallar to'plami.
    Qaytaradi: {"by_branch": [...], "unassigned": {...}, "customers": [{customer, branch_id, debts, debt_uzs}]}.
    """
    from app.models.branch import Branch
    from app.models.customer import Customer
    from app.utils.report_utils import load_debtors

    rates = _rates(db, company_id)
    debtors = load_debtors(db, Customer, company_id)
    journal: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: ZERO)))
    for cid, br, cur, total in db.query(
        CustomerDebtLog.customer_id, CustomerDebtLog.branch_id, CustomerDebtLog.currency, func.sum(CustomerDebtLog.delta),
    ).filter(CustomerDebtLog.company_id == company_id).group_by(
        CustomerDebtLog.customer_id, CustomerDebtLog.branch_id, CustomerDebtLog.currency,
    ).all():
        journal[cid][_code(cur)][br] += _d(total)

    rows_by_key: dict = {}
    for cust, pos in debtors:
        for code, amt in pos.items():
            total = _d(amt)
            parts = {b: v for b, v in journal.get(cust.id, {}).get(code, {}).items() if abs(v) > TINY}
            residual = total - sum(parts.values(), ZERO)
            if abs(residual) > TINY:
                parts[cust.branch_id] = parts.get(cust.branch_id, ZERO) + residual
            for b, v in _net_negatives(parts).items():
                if v > TINY:
                    rec = rows_by_key.setdefault((cust.id, b), {"customer": cust, "branch_id": b, "debts": {}})
                    rec["debts"][code] = v

    def _keep(b) -> bool:
        if branch_id == -1:
            return b is None
        if branch_id:
            return b == branch_id
        if branch_ids is not None:
            return b in branch_ids
        return True

    rows = []
    for rec in rows_by_key.values():
        if not _keep(rec["branch_id"]):
            continue
        rec["debt_uzs"] = float(round(sum((v * _rate(rates, c) for c, v in rec["debts"].items()), ZERO), 2))
        rec["debts"] = {c: float(round(v, 2)) for c, v in rec["debts"].items()}
        rows.append(rec)
    rows.sort(key=lambda r: r["debt_uzs"], reverse=True)

    names = {b.id: b.name for b in db.query(Branch.id, Branch.name).filter(Branch.company_id == company_id).all()}
    grouped: dict = defaultdict(list)
    for r in rows:
        grouped[r["branch_id"]].append(r)
    by_branch = [
        _agg(rs, rates, b, names.get(b) or f"Filial #{b}") for b, rs in grouped.items() if b is not None
    ]
    by_branch.sort(key=lambda x: x["debt_uzs"], reverse=True)
    unassigned = _agg(grouped.get(None, []), rates, None, None)
    return {"by_branch": by_branch, "unassigned": unassigned, "customers": rows, "branch_names": names}


def check_branch_scope(db: Session, user, ctx, branch_id: Optional[int]):
    """Hisobot filial parametri: `(branch_id, allowed_ids)`.

    Begona korxona filiali — 404; cheklangan foydalanuvchi uchun ruxsatsiz filial — 403. Parametr berilmasa
    cheklangan foydalanuvchi faqat o'z filiallarini ko'radi (`allowed_ids`), cheklanmagan — butun korxonani.
    `-1` — filialsiz guruh."""
    from app.core.branch_context import BRANCH_FORBIDDEN
    from app.models.branch import Branch

    if branch_id:
        if branch_id != -1:
            ok = db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == user.company_id).first()
            if not ok:
                raise HTTPException(status_code=404, detail=ERR_BRANCH)
            allowed = getattr(ctx, "allowed_branch_ids", None)
            if allowed is not None and branch_id not in allowed:
                raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
        return branch_id, None
    ids = ctx.scope_ids() if ctx is not None else None
    return None, (set(ids) if ids is not None else None)
