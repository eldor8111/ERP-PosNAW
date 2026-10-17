from collections import defaultdict
from decimal import Decimal
from typing import Optional
import threading

from fastapi import HTTPException

from sqlalchemy.orm import Session, joinedload

from app.core.audit import log_action
from app.models.batch import Batch
from app.models.customer import Customer
from app.models.customer_prices import CustomerPrice
from app.models.currency import Currency
from app.models.company import Company
from app.models.moliya import Transaction, KassaMovement, NON_CASH_PAYMENT_TYPES
from app.models.product import Product, ProductConversion, ProductStatus
from app.models.sale import Sale, SaleItem, SaleStatus, PaymentType, SaleItemBatch, SalePayment
from app.admin_tg_bot.notifications import trigger_instant_notification
from app.models.user import User
from app.schemas.sale import SaleCreate
from app.services.customer_service import lock_customer, ARCHIVED_DETAIL
from app.services.credit_service import check_credit_limit
from app.services.loyalty_service import get_loyalty_rules, apply_sale_loyalty
from app.services.sale_cash import build_sale_payment_entries, post_sale_payments
from app.services.sale_helpers import (
    generate_sale_number, send_tg_sync, resolve_item_pricing, resolve_branch_id, resolve_txn_branch, assert_sale_items_one_branch,
    price_is_override,
)
from app.services import approval_service  # T4.6: chegirma / qo'lda narx limitlari va tasdiqlash
from app.services.batch_allocator import (
    allocate_batches, allocation_cost, is_perishable_product, lock_batches, lock_stock_rows, tashkent_today,
)
from app.services.warehouse_resolver import resolve_warehouse
from app.services.promotion_service import load_sale_pricing_context
from app.services.wallet_resolver import resolve_wallet
from app.services.tenant_guards import NO_BRANCH_COMPANY


def _resolve_marking_codes(product: Product, item_data) -> list:
    """
    Markirovka (Data Matrix) kodlarini tekshiradi.
    Mahsulot requires_marking=True bo'lsa, skanerlangan kodlar soni miqdorga
    teng bo'lishi shart — aks holda fiskal chekda markirovka aks etmaydi.
    """
    codes = [c for c in (getattr(item_data, "marking_codes", None) or []) if c and c.strip()]
    if product.requires_marking:
        expected = int(item_data.quantity)
        if len(codes) != expected:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{product.name}' — markirovka talab qilinadi. "
                    f"{expected} ta kod skanerlanishi kerak, {len(codes)} ta kiritildi."
                ),
            )
    return codes


OFFLINE_SALE_TIME_DETAIL = "Sotuv vaqti ruxsat etilgan oraliqdan tashqarida"


def _to_naive_utc(dt):
    """tz-aware vaqtni UTC ga keltirib naive qiladi (Shift.opened_at naive-UTC saqlanadi —
    aralash solishtirish soat siljishini beradi). Naive qiymat UTC deb qabul qilinadi."""
    if dt is not None and getattr(dt, 'tzinfo', None) is not None:
        from datetime import timezone as _tz
        return dt.astimezone(_tz.utc).replace(tzinfo=None)
    return dt


def _validate_offline_created_at(created_at) -> None:
    """T3.11: oflayn sotuv vaqti [now - POS_OFFLINE_MAX_AGE_HOURS, now + POS_FUTURE_TOLERANCE_MINUTES]
    oralig'ida bo'lishi shart — orqaga/oldinga sana bilan hisobotni buzib bo'lmasin."""
    if created_at is None:
        return
    from datetime import datetime as _dt, timedelta as _td
    from app.config import settings
    now = _dt.utcnow()
    cat = _to_naive_utc(created_at)
    if cat < now - _td(hours=settings.POS_OFFLINE_MAX_AGE_HOURS)             or cat > now + _td(minutes=settings.POS_FUTURE_TOLERANCE_MINUTES):
        raise HTTPException(status_code=400, detail=OFFLINE_SALE_TIME_DETAIL)


def _sale_branch_of(db: Session, user: User) -> Optional[int]:
    """Sotuv filiali: joriy filial konteksti (T1.2), bo'lmasa foydalanuvchining asosiy filiali."""
    from app.core.branch_context import effective_branch_id
    return effective_branch_id(db, user)


def _sale_branch_snapshot(db: Session, user: User, warehouse_id, item_wh_ids) -> int:
    """Sotuv filiali (T1.9): ombor filiali → kassir filiali → korxonaning birinchi faol filiali.

    `items[].warehouse_id` sarlavha omboriga bir filialdan bo'lmasa — 400 (hisobotlarda aralashmasin).
    """
    # T1.12: yopilgan filial omboridan sotuv yo'q (sarlavha va qator omborlari)
    from app.services.sale_helpers import assert_warehouses_branch_active
    assert_warehouses_branch_active(db, [warehouse_id, *(item_wh_ids or ())])
    assert_sale_items_one_branch(db, user, warehouse_id, item_wh_ids)
    branch_id = resolve_txn_branch(db, user, warehouse_id=warehouse_id)
    if branch_id is None:
        raise HTTPException(status_code=400, detail=NO_BRANCH_COMPANY)
    return branch_id


SHIFT_REQUIRED = "Smena ochilmagan. Avval smena oching."


def _assert_shift_if_required(db: Session, user: User) -> None:
    """T1.11: `companies.pos_require_shift` yoqilgan bo'lsa ochiq smenasiz sotuv 400.
    Faqat yangi sotuv (create_sale / pending) uchun; qaytarish hujjatlariga majburlanmaydi."""
    if not user.company_id:
        return
    required = db.query(Company.pos_require_shift).filter(Company.id == user.company_id).scalar()
    if not required:
        return
    from app.models.shift import Shift as _ShiftReq
    has_open = db.query(_ShiftReq.id).filter(
        _ShiftReq.cashier_id == user.id, _ShiftReq.status == "open",
        _ShiftReq.company_id == user.company_id,  # T1.1: korxona filtri
    ).first()
    if not has_open:
        raise HTTPException(status_code=400, detail=SHIFT_REQUIRED)


