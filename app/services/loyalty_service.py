"""
Loyalty & Cashback Service
Mijoz sodiqlik ballari va keshbek logikasini boshqaradi.

T2.12: qoidalar (ball stavkasi, ball qiymati, daraja chegaralari, filialni dasturdan chiqarish, filial
keshbek stavkasi) `loyalty_settings` / `loyalty_branch_rules` jadvallaridan o'qiladi; qator bo'lmasa
bugungi qattiq qiymatlar ishlaydi. Teskari hisob (qaytarish/tahrir/o'chirish) joriy foizga emas,
sotuvda saqlangan qiymatlarga (`cashback_earned`, `loyalty_points_earned`, `loyalty_base`) tayanadi.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.sale import Sale

DEFAULT_TIERS = (1000, 5000, 10000)  # bronze, silver, gold
_D0 = Decimal("0")
_D1 = Decimal("1")
_CENT = Decimal("0.01")


@dataclass
class LoyaltyRules:
    """Bitta korxona (va filial) uchun amaldagi sodiqlik qoidalari."""
    enabled: bool = True                      # korxona va filial bo'yicha umumiy holat
    company_enabled: bool = True
    branch_enabled: bool = True
    points_percent: Decimal = Decimal("1")    # sotuv summasining % i ball sifatida
    point_value: Decimal = Decimal("1")       # 1 ball = necha so'm
    default_cashback_percent: Decimal = Decimal("0")
    max_redeem_percent: Decimal = Decimal("100")
    accrue_on_unpaid: bool = True
    return_reverses_loyalty: bool = True
    tier_bronze: int = DEFAULT_TIERS[0]
    tier_silver: int = DEFAULT_TIERS[1]
    tier_gold: int = DEFAULT_TIERS[2]
    branch_cashback_override: Optional[Decimal] = None

    @property
    def tiers(self):
        return (self.tier_bronze, self.tier_silver, self.tier_gold)


def get_loyalty_rules(db: Session, company_id: Optional[int], warehouse_id: Optional[int] = None,
                      branch_id: Optional[int] = None) -> LoyaltyRules:
    """Korxona sozlamalari (qator bo'lmasa sukut) + filial qoidasi bilan qoplangan holda.

    Filial `branch_id` bilan beriladi, berilmasa `Warehouse.branch_id` orqali aniqlanadi."""
    from app.models.loyalty import LoyaltySettings, LoyaltyBranchRule
    from app.models.warehouse import Warehouse

    rules = LoyaltyRules()
    if not company_id:
        return rules
    st = db.query(LoyaltySettings).filter(LoyaltySettings.company_id == company_id).first()
    if st is not None:
        rules.company_enabled = bool(st.is_enabled)
        rules.points_percent = Decimal(str(st.points_percent))
        rules.point_value = Decimal(str(st.point_value)) or _D1
        rules.default_cashback_percent = Decimal(str(st.default_cashback_percent or 0))
        rules.max_redeem_percent = Decimal(str(st.max_redeem_percent))
        rules.accrue_on_unpaid = bool(st.accrue_on_unpaid)
        rules.return_reverses_loyalty = bool(st.return_reverses_loyalty)
        rules.tier_bronze = int(st.tier_bronze)
        rules.tier_silver = int(st.tier_silver)
        rules.tier_gold = int(st.tier_gold)
    if branch_id is None and warehouse_id:
        branch_id = db.query(Warehouse.branch_id).filter(
            Warehouse.id == warehouse_id, Warehouse.company_id == company_id,
        ).scalar()
    if branch_id:
        br = db.query(LoyaltyBranchRule).filter(
            LoyaltyBranchRule.company_id == company_id, LoyaltyBranchRule.branch_id == branch_id,
        ).first()
        if br is not None:
            rules.branch_enabled = bool(br.is_enabled)
            if br.cashback_percent_override is not None:
                rules.branch_cashback_override = Decimal(str(br.cashback_percent_override))
    rules.enabled = rules.company_enabled and rules.branch_enabled
    return rules


def tier_for(points, rules=None) -> str:
    """Ball bo'yicha daraja. `rules` — LoyaltyRules yoki (bronze, silver, gold) juftligi; None — sukut."""
    if rules is None:
        bronze, silver, gold = DEFAULT_TIERS
    elif isinstance(rules, LoyaltyRules):
        bronze, silver, gold = rules.tiers
    else:
        bronze, silver, gold = rules
    pts = points or 0
    if pts >= gold:
        return "Gold"
    if pts >= silver:
        return "Silver"
    if pts >= bronze:
        return "Bronze"
    return "Standard"


def redeem_value_uzs(points, rules: LoyaltyRules) -> Decimal:
    """Ballarning so'mdagi qiymati."""
    return Decimal(str(points or 0)) * rules.point_value


def effective_cashback_percent(customer: Customer, rules: LoyaltyRules) -> Decimal:
    """Filial stavkasi berilgan bo'lsa shu, aks holda mijozning shaxsiy foizi."""
    if rules.branch_cashback_override is not None:
        return rules.branch_cashback_override
    return Decimal(str(getattr(customer, "cashback_percent", 0) or 0))


def apply_sale_loyalty(customer: Customer, sale: Sale, base_uzs, rules: LoyaltyRules, paid_uzs=None) -> None:
    """Sotuv uchun keshbek/ball/total_spent ni mijozga qo'shadi va sotuvga snapshot yozadi
    (`cashback_earned`, `loyalty_points_earned`, `loyalty_base`).

    `base_uzs` — sotuvning (keshbek/ball ayirilgandan keyingi) jami summasi, UZS. `accrue_on_unpaid=False`
    bo'lsa keshbek/ball faqat `min(base, paid_uzs)` ga hisoblanadi. Dastur o'chirilgan bo'lsa (korxona yoki
    filial) keshbek/ball 0, lekin total_spent baribir yoziladi (teskari hisob simmetrik bo'lsin).
    """
    base = Decimal(str(base_uzs or 0))
    accrual = base
    if not rules.accrue_on_unpaid and paid_uzs is not None:
        accrual = max(_D0, min(base, Decimal(str(paid_uzs))))
    cashback = _D0
    points = 0
    if rules.enabled:
        pct = effective_cashback_percent(customer, rules)
        if pct > 0:
            cashback = accrual * pct / Decimal("100")
        points = int(accrual * rules.points_percent / Decimal("100"))
    if cashback > 0:
        customer.bonus_balance = (customer.bonus_balance or _D0) + cashback
    if points > 0:
        customer.loyalty_points = (customer.loyalty_points or 0) + points
    customer.total_spent = (customer.total_spent or _D0) + base
    sale.cashback_earned = cashback
    sale.loyalty_points_earned = points
    sale.loyalty_base = base


def clear_sale_loyalty(sale: Sale) -> None:
    """Teskari qilingan sotuvdagi yig'ish snapshot'ini tozalaydi (qayta yig'ilmaguncha)."""
    sale.cashback_earned = _D0
    sale.loyalty_points_earned = 0
    sale.loyalty_base = None


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


def reverse_sale_loyalty(customer: Customer, sale: Sale, ratio=_D1, ratio_before=_D0,
                         include_redeemed: bool = True) -> None:
    """Sotuvning sodiqlik ta'sirini `ratio` ulushida teskari qiladi (to'liq = 1).

    `+paid_cashback`, `+loyalty_points_used` (sarflangani qaytadi; `include_redeemed=False` bo'lsa yo'q),
    `-cashback_earned`, `-loyalty_points_earned`, `total_spent -= loyalty_base` (eski sotuvlarda
    `COALESCE(loyalty_base, total_amount)`). Hammasi sotuvda saqlangan qiymatlardan; natija 0 dan pastga tushmaydi.
    Qisman qaytarishda `ratio` — shu qaytarishning ulushi (Δ), `ratio_before` — avval qaytarilgan ulush:
    yaxlitlash kumulyativ hisoblanadi, shuning uchun qisman qaytarishlar yig'indisi to'liq qaytarishga teng.
    """
    ratio = max(_D0, min(_D1, Decimal(str(ratio))))
    rb = max(_D0, min(_D1, Decimal(str(ratio_before))))
    if ratio <= 0:
        return
    ra = min(_D1, rb + ratio)

    def part_money(x) -> Decimal:
        x = Decimal(str(x or 0))
        return _q(x * ra) - _q(x * rb)

    def part_int(x) -> int:
        x = Decimal(str(x or 0))
        return int((x * ra).to_integral_value(ROUND_HALF_UP)) - int((x * rb).to_integral_value(ROUND_HALF_UP))

    if include_redeemed:
        used_cb = part_money(getattr(sale, "paid_cashback", 0))
        if used_cb > 0:
            customer.bonus_balance = (customer.bonus_balance or _D0) + used_cb
        used_pts = part_int(getattr(sale, "loyalty_points_used", 0))
        if used_pts > 0:
            customer.loyalty_points = (customer.loyalty_points or 0) + used_pts

    earned_cb = part_money(getattr(sale, "cashback_earned", 0))
    if earned_cb > 0:
        customer.bonus_balance = max(_D0, (customer.bonus_balance or _D0) - earned_cb)
    earned_pts = part_int(getattr(sale, "loyalty_points_earned", 0))
    if earned_pts > 0:
        customer.loyalty_points = max(0, (customer.loyalty_points or 0) - earned_pts)

    base = getattr(sale, "loyalty_base", None)
    if base is None:
        base = getattr(sale, "total_amount", 0)
    spent = part_money(base)
    if spent > 0:
        customer.total_spent = max(_D0, (customer.total_spent or _D0) - spent)


def reverse_return_without_sale(customer: Customer, amount_uzs, rules: LoyaltyRules) -> dict:
    """Asl sotuvga bog'lanmagan POS "Vazvrat": qaytarilgan summa bo'yicha mijozdan taxminiy ayiriladi
    (`bonus -= summa * cashback%`, `ball -= int(summa * points%)`, `total_spent -= summa`; 0 dan pastga tushmaydi).
    Natijani (log uchun) qaytaradi."""
    amount = Decimal(str(amount_uzs or 0))
    if amount <= 0 or not rules.return_reverses_loyalty:
        return {}
    cb = _D0
    pct = effective_cashback_percent(customer, rules) if rules.enabled else _D0
    if pct > 0:
        cb = min(customer.bonus_balance or _D0, _q(amount * pct / Decimal("100")))
        customer.bonus_balance = (customer.bonus_balance or _D0) - cb
    pts = 0
    if rules.enabled:
        pts = min(int(customer.loyalty_points or 0), int(amount * rules.points_percent / Decimal("100")))
        customer.loyalty_points = (customer.loyalty_points or 0) - pts
    spent = min(customer.total_spent or _D0, amount)
    customer.total_spent = (customer.total_spent or _D0) - spent
    return {"bonus": float(cb), "points": pts, "total_spent": float(spent)}


def returned_ratio(items) -> Decimal:
    """Σ(returned_quantity * unit_price) / Σ(quantity * unit_price) — `SaleItem` ro'yxati bo'yicha."""
    total = _D0
    ret = _D0
    for si in items:
        price = Decimal(str(si.unit_price or 0))
        total += Decimal(str(si.quantity or 0)) * price
        ret += Decimal(str(getattr(si, "returned_quantity", 0) or 0)) * price
    if total <= 0:
        return _D0
    return min(_D1, ret / total)


def restore_customer_debt(customer: Customer, sale: Sale) -> None:
    """Sotuvni bekor qilish yoki o'chirishda mijozning qarzini tiklaydi (aggregate va valyuta kesimi)."""
    exr = Decimal(str(getattr(sale, 'exchange_rate', 1) or 1))
    total = Decimal(str(sale.total_amount or 0))
    paid = Decimal(str(sale.paid_amount or 0))

    # 1. Qarzni tiklash (Aggregate and JSON)
    debt_in_sale_raw = total - paid
    if debt_in_sale_raw > 0:
        # Multi-currency debt_balances sync
        if not customer.debt_balances: customer.debt_balances = {}

        from app.models.currency import Currency as CurrencyModel
        sale_currency = "UZS"
        if getattr(sale, "currency_id", None):
            # We need DB session here, but we don't have it in args.
            # In SQLAlchemy, an object usually has an associated session via object_session(object)
            from sqlalchemy.orm import object_session
            sess = object_session(customer)
            if sess:
                curr_obj = sess.get(CurrencyModel, sale.currency_id)
                if curr_obj:
                    sale_currency = curr_obj.code

        # Subtract the raw debt from the specific currency bucket
        current_bucket_val = Decimal(str(customer.debt_balances.get(sale_currency, 0)))
        customer.debt_balances[sale_currency] = float(max(Decimal("0"), current_bucket_val - debt_in_sale_raw))
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(customer, "debt_balances")

        # Update aggregate UZS balance
        debt_in_uzs = debt_in_sale_raw * exr
        customer.debt_balance = max(
            Decimal("0"),
            (customer.debt_balance or Decimal("0")) - debt_in_uzs
        )


def restore_customer_after_sale(customer: Customer, sale: Sale) -> None:
    """
    Sotuvni bekor qilish yoki o'chirishda mijozning barcha ko'rsatkichlarini tiklaydi:
    qarz (`restore_customer_debt`), ishlatilgan keshbek/ball, qo'shilgan keshbek/ball va total_spent
    (`reverse_sale_loyalty` — sotuvda saqlangan qiymatlar bo'yicha).
    """
    restore_customer_debt(customer, sale)
    reverse_sale_loyalty(customer, sale)