def _assert_branch_open(db: Session, user: User) -> None:
    """T1.12: xodim filiali yopilgan bo'lsa sotuv 409 (yangi sotuv va kutilayotgan sotuv uchun)."""
    from app.services.sale_helpers import assert_user_branch_active
    assert_user_branch_active(db, user)


def create_sale(
    db: Session,
    data: SaleCreate,
    current_user: User,
    ip: Optional[str] = None,
    background_tasks=None,
    idempotency_key: Optional[str] = None,
) -> Sale:
    _assert_branch_open(db, current_user)
    _assert_shift_if_required(db, current_user)
    # T3.11: oflayn sotuv vaqti chegarasi (mutatsiyadan oldin)
    _validate_offline_created_at(getattr(data, 'created_at', None))
    # ── Warehouse aniqlash ────────────────────────────────────────────────────
    if data.warehouse_id is None:
        # T1.5: yagona qoida — filial default savdo ombori (main/shop); filialda ombor yo'q — 409,
        # filial ham, ombor ham aniq emas (2+ filial) — 400. Boshqa filialga jim fallback yo'q.
        data.warehouse_id = resolve_warehouse(
            db, current_user.company_id, branch_id=_sale_branch_of(db, current_user), purpose="sale", user=current_user,
        )
    else:
        # T0.13: mijoz yuborgan ombor — korxona/faollik/filial bo'yicha (mutatsiyadan oldin)
        from app.services.sale_helpers import validate_sale_warehouse
        validate_sale_warehouse(db, current_user, data.warehouse_id)
    # T0.13: qator omborlari ham (begona/nofaol ombor uchun StockLevel yaratilmasin)
    _item_wh_ids = {i.warehouse_id for i in data.items if getattr(i, "warehouse_id", None)}
    if _item_wh_ids:
        from app.services.sale_helpers import validate_sale_warehouses
        validate_sale_warehouses(db, current_user, _item_wh_ids)
    # T1.9: sotuv filiali snapshot'i (Sale.branch_id) — Sale yaratilishidan oldin aniqlanadi
    sale_branch_id = _sale_branch_snapshot(db, current_user, data.warehouse_id, _item_wh_ids)

    # ── Mahsulotlar narxi hisoblash ───────────────────────────────────────────
    product_ids = [item.product_id for item in data.items]

    products_map = {
        p.id: p for p in db.query(Product).filter(
            Product.id.in_(product_ids),
            Product.company_id == current_user.company_id,
            Product.is_deleted == False,
            Product.status == ProductStatus.active,
        ).all()
    }

    # T4.3: filial narxlari va amaldagi aksiyalar (ombor filiali bo'yicha)
    _pricing_ctx = load_sale_pricing_context(db, current_user, data.warehouse_id, data.items)

    customer = None
    customer_prices_map = {}
    if data.customer_id:
        # T0.26: mijoz qatori qulflanadi (qarz/bonus/ball Python'da hisoblanib yoziladi —
        # parallel sotuv/to'lov bir-birini ustidan yozmasligi uchun). Qulf tartibi:
        # mijoz -> ombor qoldig'i -> hamyon. Arxivlangan mijozga sotuv: 400.
        customer = lock_customer(db, data.customer_id, current_user.company_id)
        customer_prices_map = {
            cp.product_id: cp for cp in db.query(CustomerPrice).filter(
                CustomerPrice.customer_id == data.customer_id,
                CustomerPrice.product_id.in_(product_ids),
            ).all()
        }

    conversions_map = {
        c.sell_product_id: c for c in db.query(ProductConversion).filter(
            ProductConversion.sell_product_id.in_(product_ids),
        ).all()
    }
    source_product_ids = list({c.source_product_id for c in conversions_map.values()})
    source_products_map = {}
    if source_product_ids:
        source_products_map = {
            p.id: p for p in db.query(Product).filter(
                Product.id.in_(source_product_ids),
                Product.is_deleted == False,
            ).all()
        }

    currency = None
    exchange_rate = Decimal("1.0")
    if data.currency_id:
        currency = db.query(Currency).filter(Currency.id == data.currency_id).first()
        if currency:
            exchange_rate = Decimal(str(currency.rate))

    sale_items_data = []
    total_amount = Decimal("0")
    _approval_violations = []           # T4.6: qoida buzilishlari (qoida yo'q korxonada bo'sh qoladi)
    _gross_total = Decimal("0")         # T4.6: umumiy chegirma foizi uchun (UZS, chegirmasiz)

    for item_data in data.items:
        product = products_map.get(item_data.product_id)
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Mahsulot ID={item_data.product_id} topilmadi yoki nofaol",
            )

        _customer_price = customer_prices_map.get(item_data.product_id) if data.customer_id else None
        _branch_price = _pricing_ctx.branch_price(item_data.product_id, getattr(item_data, "variant_id", None))
        # T3.19: narx (individual narx > price_type > sale_price) va mijoz chegirmasi serverda hal qilinadi
        unit_price, discount, _price_src = resolve_item_pricing(
            item_data, product, _customer_price, customer, current_user, branch_price=_branch_price)
        # T4.3: aksiya serverda tekshiriladi (noto'g'ri promotion_id -> 400); qo'shimcha chegirma qo'shilmaydi
        discount, _promo_id, _promo_disc = _pricing_ctx.apply(item_data, unit_price, discount)
        if discount > unit_price * item_data.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"'{product.name}' uchun chegirma ({discount}) narxdan oshib ketdi",
            )
        subtotal = (unit_price * item_data.quantity) - discount

        # T4.6: kassir kiritgan chegirma (aksiya va mijozning doimiy chegirmasi hisobga olinmaydi) va qo'lda
        # tushirilgan narx limiti. Admin/director ozod (limitdan oshsa faqat audit).
        _rate = getattr(item_data, "exchange_rate", None) or Decimal("1")
        _gross_total += unit_price * item_data.quantity * Decimal(str(_rate))
        _manual_disc = max(Decimal(str(getattr(item_data, "discount", 0) or 0)) - Decimal(str(_promo_disc or 0)), Decimal("0"))
        _list_p = price_is_override(item_data, product, _customer_price, customer, _branch_price)
        _approval_violations.extend(approval_service.evaluate_discount(
            db, current_user, product, unit_price, _manual_disc, item_data.quantity,
            branch_id=sale_branch_id, list_price=_list_p, is_override=_list_p is not None, rate=_rate,
        ))

        # O'zining asl valyutasida saqlanadi
        item_currency_code = getattr(item_data, "currency_code", "UZS")
        item_exchange_rate = getattr(item_data, "exchange_rate", Decimal("1.0"))

        conversion = conversions_map.get(product.id)
        source_product = None
        if conversion:
            source_product = source_products_map.get(conversion.source_product_id)
            if not source_product:
                conversion = None

        marking_codes = _resolve_marking_codes(product, item_data)

        sale_items_data.append({
            "product": product,
            "variant_id": getattr(item_data, "variant_id", None),
            "quantity": item_data.quantity,
            "unit_price": unit_price,
            "cost_price": product.cost_price,
            "discount": discount,
            "subtotal": subtotal,
            "currency_code": item_currency_code,
            "exchange_rate": item_exchange_rate,
            "conversion": conversion,
            "source_product": source_product,
            "item_warehouse_id": item_data.warehouse_id,
            "marking_codes": marking_codes,
            "promotion_id": _promo_id,
            "promotion_discount": _promo_disc,
        })
        
        # Jami sotuv summasi doim UZS (asosiy valyuta) da yig'iladi
        total_amount += (subtotal * item_exchange_rate)

    # T4.6: umumiy (chek) chegirmasi ham chegirma limitiga kiradi; so'ng qaror: block -> 403 limit_exceeded,
    # require_approval -> approval_id yo'q bo'lsa 403 approval_required, bor bo'lsa tasdiq bir marta ishlatiladi
    if Decimal(str(data.discount_amount or 0)) > 0:
        _approval_violations.extend(approval_service.evaluate_discount(
            db, current_user, None, _gross_total, data.discount_amount, 1, branch_id=sale_branch_id,
        ))
    _consumed_approval = approval_service.enforce(
        db, current_user, _approval_violations, payload=approval_service.sale_payload(data), amount=total_amount,
        branch_id=sale_branch_id, approval_id=getattr(data, "approval_id", None),
    )

    total_amount -= data.discount_amount
    if total_amount < Decimal("0"):
        total_amount = Decimal("0")

    if data.payment_type.value == "debt" and not data.customer_id:
        raise HTTPException(status_code=400, detail="Qarzga sotish uchun mijozni tanlash majburiy")

    # ── Payments normalizatsiya ───────────────────────────────────────────────
    if not data.payments:
        _auto_payments = []
        _field_type_map = [
            ("paid_cash", "cash"), ("paid_card", "card"), ("paid_uzcard", "uzcard"),
            ("paid_humo", "humo"), ("paid_click", "click"), ("paid_payme", "payme"),
            ("paid_uzum", "uzum"), ("paid_cashback", "cashback"),
        ]
        sale_curr = currency.code if currency else "UZS"
        for _field, _ptype in _field_type_map:
            _val = getattr(data, _field, Decimal("0")) or Decimal("0")
            if _val > 0:
                from app.schemas.sale import PaymentItem as _PI
                _auto_payments.append(_PI(type=PaymentType(_ptype), amount=_val, currency=sale_curr))
        if _auto_payments:
            data.payments = _auto_payments

    paid_cashback_amount = getattr(data, "paid_cashback", Decimal("0")) or Decimal("0")
    if not paid_cashback_amount and data.payments:
        for _p in data.payments:
            if _p.type == PaymentType.cashback:
                paid_cashback_amount += _p.amount
    if paid_cashback_amount > 0 and not data.customer_id:
        raise HTTPException(status_code=400, detail="Keshbekdan foydalanish uchun mijozni tanlash majburiy")
    if data.loyalty_points_used > 0 and not data.customer_id:
        raise HTTPException(status_code=400, detail="Ball ishlatish uchun mijozni tanlash majburiy")

    # T2.12: sodiqlik qoidalari (korxona + filial): 1 ball qiymati, sarflash chegarasi, filial yoqilganligi
    rules = get_loyalty_rules(db, current_user.company_id, branch_id=sale_branch_id)
    redeem_points_uzs = Decimal(str(data.loyalty_points_used or 0)) * rules.point_value
    if paid_cashback_amount > 0 or data.loyalty_points_used > 0:
        if not rules.enabled:
            raise HTTPException(status_code=400, detail="Bu filialda sodiqlik dasturi o'chirilgan")
        _max_pct = rules.max_redeem_percent
        if _max_pct < Decimal("100") and (paid_cashback_amount + redeem_points_uzs) > total_amount * _max_pct / Decimal("100") + Decimal("0.01"):
            raise HTTPException(
                status_code=400,
                detail=f"Keshbek/ball bilan to'lash chekning {_max_pct.normalize():f}% idan oshmasligi kerak",
            )

    # ── Haqiqiy to'langan summa (UZS) ──
    paid_amount_uzs = Decimal("0")
    if getattr(data, "payments", None):
        for _p in data.payments:
            if _p.type.value not in ("debt", "cashback"):
                _p_rate = Decimal(str(getattr(_p, "rate", 1.0) or 1.0))
                paid_amount_uzs += _p.amount * _p_rate
    else:
        paid_amount_uzs = data.paid_amount * exchange_rate

    # Agar qarz bo'lsa va mijoz tanlanmagan bo'lsa xato ko'tarish
    if (paid_amount_uzs + paid_cashback_amount + redeem_points_uzs) < total_amount and not data.customer_id:
        raise HTTPException(status_code=400, detail="Qarzga sotish uchun mijozni tanlash majburiy")

    loyalty_earned = 0
    cashback_earned_amount = Decimal("0")
    loyalty_base_value = None
    prev_debt_balance = 0.0
    prev_debt_balances = None
    sale_debt_amounts = {}  # mijozsiz / qarzsiz sotuvda ham aniqlangan bo'lsin (UnboundLocalError)
    if data.customer_id:
        prev_debt_balance = float(customer.debt_balance or 0)
        
        # Legacy support
        if not customer.debt_balances and prev_debt_balance != 0:
            legacy_curr = (getattr(customer, "debt_currency", "UZS") or "UZS").strip().upper()
            customer.debt_balances = {legacy_curr: float(prev_debt_balance)}
            
        prev_debt_balances = dict(customer.debt_balances or {})

        if data.loyalty_points_used > 0:
            if data.loyalty_points_used > customer.loyalty_points:
                raise HTTPException(status_code=400, detail="Mijozda yetarli loyallik ballari yo'q")
            total_amount = max(Decimal("0"), total_amount - redeem_points_uzs)
            customer.loyalty_points -= data.loyalty_points_used

        if paid_cashback_amount > 0:
            avail_bonus = customer.bonus_balance or Decimal("0")
            if paid_cashback_amount > avail_bonus:
                raise HTTPException(
                    status_code=400,
                    detail=f"Bonus hisobida yetarli mablag' yo'q. Mavjud: {avail_bonus:.0f}, so'ralgan: {paid_cashback_amount:.0f}",
                )
            customer.bonus_balance = avail_bonus - paid_cashback_amount
            total_amount -= paid_cashback_amount
            if total_amount < Decimal("0"):
                total_amount = Decimal("0")

        # Keshbek/ball/total_spent — yagona hisob (T2.12); snapshot sotuvga yoziladi (teskari hisob uchun)
        from types import SimpleNamespace as _NS
        _loy = _NS()
        apply_sale_loyalty(customer, _loy, total_amount, rules, paid_uzs=paid_amount_uzs)
        cashback_earned_amount = _loy.cashback_earned
        loyalty_earned = _loy.loyalty_points_earned
        loyalty_base_value = _loy.loyalty_base

        if paid_amount_uzs < total_amount:
            debt_amount_uzs = total_amount - paid_amount_uzs
            if debt_amount_uzs > Decimal("0.01"):
                # Kredit limit (T2.12): yagona yordamchi, mijoz qatori yuqorida qulflangan (0 = cheklanmagan)
                check_credit_limit(db, customer, debt_amount_uzs)
                customer.debt_balance += debt_amount_uzs

                # Sync with multi-currency debt_balances
                if not customer.debt_balances:
                    customer.debt_balances = {}

                final_debts = {}
                if getattr(data, "currency_totals", None):
                    final_debts = {k: Decimal(str(v)) for k, v in data.currency_totals.items()}
                else:
                    currency_rates = {"UZS": Decimal("1.0")}
                    remain = {}
                    for item in sale_items_data:
                        curr = item["currency_code"]
                        currency_rates[curr] = item.get("exchange_rate", Decimal("1.0"))
                        remain[curr] = remain.get(curr, Decimal("0")) + item["subtotal"]
                    
                    if getattr(data, "payments", None):
                        for p in data.payments:
                            if p.currency:
                                currency_rates[p.currency] = getattr(p, "rate", Decimal("1.0")) or Decimal("1.0")
                            if p.type.value not in ("debt", "cashback"):
                                p_curr = p.currency or "UZS"
                                remain[p_curr] = remain.get(p_curr, Decimal("0")) - p.amount

                    if currency:
                        currency_rates[currency.code] = exchange_rate

                    if data.discount_amount > 0:
                        remain["UZS"] = remain.get("UZS", Decimal("0")) - data.discount_amount
                    if paid_cashback_amount > 0:
                        remain["UZS"] = remain.get("UZS", Decimal("0")) - paid_cashback_amount
                    if getattr(data, "loyalty_points_used", 0) > 0:
                        remain["UZS"] = remain.get("UZS", Decimal("0")) - redeem_points_uzs

                    overpaid_uzs = Decimal("0")
                    for c in list(remain.keys()):
                        if remain[c] < Decimal("-0.001"):
                            overpaid_uzs += abs(remain[c]) * currency_rates.get(c, Decimal("1"))
                            del remain[c]
                    
                    for c in list(remain.keys()):
                        if remain[c] > Decimal("0.001") and overpaid_uzs > Decimal("0.001"):
                            need_uzs = remain[c] * currency_rates.get(c, Decimal("1"))
                            if overpaid_uzs >= need_uzs:
                                overpaid_uzs -= need_uzs
                                del remain[c]
                            else:
                                remain[c] -= overpaid_uzs / currency_rates.get(c, Decimal("1"))
                                overpaid_uzs = Decimal("0")
                    
                    final_debts = {c: amt for c, amt in remain.items() if amt > Decimal("0.01")}

                # Baza va mijozning debt_balances ni yangilaymiz
                for curr_code, curr_debt in final_debts.items():
                    curr_val = Decimal(str(customer.debt_balances.get(curr_code, 0)))
                    customer.debt_balances[curr_code] = float(curr_val + curr_debt)

                # final_debts ni saqlab qolamiz sale.debt_amounts ga o'tkazish uchun
                sale_debt_amounts = {c: float(amt) for c, amt in final_debts.items()}

                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(customer, "debt_balances")
        else:
            sale_debt_amounts = {}

    # ── Kassa (T1.10) ─────────────────────────────────────────────────────────
    # Yagona qoida: so'ralgan kassa (data.wallet_id) -> kassirning default kassasi -> filial kassasi ->
    # filialning ochiq kassasi. Faqat haqiqiy pul tushsa (qarz/keshbek emas) yoki kassa aniq so'ralganda
    # aniqlanadi; >=2 filialli korxonada topilmasa 400 "Bu filial uchun kassa sozlanmagan".
    _payment_entries = build_sale_payment_entries(data, currency.code if currency else "UZS")
    _has_real_cash = any(
        Decimal(str(e["amount"] or 0)) > 0 and str(e["type"]) not in NON_CASH_PAYMENT_TYPES
        for e in _payment_entries
    )
    _sale_wallet = None
    if _has_real_cash or getattr(data, "wallet_id", None):
        _sale_wallet = resolve_wallet(
            db, current_user, branch_id=sale_branch_id, purpose="sale",
            requested_wallet_id=getattr(data, "wallet_id", None),
        )

    # ── Sale yozuvi ───────────────────────────────────────────────────────────
    # Hujjat raqami korxona/filial kesimida (T1.14); filial tranzaksiya filiali bilan bir xil aniqlanadi
    sale_create_kwargs = dict(
        number=generate_sale_number(db, current_user.company_id, sale_branch_id),
        cashier_id=current_user.id,
        company_id=current_user.company_id,
        warehouse_id=data.warehouse_id,
        branch_id=sale_branch_id,
        wallet_id=_sale_wallet.id if _sale_wallet is not None else None,
        customer_id=data.customer_id,
        total_amount=total_amount,
        discount_amount=data.discount_amount,
        paid_amount=data.paid_amount,
        paid_cash=data.paid_cash,
        paid_card=data.paid_card,
        paid_cashback=paid_cashback_amount,
        cashback_earned=cashback_earned_amount,
        payment_type=data.payment_type,
        status=SaleStatus.completed,
        note=data.note,
        currency_id=data.currency_id,
        exchange_rate=exchange_rate,
        loyalty_points_earned=loyalty_earned,
        loyalty_points_used=data.loyalty_points_used,
        loyalty_base=loyalty_base_value,
        debt_due_date=data.debt_due_date,
        debt_amounts=sale_debt_amounts,
        before_debt_balances=prev_debt_balances,
    )
    # Oflayn POS: agar sotuv vaqti yuborilgan bo'lsa — o'sha vaqtni saqla
    if getattr(data, 'created_at', None):
        sale_create_kwargs['created_at'] = data.created_at

    if idempotency_key:
        sale_create_kwargs['idempotency_key'] = idempotency_key

    # Sotuvni kassir smenasiga aniq bog'laymiz. Oflayn sotuv (created_at
    # yuborilgan) uchun avval o'sha vaqtni qamrab olgan smenani qidiramiz.
    # XAVFSIZLIK: faqat hali OCHIQ smenaga bog'laymiz — yopiq smenaning
    # inkassosi allaqachon hisoblangan, unga retro-bog'lash soxta created_at
    # bilan bugungi kutilgan g'aladon summasidan pulni "yashirish" yo'lini
    # ochardi. Kelajakdagi created_at ham e'tiborga olinmaydi.
    from app.models.shift import Shift as _Shift
    _shift = None
    _cat = getattr(data, 'created_at', None)
    if _cat is not None:
        # tz-aware bo'lsa UTC ga keltirib naive qilamiz — Shift.opened_at
        # naive-UTC saqlanadi, aralash solishtirish 5 soatlik siljish beradi.
        _cat = _to_naive_utc(_cat)
        from datetime import datetime as _dt
        if _cat <= _dt.utcnow():
            _shift = db.query(_Shift).filter(
                _Shift.cashier_id == current_user.id,
                _Shift.status == "open",
                _Shift.company_id == current_user.company_id,  # T1.1: korxona filtri
                _Shift.opened_at <= _cat,
            ).order_by(_Shift.opened_at.desc()).first()
    if _shift is None:
        _shift = db.query(_Shift).filter(
            _Shift.cashier_id == current_user.id,
            _Shift.status == "open",
            _Shift.company_id == current_user.company_id,  # T1.1: korxona filtri
        ).first()
    if _shift:
        sale_create_kwargs['shift_id'] = _shift.id

    sale = Sale(**sale_create_kwargs)
    db.add(sale)
    db.flush()
    approval_service.link_reference(_consumed_approval, "sale", sale.id)   # T4.6

    # T3.11: oflayn sinxronlangan sotuv (vaqt serverdan 10 daqiqadan ko'p farq qiladi) — audit
    if _cat is not None:
        from datetime import datetime as _dt2, timedelta as _td2
        _now = _dt2.utcnow()
        if abs(_cat - _now) > _td2(minutes=10):
            log_action(
                db=db, action="OFFLINE_SALE_SYNCED", entity_type="sale", entity_id=sale.id,
                user_id=current_user.id,
                new_values={
                    "number": sale.number,
                    "created_at": _cat.isoformat(),
                    "synced_at": _now.isoformat(),
                    "local_id": getattr(data, 'local_id', None),
                },
                ip_address=ip,
            )

    # ── To'lovlar + tranzaksiyalar ────────────────────────────────────────────
    tx_branch_id = sale_branch_id  # T1.9: tranzaksiya filiali = sotuv filiali

    # Hamyon: yuqorida resolve_wallet bilan aniqlangan (T1.10).
    # SalePayment, Transaction (T0.29), KassaMovement va Wallet.balance — post_sale_payments (T0.30).
    post_sale_payments(
        db, sale, _payment_entries,
        current_user, wallet_id=_sale_wallet.id if _sale_wallet is not None else None,
        tx_branch_id=tx_branch_id,
    )

    # ── Stock kamaytirish (FIFO Batch) ────────────────────────────────────────
    virtual_source_ids = list({
        d["source_product"].id for d in sale_items_data if d.get("source_product")
    })
    regular_ids = list({
        d["product"].id for d in sale_items_data if not d.get("source_product")
    })
    all_stock_ids = list(set(virtual_source_ids + regular_ids))

    # T1.6: har qator ombori aniqlanadi (T1.5 qoidasi), so'ng FAQAT kerakli (mahsulot, variant, ombor)
    # qatorlari qulflanadi: avval StockLevel (ORDER BY id), so'ng shu kalitlar partiyalari (ORDER BY id).
    # Kalitlar tartiblangani va qulf tartibi barqaror bo'lgani uchun teskari tartibli savatlar deadlock bermaydi.
    from app.models.inventory import StockLevel as _SL
    preferred_wh_id = data.warehouse_id

    def _row_key(d):
        sp = d.get("source_product") if d.get("conversion") is not None else d["product"]
        sv = None if d.get("conversion") is not None else d["variant_id"]
        wh = d.get("item_warehouse_id") or preferred_wh_id
        if not wh:
            raise HTTPException(status_code=400, detail="Ombor aniqlanmadi")
        return (sp.id, sv or None, wh)

    _lock_keys = sorted({_row_key(d) for d in sale_items_data}, key=lambda k: (k[0], k[1] or 0, k[2]))
    stock_rows = lock_stock_rows(db, _lock_keys)
    lock_batches(db, current_user.company_id, _lock_keys)

    new_sale_items = []
    new_movements = []

    # Kompaniya sozlamasi: minus qoldiqda sotish taqiqlangan bo'lsa bloklaymiz
    _neg_company = db.query(Company).filter(Company.id == current_user.company_id).first()
    block_negative_stock = _neg_company is not None and _neg_company.pos_allow_negative_stock is False

    for item_d in sale_items_data:
        product = item_d["product"]
        variant_id = item_d["variant_id"]
        qty_needed = Decimal(item_d["quantity"])
        is_virtual = item_d.get("conversion") is not None
        source_product = item_d.get("source_product")
        stock_product = source_product if is_virtual else product
        stock_variant_id = None if is_virtual else variant_id
        ratio = Decimal(str(item_d["conversion"].ratio)) if is_virtual else Decimal("1")
        qty_to_deduct = qty_needed * ratio if is_virtual else qty_needed

        item_preferred_wh = item_d.get("item_warehouse_id") or preferred_wh_id
        if not item_preferred_wh:
            # T1.5: ombor har doim aniqlangan (resolve_warehouse); boshqa omborlardan yechilmaydi
            raise HTTPException(status_code=400, detail="Ombor aniqlanmadi")
        _skey = (stock_product.id, stock_variant_id or None, item_preferred_wh)
        selected_stock = stock_rows.get(_skey)
        if selected_stock is None:
            selected_stock = _SL(product_id=stock_product.id, variant_id=stock_variant_id, warehouse_id=item_preferred_wh, quantity=Decimal("0"))
            db.add(selected_stock)
            stock_rows[_skey] = selected_stock

        if (
            block_negative_stock
            and getattr(stock_product, "product_type", "stock") != "service"
            and selected_stock.quantity < qty_to_deduct
        ):
            raise HTTPException(
                status_code=400,
                detail=f"'{stock_product.name}' mahsuloti qoldig'i yetarli emas. "
                       f"Mavjud: {selected_stock.quantity}, So'ralgan: {qty_to_deduct}",
            )

        item_warehouse_id = selected_stock.warehouse_id
        qty_before = selected_stock.quantity
        selected_stock.quantity -= qty_to_deduct

        from app.models.inventory import StockMovement, MovementType
        new_movements.append(StockMovement(
            product_id=stock_product.id,
            variant_id=stock_variant_id,
            warehouse_id=item_warehouse_id,
            type=MovementType.OUT,
            qty_before=qty_before,
            qty_after=selected_stock.quantity,
            quantity=qty_to_deduct,
            reference_type="sale",
            reference_id=sale.id,
            user_id=current_user.id,
            reason=f"Sotuv #{sale.number}" + (f" ({product.name} → {stock_product.name} x{ratio})" if is_virtual else ""),
        ))

        # Partiyalar — OMBOR bo'yicha (shu ombor, so'ng omborsiz eskilari); update_sale/tasdiqlash bilan
        # bir xil servis (T1.6). Qulf yuqorida olingan; yetmagan qism mahsulot tannarxi bilan.
        allocated_batches, shortfall = allocate_batches(
            db, company_id=current_user.company_id, product_id=stock_product.id, variant_id=stock_variant_id,
            warehouse_id=item_warehouse_id, quantity=qty_to_deduct,
            perishable=is_perishable_product(stock_product), today=tashkent_today(), lock=False,
        )
        total_cost = allocation_cost(
            allocated_batches, shortfall,
            source_product.cost_price if is_virtual else product.cost_price,
        )

        exact_unit_cost = total_cost / qty_needed if qty_needed > 0 else Decimal("0")

        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            variant_id=variant_id,
            warehouse_id=item_warehouse_id,
            unit=product.unit or "dona",
            quantity=qty_needed,
            unit_price=item_d["unit_price"],
            cost_price=exact_unit_cost,
            discount=item_d["discount"],
            subtotal=item_d["subtotal"],
            currency_code=item_d["currency_code"],
            exchange_rate=item_d["exchange_rate"],
            marking_codes=item_d["marking_codes"] or None,
            promotion_id=item_d.get("promotion_id"),
            promotion_discount=item_d.get("promotion_discount"),
        )
        new_sale_items.append((sale_item, allocated_batches))

    for sale_item, _ in new_sale_items:
        db.add(sale_item)
    db.flush()

    for sale_item, allocated_batches in new_sale_items:
        for ab in allocated_batches:
            db.add(SaleItemBatch(
                sale_item_id=sale_item.id,
                batch_id=ab["batch_id"],
                quantity=ab["quantity"],
                unit_cost=ab["unit_cost"],
            ))
    for mov in new_movements:
        db.add(mov)

    if getattr(data, "delivery", None) is not None:
        from app.services.sale_delivery_service import upsert_sale_delivery
        upsert_sale_delivery(db, sale, data.delivery, current_user.company_id)

    log_action(
        db=db, action="SALE", entity_type="sale", entity_id=sale.id,
        user_id=current_user.id,
        new_values={"number": sale.number, "total": str(total_amount), "payment": data.payment_type.value},
        ip_address=ip,
    )
    db.commit()

    # ── Telegram notification ─────────────────────────────────────────────────
    if data.customer_id and customer:
        if getattr(customer, "tg_chat_id", None):
            company = db.query(Company).filter(Company.id == current_user.company_id).first()
            if company and getattr(company, "tg_bot_token", None):
                _token = str(company.tg_bot_token)
                _chat_id = str(customer.tg_chat_id)
                _sale_id = sale.id
                _prev_debt = prev_debt_balance
                _new_debt = float(customer.debt_balance or 0)
                _seller = current_user.name
                _comp_name = str(company.name)
                _cust_name = str(customer.name)

                def _bg_send(token, chat_id, sale_id, prev_debt, new_debt, seller, comp_name, cust_name):
                    try:
                        from app.database import SessionLocal
                        from sqlalchemy.orm import joinedload as _jl
                        _db = SessionLocal()
                        try:
                            from app.models.sale import Sale as _Sale, SaleItem as _SI
                            from app.models.warehouse import Warehouse as _Wh
                            from app.utils.telegram_text import esc as _esc
                            _sale = (
                                _db.query(_Sale)
                                .options(
                                    _jl(_Sale.items).joinedload(_SI.product), _jl(_Sale.payments),
                                    _jl(_Sale.branch), _jl(_Sale.warehouse).joinedload(_Wh.branch),
                                )
                                .filter(_Sale.id == sale_id)
                                .first()
                            )
                            if not _sale:
                                return

                            def FMT(v):
                                val = float(v or 0)
                                return f"{int(val):,}".replace(",", " ") if val == int(val) else f"{val:,.1f}".replace(",", " ")

                            pay_labels = {
                                "cash": "💵Naqd", "card": "💳Karta", "uzcard": "💳UzCard",
                                "humo": "💳Humo", "bank": "🏦Bank", "click": "📱Click",
                                "payme": "📱Payme", "visa": "💳Visa", "uzum": "📱Uzum",
                                "debt": "🔖Qarz", "mixed": "💰Aralash",
                            }
                            if _sale.payments:
                                pay_lines = "\n".join(
                                    f"{pay_labels.get(str(p.payment_type), str(p.payment_type))}: som {FMT(p.amount)}"
                                    for p in _sale.payments if float(p.amount or 0) > 0
                                )
                            else:
                                pt = str(_sale.payment_type.value if hasattr(_sale.payment_type, "value") else _sale.payment_type)
                                pay_lines = f"{pay_labels.get(pt, pt)}: som {FMT(_sale.total_amount)}"

                            item_lines = []
                            total_qty = 0
                            for it in _sale.items:
                                pname = it.product.name if it.product else f"ID={it.product_id}"
                                qty = float(it.quantity)
                                total_qty += qty
                                qty_str = str(int(qty)) if qty == int(qty) else f"{qty:g}"
                                item_lines.append(f"{pname}\n{qty_str} dona x som {FMT(it.unit_price)} = som {FMT(it.subtotal)}")

                            status_map = {
                                "completed": "Bajarildi", "pending": "Kutilmoqda",
                                "refunded": "Qaytarildi", "cancelled": "Bekor qilindi",
                                "partial_refund": "Qisman qaytarildi",
                            }
                            st = str(_sale.status.value if hasattr(_sale.status, "value") else _sale.status)
                            sale_date = _sale.created_at.strftime("%d.%m.%Y %H:%M") if _sale.created_at else "-"
                            tqty_str = str(int(total_qty)) if total_qty == int(total_qty) else f"{total_qty:g}"

                            # T3.7: sotuv filiali (snapshot, bo'lmasa ombor filiali) — nomi va telefoni
                            _br = _sale.branch or (_sale.warehouse.branch if _sale.warehouse else None)
                            branch_lines = ""
                            if _br is not None:
                                branch_lines = f"Filial: {_esc(_br.name)}\n"
                                if _br.phone:
                                    branch_lines += f"Tel: {_esc(_br.phone)}\n"

                            receipt = (
                                f"🧾 <b>Sotuv cheki</b>\n\n"
                                f"Mijoz: {cust_name}\n"
                                f"💴 Savdodan oldingi balans: som {FMT(prev_debt)}\n"
                                f"💰 Hozirgi balans: som {FMT(new_debt)}\n"
                                f"Savdo: #{_sale.number}\n"
                                f"Mahsulotlar:\n" + "\n".join(item_lines) +
                                f"\nTashkilot: {comp_name}\n"
                                f"{branch_lines}"
                                f"To'lov usuli:\n{pay_lines}\n\n"
                                f"Sotuvchi: {seller}\n"
                                f"📅 Sana: {sale_date}\n"
                                f"Holati: {status_map.get(st, st)}\n"
                                f"Jami: som {FMT(_sale.total_amount)}\n"
                                f"Jami miqdor: {tqty_str}\n"
                                f"🏷 Jami chegirma: som {FMT(_sale.discount_amount)}"
                            )
                            send_tg_sync(token, chat_id, receipt)
                        finally:
                            _db.close()
                    except Exception as e:
                        print("Telegram BG error:", e)

                if background_tasks:
                    background_tasks.add_task(
                        _bg_send, _token, _chat_id, _sale_id,
                        _prev_debt, _new_debt, _seller, _comp_name, _cust_name,
                    )
                else:
                    threading.Thread(
                        target=_bg_send,
                        args=(_token, _chat_id, _sale_id, _prev_debt, _new_debt, _seller, _comp_name, _cust_name),
                        daemon=True,
                    ).start()

    return sale


def create_pending_sale(
    db: Session,
    data: SaleCreate,
    current_user: User,
    ip: Optional[str] = None,
    agent_id: Optional[int] = None,
) -> Sale:
    """Ulgurji sotuv — to'lovsiz (pending). Stock va tranzaksiyalarga tegmaydi."""
    _assert_branch_open(db, current_user)
    _assert_shift_if_required(db, current_user)
    if data.warehouse_id is None:
        # T1.5: create_sale bilan bir xil qoida (bitta yordamchi)
        data.warehouse_id = resolve_warehouse(
            db, current_user.company_id, branch_id=_sale_branch_of(db, current_user), purpose="sale", user=current_user,
        )
    else:
        # T0.13: mijoz yuborgan ombor — korxona/faollik/filial bo'yicha
        from app.services.sale_helpers import validate_sale_warehouse
        validate_sale_warehouse(db, current_user, data.warehouse_id)
    _pend_item_wh_ids = {i.warehouse_id for i in data.items if getattr(i, "warehouse_id", None)}
    if _pend_item_wh_ids:
        from app.services.sale_helpers import validate_sale_warehouses
        validate_sale_warehouses(db, current_user, _pend_item_wh_ids)
    pend_branch_id = _sale_branch_snapshot(db, current_user, data.warehouse_id, _pend_item_wh_ids)

    _p_ids = [item.product_id for item in data.items]

    _products_map = {
        p.id: p for p in db.query(Product).filter(
            Product.id.in_(_p_ids),
            Product.company_id == current_user.company_id,
            Product.is_deleted == False,
        ).all()
    }

    # T4.3: filial narxlari va amaldagi aksiyalar
    _pend_ctx = load_sale_pricing_context(db, current_user, data.warehouse_id, data.items)

    _pend_customer = None
    _pend_customer_prices = {}
    if data.customer_id:
        # Mijoz faqat o'z korxonasidan bo'lishi shart (create_sale bilan bir xil)
        _pend_customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).first()
        if not _pend_customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
        if _pend_customer.is_active is False:
            raise HTTPException(status_code=400, detail=ARCHIVED_DETAIL)
        _pend_customer_prices = {
            cp.product_id: cp for cp in db.query(CustomerPrice).filter(
                CustomerPrice.customer_id == data.customer_id,
                CustomerPrice.product_id.in_(_p_ids),
            ).all()
        }

    _pend_conversions = {
        c.sell_product_id: c for c in db.query(ProductConversion).filter(
            ProductConversion.sell_product_id.in_(_p_ids),
        ).all()
    }
    _pend_src_ids = list({c.source_product_id for c in _pend_conversions.values()})
    _pend_sources = {}
    if _pend_src_ids:
        _pend_sources = {
            p.id: p for p in db.query(Product).filter(
                Product.id.in_(_pend_src_ids),
            ).all()
        }

    sale_items_data = []
    total_amount = Decimal("0")

    for item_data in data.items:
        product = _products_map.get(item_data.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Mahsulot ID={item_data.product_id} topilmadi")

        _customer_price = _pend_customer_prices.get(item_data.product_id) if data.customer_id else None
        unit_price, discount, _price_src = resolve_item_pricing(
            item_data, product, _customer_price, _pend_customer, current_user,
            branch_price=_pend_ctx.branch_price(item_data.product_id, getattr(item_data, "variant_id", None)))
        discount, _promo_id, _promo_disc = _pend_ctx.apply(item_data, unit_price, discount)
        if discount > unit_price * item_data.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"'{product.name}' uchun chegirma ({discount}) narxdan oshib ketdi",
            )
        subtotal = max(Decimal("0"), (unit_price * item_data.quantity) - discount)

        conversion = _pend_conversions.get(product.id)
        cost_price = product.cost_price
        if conversion:
            source = _pend_sources.get(conversion.source_product_id)
            if source:
                cost_price = (source.cost_price or Decimal("0")) * conversion.ratio

        # Pending (qoralama) sotuv — markirovka hali to'liq skanerlanmagan bo'lishi
        # mumkin, shuning uchun bu bosqichda majburiy tekshirilmaydi. Qat'iy
        # tekshiruv sotuv "completed" holatiga o'tganda (update_sale) qo'llanadi.
        marking_codes = [c for c in (getattr(item_data, "marking_codes", None) or []) if c and c.strip()]

        sale_items_data.append({
            "product": product,
            "quantity": item_data.quantity,
            "unit_price": unit_price,
            "cost_price": cost_price,
            "discount": discount,
            "subtotal": subtotal,
            "marking_codes": marking_codes,
            "promotion_id": _promo_id,
            "promotion_discount": _promo_disc,
        })
        total_amount += subtotal

    total_amount = max(Decimal("0"), total_amount - data.discount_amount)

    sale = Sale(
        number=generate_sale_number(db, current_user.company_id, pend_branch_id),
        cashier_id=current_user.id,
        company_id=current_user.company_id,
        warehouse_id=data.warehouse_id,
        branch_id=pend_branch_id,
        customer_id=data.customer_id,
        total_amount=total_amount,
        discount_amount=data.discount_amount,
        paid_amount=Decimal("0"),
        paid_cash=Decimal("0"),
        paid_card=Decimal("0"),
        payment_type=PaymentType.cash,
        status=SaleStatus.pending,
        note=data.note,
        currency_id=data.currency_id,
        exchange_rate=Decimal("1"),
        loyalty_points_earned=0,
        loyalty_points_used=0,
        debt_due_date=None,
    )
    from app.models.shift import Shift as _Shift
    _open_shift = db.query(_Shift).filter(
        _Shift.cashier_id == current_user.id,
        _Shift.status == "open",
        _Shift.company_id == current_user.company_id,  # T1.1: korxona filtri
    ).first()
    if _open_shift:
        sale.shift_id = _open_shift.id
    if agent_id:
        sale.agent_id = agent_id
    db.add(sale)
    db.flush()

    for item_d in sale_items_data:
        db.add(SaleItem(
            sale_id=sale.id,
            product_id=item_d["product"].id,
            quantity=item_d["quantity"],
            unit_price=item_d["unit_price"],
            cost_price=item_d["cost_price"],
            discount=item_d["discount"],
            subtotal=item_d["subtotal"],
            marking_codes=item_d["marking_codes"] or None,
            promotion_id=item_d.get("promotion_id"),
            promotion_discount=item_d.get("promotion_discount"),
        ))

    if getattr(data, "delivery", None) is not None:
        from app.services.sale_delivery_service import upsert_sale_delivery
        upsert_sale_delivery(db, sale, data.delivery, current_user.company_id)

    log_action(
        db=db, action="SALE_PENDING", entity_type="sale", entity_id=sale.id,
        user_id=current_user.id,
        new_values={"number": sale.number, "total": str(total_amount), "status": "pending"},
        ip_address=ip,
    )
    db.commit()
    return sale
