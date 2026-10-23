from datetime import timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.audit import log_action
from app.models.customer import Customer
from app.models.customer_prices import CustomerPrice
from app.models.moliya import Transaction
from app.models.product import Product, ProductConversion
from app.models.sale import Sale, SaleItem, SaleStatus, PaymentType
from app.models.shift import Shift
from app.models.user import User, UserRole
from app.services.customer_service import lock_customer, ARCHIVED_DETAIL
from app.services.credit_service import check_credit_limit
from app.services.loyalty_service import (
    get_loyalty_rules, apply_sale_loyalty, reverse_sale_loyalty, clear_sale_loyalty, restore_customer_debt,
)
from app.services.sale_cash import build_sale_payment_entries, post_sale_payments, reverse_sale_payments
from app.services.sale_delete import cancel_sale_effects
from app.services.sale_helpers import (
    resolve_item_pricing, apply_sale_branch_filter, resolve_txn_branch, assert_sale_items_one_branch,
    _warehouse_branch_id, SALE_WAREHOUSE_BRANCH_CHANGE,
)
from app.services.batch_allocator import assert_pharmacy_sellable, deduct_sale_item, tashkent_today
from app.services.pharmacy import pharmacy_context
from app.services.sale_stock import is_return_linked, restore_sale_batches, restore_sale_stock
from app.services.sale_create import _resolve_marking_codes, _prepare_prescriptions, _is_open_box_line
from app.services.sale_stock import resolve_sale_unit  # CD.1: tahrirda qadoq birligi (dorixona)
from app.models.product_units import SaleItemUnit
from app.models.prescription import SalePrescription
from app.services.promotion_service import load_sale_pricing_context
from app.services.tenant_guards import BRANCH_FREE_ROLES

CANNOT_EDIT_RETURNED = "Qaytarish bilan bog'liq sotuvni tahrirlab bo'lmaydi"


def _earn_on_confirm(db: Session, sale: Sale, customer: Customer, paid_amount) -> None:
    """Kutilayotgan (pending) sotuv yakunlanganda mijozga keshbek/ball/total_spent yoziladi (T2.12)."""
    rules = get_loyalty_rules(db, sale.company_id, branch_id=sale.branch_id)
    exr = Decimal(str(sale.exchange_rate or 1))
    apply_sale_loyalty(
        customer, sale, Decimal(str(sale.total_amount or 0)), rules,
        paid_uzs=Decimal(str(paid_amount or 0)) * exr,
    )


def _pharmacy_check_lines(db: Session, sale: Sale, rows, ph_ctx, credit=None) -> None:
    """D1.2: dorixona rejimida qoldiq yechilishidan OLDIN yaroqli partiyalar yetarliligini tekshiradi.

    `rows`: `(product, variant_id, warehouse_id|None, quantity)`; virtual mahsulot manba mahsulotga
    o'tkaziladi (`deduct_target_for_sale`, deduct_sale_item bilan bir xil). Modul o'chiq bo'lsa hech narsa qilmaydi.
    """
    if not ph_ctx[0]:
        return
    from app.utils.product_conversion import deduct_target_for_sale
    lines = []
    for product, variant_id, wh_id, qty in rows:
        if product is None:
            continue
        _did, deduct_qty, conv, src = deduct_target_for_sale(db, product.id, Decimal(str(qty or 0)))
        lines.append((
            src if (conv and src) else product,
            None if conv else variant_id,
            wh_id if wh_id is not None else sale.warehouse_id,
            deduct_qty,
        ))
    assert_pharmacy_sellable(
        db, company_id=sale.company_id, lines=lines, pharmacy_ctx=ph_ctx, today=tashkent_today(), credit=credit,
    )


def _sale_batch_credit(db: Session, sale: Sale) -> dict:
    """Sotuv teskari qilinganda partiyalarga qaytadigan miqdor: {batch_id: miqdor} (SaleItemBatch bo'yicha)."""
    from app.models.sale import SaleItemBatch
    credit: dict = {}
    rows = (
        db.query(SaleItemBatch.batch_id, SaleItemBatch.quantity)
        .join(SaleItem, SaleItem.id == SaleItemBatch.sale_item_id)
        .filter(SaleItem.sale_id == sale.id)
        .all()
    )
    for batch_id, qty in rows:
        credit[batch_id] = credit.get(batch_id, Decimal("0")) + Decimal(str(qty or 0))
    return credit


def _release_sale_marking(db: Session, sale: Sale) -> None:
    """CD.1/D3.2: sotuv teskari qilinganda (tahrir, kutilayotganga qaytarish, bekor qilish) shu sotuv qatorlarining
    `sold` kodlari omborga qaytadi (in_stock). Qutidan bo'lib sotishdagi kodlar holati o'zgarmagan edi — tegilmaydi."""
    from app.models.marking_code import MarkingCode
    item_ids = [r[0] for r in db.query(SaleItem.id).filter(SaleItem.sale_id == sale.id).all()]
    if not item_ids:
        return
    for row in db.query(MarkingCode).filter(
        MarkingCode.company_id == sale.company_id, MarkingCode.sale_item_id.in_(item_ids),
        MarkingCode.status == "sold",
    ).with_for_update().all():
        row.status = "in_stock"
        row.sale_item_id = None
    db.flush()


def _confirm_rx_and_marking(db: Session, sale: Sale, data, ph_ctx, items) -> tuple:
    """CD.1: kutilayotgan sotuvni tasdiqlash (qatorlar o'zgarmaydi): dorixonada retsept tekshiruvi va markirovka kodlari
    (yozishdan OLDIN; xato bo'lsa 400). Qaytaradi: (retsept qatorlari, markirovka rejasi). Modul o'chiq bo'lsa ([], {})."""
    if not ph_ctx[0]:
        return [], {}
    from app.routers.pharmacy_marking import plan_sale_marking
    convs = {c.sell_product_id: c for c in db.query(ProductConversion).filter(
        ProductConversion.sell_product_id.in_([it.product_id for it in items])).all()} if items else {}
    srcs = {}
    if convs:
        srcs = {p.id: p for p in db.query(Product).filter(
            Product.id.in_({c.source_product_id for c in convs.values()})).all()}
    lines = []
    for it in items:
        conv = convs.get(it.product_id)
        lines.append({
            "product": it.product, "conversion": conv,
            "source_product": srcs.get(conv.source_product_id) if conv is not None else None,
        })
    rx_data = SimpleNamespace(
        items=[SimpleNamespace(product_id=it.product_id) for it in items],
        prescriptions=getattr(data, "prescriptions", None), rx_override_reason=getattr(data, "rx_override_reason", None),
    )
    rx_rows, _warn = _prepare_prescriptions(db, rx_data, lines, sale.company_id, ph_ctx, tashkent_today())
    mk_lines = []
    for idx, (it, ln) in enumerate(zip(items, lines)):
        codes = [c for c in (it.marking_codes or []) if c and str(c).strip()]
        prod = it.product
        if prod is not None and prod.requires_marking and ph_ctx[0]:
            if db.query(SaleItemUnit.id).filter(SaleItemUnit.sale_item_id == it.id).first() is None                     and len(codes) != int(it.quantity):
                raise HTTPException(
                    status_code=400,
                    detail=(f"'{prod.name}' — markirovka talab qilinadi. "
                            f"{int(it.quantity)} ta kod skanerlanishi kerak, {len(codes)} ta kiritildi."),
                )
        mk_lines.append((idx, prod, ln["source_product"], codes))
    plan = plan_sale_marking(db, sale.company_id, [l for l in mk_lines if l[1] is not None])
    return rx_rows, plan


def _write_prescriptions(db: Session, sale: Sale, rx_rows: list, item_by_pid: dict) -> None:
    for row in rx_rows:
        db.add(SalePrescription(
            sale_id=sale.id, sale_item_id=item_by_pid.get(row["product_id"]), company_id=sale.company_id, **row,
        ))


def _reverse_sale_effects(db: Session, sale: Sale, current_user: User, release_marking: bool = False) -> list:
    """Sotuvning barcha moliyaviy ta'sirlarini bekor qilish.

    Qoldiq qator ombori va variant bo'yicha, partiyalar `SaleItemBatch` bo'yicha,
    kassa `KassaMovement` sof qoldig'i bo'yicha teskari qilinadi (T0.30).
    Teskari qilingan hamyon id'lari ro'yxatini qaytaradi (qayta yozishda shu hamyon afzal).
    """
    from app.models.sale import SalePayment

    # Qulf tartibi: mijoz -> qoldiq -> hamyon
    customer = None
    if sale.customer_id and sale.status != SaleStatus.pending:
        customer = lock_customer(db, sale.customer_id, sale.company_id, allow_inactive=True, required=False)

    restore_sale_stock(db, sale)
    restore_sale_batches(db, sale)
    if release_marking:
        _release_sale_marking(db, sale)   # CD.1: dorixona — eski kodlar in_stock ga qaytadi

    if customer is not None:
        # Qarzni tiklash: sale.debt_amounts JSON dan aniq valyuta miqdorlarini ishlatamiz
        # Bu _reverse_sale_effects dan keyin yangi qarz to'g'ri yozilishini ta'minlaydi
        debt_amounts = getattr(sale, 'debt_amounts', None) or {}
        if isinstance(debt_amounts, dict) and debt_amounts:
            # Multi-currency: har bir valyuta uchun alohida ayirish
            from sqlalchemy.orm.attributes import flag_modified
            if not customer.debt_balances:
                customer.debt_balances = {}

            exr = Decimal(str(sale.exchange_rate or 1))

            # debt_amounts sotuv oxirgi marta saqlanganda yozilgan qarz
            # miqdori - agar shundan beri pay_debt orqali qisman to'lov
            # bo'lgan bo'lsa (paid_amount ortgan, debt_amounts esa
            # yangilanmagan), uni to'liq ayirish allaqachon to'langan
            # qismni IKKINCHI marta ayirib, mijozning BOSHQA sotuvidagi
            # qarzini ham yo'q qilib yuborishi mumkin. Shuning uchun
            # reversalni joriy haqiqiy qoldiqqa moslab proportsional
            # kichraytiramiz.
            recorded_uzs = sum(
                (Decimal(str(amt)) * (Decimal("1") if curr == "UZS" else exr))
                for curr, amt in debt_amounts.items()
            )
            actual_outstanding_uzs = max(
                Decimal("0"),
                (Decimal(str(sale.total_amount or 0)) - Decimal(str(sale.paid_amount or 0))) * exr,
            )
            scale = Decimal("1")
            if recorded_uzs > Decimal("0.01"):
                scale = min(Decimal("1"), actual_outstanding_uzs / recorded_uzs)

            for curr_code, amt in debt_amounts.items():
                amt_d = Decimal(str(amt)) * scale
                if amt_d > Decimal("0.001"):
                    curr_val = Decimal(str(customer.debt_balances.get(curr_code, 0)))
                    customer.debt_balances[curr_code] = float(
                        max(Decimal("0"), curr_val - amt_d)
                    )
                    # Aggregate UZS balance
                    uzs_equiv = amt_d * (Decimal("1") if curr_code == "UZS" else exr)
                    customer.debt_balance = max(
                        Decimal("0"),
                        (customer.debt_balance or Decimal("0")) - uzs_equiv,
                    )
            flag_modified(customer, "debt_balances")
        else:
            # Eski sotuvlar uchun fallback: qarz loyalty_service orqali tiklanadi
            restore_customer_debt(customer, sale)
        # Keshbek/ball/total_spent — qarz bor-yo'qligidan qat'i nazar, sotuvda saqlangan qiymatlar bo'yicha (T2.12)
        reverse_sale_loyalty(customer, sale)

    for otx in db.query(Transaction).filter(
        Transaction.reference_type == "sale",
        Transaction.reference_id == sale.id,
        Transaction.type == "income",
    ).all():
        db.delete(otx)

    # Kassa: sof qoldiq bo'yicha teskari harakat (eski yozuvlar audit uchun qoladi)
    reversed_wallet_ids = reverse_sale_payments(db, sale, current_user)

    db.query(SalePayment).filter(SalePayment.sale_id == sale.id).delete()

    for item in db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all():
        db.delete(item)

    db.flush()
    # Kolleksiyalar keyingi murojaatda bazadan qayta yuklansin (eskirgan nusxalar qolmasin)
    db.expire(sale, ["items", "payments"])
    return reversed_wallet_ids


def update_sale(db: Session, sale_id: int, data, current_user: User) -> Sale:
    """Sotuvni yangilash: holat/izoh yoki to'liq tahrirlash (items bilan)."""
    q = (
        db.query(Sale)
        .options(joinedload(Sale.items), joinedload(Sale.payments))
        .filter(Sale.id == sale_id)
    )
    if current_user.role != UserRole.super_admin:
        q = q.filter(Sale.company_id == current_user.company_id)
    q = apply_sale_branch_filter(q, db, current_user)
    # Sotuv qatori qulflanadi — parallel tahrir/o'chirish bir-birining ustidan yozmasin
    sale = q.with_for_update(of=Sale).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")
    _old_status = sale.status

    # Kassir cheklovlari (mutatsiyadan oldin): bekor qilish/qaytarish — menejer/admin ishi;
    # tugallangan sotuvni faqat o'z ochiq smenasida tahrirlay oladi
    if current_user.role == UserRole.cashier:
        if data.status in (SaleStatus.cancelled, SaleStatus.refunded):
            raise HTTPException(status_code=403, detail="Sotuvni bekor qilish uchun menejer/admin kerak")
        if sale.status != SaleStatus.pending:
            _shift = db.get(Shift, sale.shift_id) if sale.shift_id else None
            if sale.cashier_id != current_user.id or not _shift or _shift.status != "open":
                raise HTTPException(status_code=403, detail="Faqat o'z ochiq smenangizdagi sotuvni tahrirlay olasiz")
        elif sale.cashier_id != current_user.id:
            raise HTTPException(status_code=403, detail="Faqat o'zingiz yaratgan sotuvni tahrirlay olasiz")

    # Qaytarish holati faqat qaytarish amali orqali qo'yiladi (PUT bilan emas) (T0.30)
    if data.status == SaleStatus.refunded:
        raise HTTPException(status_code=400, detail="Qaytarish holatini tahrirlash orqali qo'yib bo'lmaydi")
    # Qaytarish bilan bog'liq sotuv (R... hujjat, refunded/partial_refund, qaytarilgan qator):
    # items/status/paid_amount o'zgartirish qoldiq va pulni ikki marta hisoblaydi — faqat izoh
    _wants_change = (
        data.items is not None
        or (data.status is not None and data.status != sale.status)
        or (data.paid_amount is not None and Decimal(str(data.paid_amount)) != Decimal(str(sale.paid_amount or 0)))
    )
    if _wants_change and is_return_linked(db, sale):
        raise HTTPException(status_code=400, detail=CANNOT_EDIT_RETURNED)

    # Kompaniya sozlamasi: minus qoldiqda sotish taqiqlanganmi
    from app.models.company import Company as _Company
    _neg_company = db.query(_Company).filter(_Company.id == sale.company_id).first()
    allow_negative_stock = not (_neg_company is not None and _neg_company.pos_allow_negative_stock is False)

    if data.items is not None:
        # ── To'liq tahrirlash ─────────────────────────────────────────────────
        old_paid_amount = Decimal(str(sale.paid_amount or 0))
        old_payment_type = sale.payment_type
        old_paid_cash = Decimal(str(sale.paid_cash or 0))
        old_paid_card = Decimal(str(sale.paid_card or 0))

        # Yangi mijoz korxonaga tegishli ekanini oldindan tekshirish (qaytarishdan oldin)
        if data.customer_id is not None:
            _chk_customer = db.query(Customer).filter(
                Customer.id == data.customer_id,
                Customer.company_id == sale.company_id,
            ).first()
            if not _chk_customer:
                raise HTTPException(status_code=404, detail="Mijoz topilmadi")
            # T0.26: arxivlangan mijozga o'tkazib bo'lmaydi (teskari ta'sirlardan oldin tekshiriladi)
            if data.customer_id != sale.customer_id and _chk_customer.is_active is False:
                raise HTTPException(status_code=400, detail=ARCHIVED_DETAIL)

        # T0.13: mijoz yuborgan ombor(lar) — teskari ta'sirlar yozilishidan OLDIN tekshiriladi
        _upd_wh_ids = {i.warehouse_id for i in data.items if getattr(i, "warehouse_id", None)}
        if data.warehouse_id is not None:
            _upd_wh_ids.add(data.warehouse_id)
        if _upd_wh_ids:
            from app.services.sale_helpers import validate_sale_warehouses
            validate_sale_warehouses(db, current_user, _upd_wh_ids, company_id=sale.company_id)

        # T1.9: sotuv filiali snapshot'i tahrirda saqlanadi. Ombor o'zgarsa va yangi ombor boshqa
        # filialniki bo'lsa — sotuv filiali ham o'sha filialga o'tadi, lekin faqat admin/director uchun.
        _hdr_wh_id = data.warehouse_id if data.warehouse_id is not None else sale.warehouse_id
        assert_sale_items_one_branch(
            db, current_user, _hdr_wh_id,
            {i.warehouse_id for i in data.items if getattr(i, "warehouse_id", None)},
            company_id=sale.company_id,
        )
        _new_sale_branch = None
        if data.warehouse_id is not None and data.warehouse_id != sale.warehouse_id:
            _wh_branch = _warehouse_branch_id(db, sale.company_id, data.warehouse_id)
            if _wh_branch is not None and _wh_branch != resolve_txn_branch(db, current_user, sale=sale):
                if current_user.role not in BRANCH_FREE_ROLES:
                    raise HTTPException(status_code=403, detail=SALE_WAREHOUSE_BRANCH_CHANGE)
                _new_sale_branch = _wh_branch

        # D1.2: dorixona rejimi — yangi qatorlar uchun yaroqli partiyalar yetarliligi teskari ta'sirlar yozilishidan
        # OLDIN tekshiriladi (eski sotuv partiyalariga qaytadigan miqdor hisobga olinadi). `pharmacy_context` bir marta.
        _ph_ctx = pharmacy_context(db, sale.company_id)
        # CD.1: qadoq birligi (quti/blister) — miqdor asosiy birlikka o'tkaziladi (oddiy korxonada resolve_sale_unit 400 beradi)
        _unit_ctxs = {}
        for _ix, _it in enumerate(data.items):
            if getattr(_it, "unit_id", None):
                _up = db.query(Product).filter(
                    Product.id == _it.product_id, Product.company_id == current_user.company_id,
                    Product.is_deleted == False,
                ).first()
                if _up is None:
                    raise HTTPException(status_code=404, detail=f"Mahsulot ID={_it.product_id} topilmadi")
                _unit_ctxs[_ix] = resolve_sale_unit(db, sale.company_id, _up, _it, _ph_ctx)
        if _ph_ctx[0]:
            if data.status is not None:
                _ph_pending = data.status == SaleStatus.pending
            elif sale.status == SaleStatus.pending:
                _ph_pending = not (bool(data.payments) or (data.paid_amount is not None and data.paid_amount > 0)
                                   or (data.payment_type if data.payment_type is not None else old_payment_type) == PaymentType.debt)
            else:
                _ph_pending = sale.status == SaleStatus.pending
            if not _ph_pending:
                _ph_rows = []
                for _ix, _i in enumerate(data.items):
                    _p = db.query(Product).filter(
                        Product.id == _i.product_id, Product.company_id == current_user.company_id,
                        Product.is_deleted == False,
                    ).first()
                    _q = _unit_ctxs[_ix]["base_qty"] if _ix in _unit_ctxs else _i.quantity
                    _ph_rows.append((_p, getattr(_i, "variant_id", None), getattr(_i, "warehouse_id", None) or _hdr_wh_id, _q))
                _pharmacy_check_lines(db, sale, _ph_rows, _ph_ctx, credit=_sale_batch_credit(db, sale))

        # T2.12: tahrirda sarflangan keshbek/ball qayta yechiladi (teskari hisobda mijozga qaytadi)
        _old_pc =Decimal(str(sale.paid_cashback or 0))
        _old_pts = int(sale.loyalty_points_used or 0)
        _old_customer_id = sale.customer_id
        _reversed_wallet_ids = _reverse_sale_effects(db, sale, current_user, release_marking=_ph_ctx[0])
        clear_sale_loyalty(sale)
        if _new_sale_branch is not None:
            sale.branch_id = _new_sale_branch

        wh_id = data.warehouse_id if data.warehouse_id is not None else sale.warehouse_id
        disc_amount = data.discount_amount if data.discount_amount is not None else Decimal("0")
        payment_type = data.payment_type if data.payment_type is not None else old_payment_type
        new_customer_id = data.customer_id if data.customer_id is not None else sale.customer_id

        if data.status is not None:
            final_status = data.status
        elif sale.status == SaleStatus.pending:
            has_payment = bool(data.payments) or (data.paid_amount is not None and data.paid_amount > 0) or (payment_type == PaymentType.debt)
            final_status = SaleStatus.completed if has_payment else SaleStatus.pending
        else:
            final_status = sale.status

        # T4.3: filial narxlari va aksiyalar (aksiya sotuv yaratilgan vaqt bo'yicha tekshiriladi)
        _upd_now = None
        if sale.created_at is not None:
            _c = sale.created_at
            _upd_now = (_c + timedelta(hours=5)).replace(tzinfo=None) if getattr(_c, "tzinfo", None) is None                 else (_c.astimezone(timezone.utc) + timedelta(hours=5)).replace(tzinfo=None)
        _pricing_ctx = load_sale_pricing_context(
            db, current_user, wh_id, data.items, company_id=sale.company_id, now=_upd_now)

        sale_items_data = []
        total_amount = Decimal("0")

        for _ix, item_d in enumerate(data.items):
            product = db.query(Product).filter(
                Product.id == item_d.product_id,
                Product.company_id == current_user.company_id,
                Product.is_deleted == False,
            ).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Mahsulot ID={item_d.product_id} topilmadi")

            _unit_ctx = _unit_ctxs.get(_ix)
            if _unit_ctx is not None and final_status == SaleStatus.pending:
                raise HTTPException(status_code=400, detail="Kutilayotgan sotuvda qadoq birligi qo'llanmaydi — miqdorni asosiy birlikda kiriting")
            _price_item = _unit_ctx["price_item"] if _unit_ctx is not None else item_d
            _line_qty = _price_item.quantity

            _customer_price = None
            _customer = None
            if new_customer_id:
                _customer_price = db.query(CustomerPrice).filter(
                    CustomerPrice.customer_id == new_customer_id,
                    CustomerPrice.product_id == item_d.product_id,
                ).first()
                _customer = db.query(Customer).filter(
                    Customer.id == new_customer_id,
                    Customer.company_id == sale.company_id,
                ).first()

            unit_price, discount, _price_src = resolve_item_pricing(
                _price_item, product, _customer_price, _customer, current_user,
                branch_price=_pricing_ctx.branch_price(item_d.product_id, getattr(item_d, "variant_id", None)))
            _unit_level_price = None
            if _unit_ctx is not None:
                # CD.1 (create_sale bilan bir xil): oddiy ro'yxat narxi — birlik narxi / nisbat; jami tiyingacha aniq
                if _price_src == "sale_price":
                    unit_price = _unit_ctx["unit_list_price"] / _unit_ctx["ratio"]
                    _unit_level_price = Decimal(str(_unit_ctx["unit_list_price"]))
                    if Decimal(str(getattr(item_d, "discount", 0) or 0)) == 0 and _customer is not None and \
                            Decimal(str(getattr(_customer, "discount_percent", 0) or 0)) > 0:
                        discount = (unit_price * _line_qty * Decimal(str(_customer.discount_percent)) / Decimal("100")).quantize(Decimal("0.01"))
                elif _unit_ctx["price_overridden"]:
                    _unit_level_price = Decimal(str(item_d.unit_price))
                else:
                    _unit_level_price = (unit_price * _unit_ctx["ratio"]).quantize(Decimal("0.0001"))
            discount, _promo_id, _promo_disc = _pricing_ctx.apply(_price_item, unit_price, discount)
            if _unit_ctx is not None:
                _line_gross = (_unit_level_price * _unit_ctx["unit_qty"]).quantize(Decimal("0.01"))
            else:
                _line_gross = unit_price * _line_qty
            if discount > _line_gross:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{product.name}' uchun chegirma ({discount}) narxdan oshib ketdi",
                )
            subtotal = _line_gross - discount
            if _unit_ctx is not None:
                subtotal = subtotal.quantize(Decimal("0.01"))
            
            item_currency_code = getattr(item_d, "currency_code", "UZS")
            item_exchange_rate = getattr(item_d, "exchange_rate", Decimal("1.0"))

            conversion = db.query(ProductConversion).filter(
                ProductConversion.sell_product_id == product.id
            ).first()
            cost_price = product.cost_price
            source = None
            if conversion:
                source = db.query(Product).filter(Product.id == conversion.source_product_id).first()
                if source:
                    cost_price = (source.cost_price or Decimal("0")) * conversion.ratio

            # Sotuv "completed" ga o'tayotgan bo'lsa markirovka to'liq skanerlanganini
            # tekshiramiz — pending (qoralama) holatda hali majburiy emas.
            if final_status != SaleStatus.pending:
                marking_codes = _resolve_marking_codes(product, item_d, _unit_ctx)
            else:
                marking_codes = [c for c in (getattr(item_d, "marking_codes", None) or []) if c and c.strip()]

            # Variant shu mahsulotga tegishli bo'lishi shart (T0.30)
            variant_id = getattr(item_d, "variant_id", None)
            if variant_id is not None:
                from app.models.product_variant import ProductVariant
                _variant = db.query(ProductVariant.id).filter(
                    ProductVariant.id == variant_id,
                    ProductVariant.product_id == product.id,
                ).first()
                if not _variant:
                    raise HTTPException(status_code=404, detail=f"'{product.name}' uchun variant topilmadi")

            sale_items_data.append({
                "product": product,
                "variant_id": variant_id,
                "quantity": _line_qty,   # CD.1: unit_id bo'lsa asosiy birlikda
                "unit_price": unit_price,
                "cost_price": cost_price,
                "discount": discount,
                "subtotal": subtotal,
                "currency_code": item_currency_code,
                "exchange_rate": item_exchange_rate,
                "item_warehouse_id": getattr(item_d, "warehouse_id", None),
                "marking_codes": marking_codes,
                "promotion_id": _promo_id,
                "promotion_discount": _promo_disc,
                "conversion": conversion if source is not None else None,
                "source_product": source,
                "unit_ctx": _unit_ctx,
                "unit_level_price": _unit_level_price,
                "marking_open_box": _is_open_box_line(_unit_ctx) and bool(product.requires_marking),
            })
            total_amount += (subtotal * item_exchange_rate)

        total_amount = max(Decimal("0"), total_amount - disc_amount)
        paid_amount = data.paid_amount if data.paid_amount is not None else old_paid_amount
        paid_cash = data.paid_cash if data.paid_cash is not None else old_paid_cash
        paid_card = data.paid_card if data.paid_card is not None else old_paid_card

        # CD.1: dorixona — retsept tekshiruvi (kutilayotgandan tasdiqlashda yoki so'rovda retsept berilganda) va markirovka
        # kodlari (eski kodlar yuqorida in_stock ga qaytarilgan); yozishdan OLDIN, xatoda 400
        _rx_rows, _mk_plan = [], {}
        if _ph_ctx[0] and final_status != SaleStatus.pending:
            _wants_rx = _old_status == SaleStatus.pending or bool(data.prescriptions) or bool(data.rx_override_reason)
            if _wants_rx:
                _rx_rows, _ = _prepare_prescriptions(
                    db, data, sale_items_data, sale.company_id, _ph_ctx, tashkent_today(),
                )
            from app.routers.pharmacy_marking import plan_sale_marking
            _mk_plan = plan_sale_marking(db, sale.company_id, [
                (_i, _d["product"], _d.get("source_product"), [] if _d.get("marking_open_box") else _d["marking_codes"])
                for _i, _d in enumerate(sale_items_data)
            ])
        _new_items = []
        _unit_rows = []

        for sid in sale_items_data:
            item_wh = sid.get("item_warehouse_id") or wh_id
            new_item = SaleItem(
                sale_id=sale.id,
                product_id=sid["product"].id,
                variant_id=sid.get("variant_id"),
                quantity=sid["quantity"],
                unit_price=sid["unit_price"],
                cost_price=sid["cost_price"],
                discount=sid["discount"],
                subtotal=sid["subtotal"],
                currency_code=sid["currency_code"],
                exchange_rate=sid["exchange_rate"],
                warehouse_id=item_wh,
                unit=sid["product"].unit or "dona",
                marking_codes=sid["marking_codes"] or None,
                promotion_id=sid.get("promotion_id"),
                promotion_discount=sid.get("promotion_discount"),
            )
            db.add(new_item)
            _new_items.append(new_item)
            if final_status != SaleStatus.pending:
                # Variant, qator ombori, partiya (FIFO) va SaleItemBatch — create_sale bilan bir xil
                db.flush()
                deduct_sale_item(
                    db, sale, new_item, current_user, allow_negative_stock,
                    reason=f"Sotuv tahrirlash (sale #{sale_id})", pharmacy_ctx=_ph_ctx,
                )
            if sid.get("unit_ctx") is not None:
                _unit_rows.append((new_item, sid["unit_ctx"], sid.get("unit_level_price")))

        db.flush()
        # CD.1: qaysi birlikda sotilgani (D2.4), kodlar sold (D3.2), retseptlar (D2.5)
        for _ni, _uc, _base_price in _unit_rows:
            db.add(SaleItemUnit(
                sale_item_id=_ni.id, company_id=sale.company_id, unit_id=_uc["unit"].id,
                unit_name=_uc["unit"].name, unit_ratio=_uc["ratio"], unit_qty=_uc["unit_qty"],
                unit_price=(Decimal(str(_base_price)).quantize(Decimal("0.0001")) if _base_price is not None else None),
            ))
        if _mk_plan:
            from app.routers.pharmacy_marking import apply_sale_marking
            apply_sale_marking(_mk_plan, {_i: _ni.id for _i, _ni in enumerate(_new_items)})
        if _rx_rows:
            db.query(SalePrescription).filter(SalePrescription.sale_id == sale.id).delete(synchronize_session=False)
            _by_pid = {}
            for _ni in _new_items:
                _by_pid.setdefault(_ni.product_id, _ni.id)
            _write_prescriptions(db, sale, _rx_rows, _by_pid)

        if new_customer_id and final_status != SaleStatus.pending:
            # T0.26: mijoz qatori qulflanadi; yangi mijozga o'tishda arxivlangan mijoz — 400,
            # sotuvdagi mavjud mijoz arxivlangan bo'lsa ham tahrir davom etadi
            # mijoz o'zgarmagan bo'lsa (frontend tahrirda customer_id ni qayta yuboradi) arxivlangan bo'lsa ham o'tadi
            new_customer = lock_customer(
                db, new_customer_id, sale.company_id,
                allow_inactive=(data.customer_id is None or new_customer_id == sale.customer_id), required=False,
            )
            if not new_customer:
                if data.customer_id is not None:
                    raise HTTPException(status_code=404, detail="Mijoz topilmadi")
                raise HTTPException(status_code=409, detail="Sotuvdagi mijoz boshqa korxonaga tegishli")
            if new_customer:
                _rules = get_loyalty_rules(db, sale.company_id, branch_id=sale.branch_id)
                _redeem_total = Decimal("0")
                if (_old_pc > 0 or _old_pts > 0) and _old_customer_id == new_customer.id:
                    if _old_pts > int(new_customer.loyalty_points or 0):
                        raise HTTPException(status_code=400, detail="Mijozda yetarli loyallik ballari yo'q")
                    _avail_bonus = new_customer.bonus_balance or Decimal("0")
                    if _old_pc > _avail_bonus:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Bonus hisobida yetarli mablag' yo'q. Mavjud: {_avail_bonus:.0f}, so'ralgan: {_old_pc:.0f}",
                        )
                    _redeem_total = _old_pc + Decimal(_old_pts) * _rules.point_value
                    if _redeem_total > total_amount + Decimal("0.01"):
                        raise HTTPException(
                            status_code=400,
                            detail="Ishlatilgan keshbek/ball summasi yangi jami summadan oshib ketdi",
                        )
                    new_customer.bonus_balance = _avail_bonus - _old_pc  # type: ignore
                    new_customer.loyalty_points = int(new_customer.loyalty_points or 0) - _old_pts  # type: ignore
                    total_amount = max(Decimal("0"), total_amount - _redeem_total)
                    sale.paid_cashback = _old_pc  # type: ignore
                    sale.loyalty_points_used = _old_pts  # type: ignore
                else:
                    sale.paid_cashback = Decimal("0")  # type: ignore
                    sale.loyalty_points_used = 0  # type: ignore
                new_debt_uzs = max(Decimal("0"), total_amount - paid_amount)
                if new_debt_uzs > Decimal("0.01"):
                    # Kredit limit (T2.12): to'liq tahrirda ham majburlanadi (sotuvning eski qarzi yuqorida qaytarilgan)
                    check_credit_limit(db, new_customer, new_debt_uzs)
                    new_customer.debt_balance = (new_customer.debt_balance or Decimal("0")) + new_debt_uzs  # type: ignore

                    # Sync with multi-currency debt_balances
                    if not new_customer.debt_balances:
                        new_customer.debt_balances = {}  # type: ignore
                    
                    final_debts = {}
                    if hasattr(data, "currency_totals") and data.currency_totals:
                        final_debts = {k: Decimal(str(v)) for k, v in data.currency_totals.items()}
                    else:
                        currency_rates = {"UZS": Decimal("1.0")}
                        remain = {}
                        for sid in sale_items_data:
                            curr = sid["currency_code"]
                            currency_rates[curr] = sid.get("exchange_rate", Decimal("1.0"))
                            remain[curr] = remain.get(curr, Decimal("0")) + sid["subtotal"]
                        
                        if getattr(data, "payments", None):
                            for p in data.payments:
                                if getattr(p, "currency", None):
                                    currency_rates[p.currency] = getattr(p, "rate", Decimal("1.0")) or Decimal("1.0")
                                if p.type.value not in ("debt", "cashback"):
                                    p_curr = getattr(p, "currency", "UZS") or "UZS"
                                    remain[p_curr] = remain.get(p_curr, Decimal("0")) - p.amount

                        if sale.currency_id:
                            from app.models.currency import Currency
                            curr_obj = db.query(Currency).filter(Currency.id == sale.currency_id).first()
                            if curr_obj:
                                currency_rates[curr_obj.code] = sale.exchange_rate or Decimal("1")

                        if disc_amount > 0:
                            remain["UZS"] = remain.get("UZS", Decimal("0")) - disc_amount
                        if _redeem_total > 0:
                            remain["UZS"] = remain.get("UZS", Decimal("0")) - _redeem_total

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

                    for curr_code, curr_debt in final_debts.items():
                        curr_val = float(new_customer.debt_balances.get(curr_code, 0))
                        new_customer.debt_balances[curr_code] = curr_val + float(curr_debt)

                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(new_customer, "debt_balances")
                    sale.debt_amounts = {c: float(amt) for c, amt in final_debts.items()}

                # Keshbek/ball/total_spent — bitta marta, snapshot sotuvga yoziladi (T2.12)
                apply_sale_loyalty(new_customer, sale, total_amount, _rules, paid_uzs=paid_amount)
        else:
            # Mijoz yo'q yoki sotuv kutilayotgan holatda: teskari hisobda qaytgan sarf sotuvdan olib tashlanadi
            sale.paid_cashback = Decimal("0")  # type: ignore
            sale.loyalty_points_used = 0  # type: ignore

        if final_status != SaleStatus.pending:
            # To'lovlar: SalePayment, Transaction (T0.29 qoidasi), KassaMovement va Wallet.balance —
            # create_sale bilan bir xil; hamyon: avval teskari qilingan asl hamyon, bo'lmasa kassirniki
            # T1.9: tranzaksiya filiali — sotuv filiali (tahrir qiluvchi xodim filiali emas)
            tx_branch_id = resolve_txn_branch(db, current_user, sale=sale, warehouse_id=wh_id)
            if sale.branch_id is None:
                sale.branch_id = tx_branch_id
            _sale_currency_code = "UZS"
            if sale.currency_id:
                from app.models.currency import Currency as _Cur
                _cur_obj = db.query(_Cur).filter(_Cur.id == sale.currency_id).first()
                if _cur_obj:
                    _sale_currency_code = _cur_obj.code
            _pay_src = SimpleNamespace(
                payments=data.payments, paid_amount=paid_amount, payment_type=payment_type,
                paid_cash=paid_cash, paid_card=paid_card,
            )
            post_sale_payments(
                db, sale, build_sale_payment_entries(_pay_src, _sale_currency_code), current_user,
                wallet_id=_reversed_wallet_ids[0] if _reversed_wallet_ids else None,
                tx_branch_id=tx_branch_id, created_at=sale.created_at,
                desc_prefix="Sotuv tahrirlash",
            )

        if _old_status == SaleStatus.pending and final_status == SaleStatus.completed:
            _cur_shift = db.query(Shift).filter(
                Shift.cashier_id == current_user.id,
                Shift.status == "open",
                Shift.company_id == current_user.company_id,
            ).first()
            if _cur_shift:
                sale.shift_id = _cur_shift.id
            log_action(
                db=db, action="SALE_CONFIRMED", entity_type="sale", entity_id=sale.id,
                user_id=current_user.id,
                new_values={"number": sale.number, "status": "completed", "total": str(total_amount), "paid": str(paid_amount)},
            )

        sale.status = final_status
        sale.total_amount = total_amount  # type: ignore
        sale.discount_amount = disc_amount  # type: ignore
        sale.paid_amount = paid_amount  # type: ignore
        sale.paid_cash = paid_cash  # type: ignore
        sale.paid_card = paid_card  # type: ignore
        sale.payment_type = payment_type
        sale.customer_id = new_customer_id
        sale.warehouse_id = wh_id
        if data.note is not None:
            sale.note = data.note
        if data.debt_due_date is not None:
            sale.debt_due_date = data.debt_due_date
        
        # Currency update
        if hasattr(data, "currency_id") and data.currency_id is not None:
            sale.currency_id = data.currency_id
        
        # Resolve overall exchange rate from first item if possible (as a fallback)
        if sale_items_data:
            # We already accumulated total_amount in UZS by multiplying with item_exchange_rate
            # It's good to keep an exchange rate on the Sale object for display
            first_item = sale_items_data[0]
            if first_item.get("currency_code") != "UZS":
                sale.exchange_rate = first_item.get("exchange_rate", sale.exchange_rate)
        
        if hasattr(data, "currency_code") and data.currency_code is not None:
            sale.currency_code = data.currency_code

    else:
        # ── Oddiy yangilash: holat/izoh/to'lov ───────────────────────────────
        old_status = sale.status
        new_status = data.status if data.status is not None else old_status
        # pending -> completed: qoldiq yechiladi, qarz qo'shiladi, to'lov kassaga tushadi.
        # pending -> cancelled: faqat holat (rad etilgan buyurtma uchun qoldiq/qarz yo'q).
        # completed -> pending: qoldiq/partiya nisbiy qaytadi. completed -> cancelled: to'liq teskari.
        confirming = old_status == SaleStatus.pending and new_status not in (SaleStatus.pending, SaleStatus.cancelled)
        unconfirming = old_status == SaleStatus.completed and new_status == SaleStatus.pending
        cancelling_completed = old_status == SaleStatus.completed and new_status == SaleStatus.cancelled

        # D1.2: dorixona rejimida pending -> completed (qoldiq shu yerda yechiladigan holat): yaroqli partiyalar
        # yetarliligi mijoz qarzi/to'lov yozuvlaridan OLDIN tekshiriladi. `pharmacy_context` bir marta.
        _ph_ctx = (False, {})
        _confirm_items, _confirm_rx, _confirm_mk = [], [], {}
        if confirming:
            _ph_ctx = pharmacy_context(db, sale.company_id)
            _ph_stage = getattr(_neg_company, "stock_deduct_stage", "order_confirmed") or "order_confirmed"
            if _ph_ctx[0] and not (getattr(sale, "delivery", None) is not None and _ph_stage in ("loaded", "delivered")):
                _pending_items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()
                _pharmacy_check_lines(db, sale, [
                    (it.product, it.variant_id, it.warehouse_id, it.quantity) for it in _pending_items
                ], _ph_ctx)
            if _ph_ctx[0]:
                # CD.1: dorixona — retsept tekshiruvi va markirovka kodlari (yozishdan OLDIN; xatoda 400)
                _confirm_items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).order_by(SaleItem.id).all()
                _confirm_rx, _confirm_mk = _confirm_rx_and_marking(db, sale, data, _ph_ctx, _confirm_items)

        _paid_delta = Decimal("0")
        if data.paid_amount is not None:
            _paid_delta = Decimal(str(data.paid_amount)) - Decimal(str(sale.paid_amount or 0))
            if _paid_delta < Decimal("-0.01"):
                raise HTTPException(
                    status_code=400,
                    detail="To'lovni kamaytirish uchun sotuvni tahrirlash oynasidan foydalaning",
                )

        # Qulf tartibi: mijoz -> qoldiq -> hamyon (to'liq teskari uchun mijoz avval qulflanadi)
        _cancel_customer = None
        if cancelling_completed and sale.customer_id:
            _cancel_customer = lock_customer(db, sale.customer_id, sale.company_id, allow_inactive=True, required=False)

        if data.status is not None:
            sale.status = data.status
        if data.note is not None:
            sale.note = data.note
        if data.paid_amount is not None:
            if sale.customer_id and not cancelling_completed:
                # T0.26: qarz o'zgaradi — mijoz qatori qulflanadi (arxivlangan mijoz sotuvi ham yopilishi mumkin)
                customer = lock_customer(db, sale.customer_id, sale.company_id, allow_inactive=True, required=False)
                if not customer:
                    raise HTTPException(status_code=409, detail="Sotuvdagi mijoz boshqa korxonaga tegishli")
                if customer:
                    old_debt = (sale.total_amount - sale.paid_amount) * (sale.exchange_rate or Decimal("1"))
                    new_debt = (sale.total_amount - data.paid_amount) * (sale.exchange_rate or Decimal("1"))
                    if confirming:
                        if new_debt > 0:
                            check_credit_limit(db, customer, new_debt)  # T2.12: yakunlashda kredit limit majburlanadi
                            customer.debt_balance = (customer.debt_balance or Decimal("0")) + new_debt
                            
                            # Sync JSON
                            if not customer.debt_balances: customer.debt_balances = {}  # type: ignore
                            
                            sale_currency = "UZS"
                            if sale.currency_id:
                                from app.models.currency import Currency
                                curr_obj = db.query(Currency).filter(Currency.id == sale.currency_id).first()
                                if curr_obj:
                                    sale_currency = curr_obj.code
                                    
                            curr_val = float(customer.debt_balances.get(sale_currency, 0))
                            raw_new_debt = sale.total_amount - data.paid_amount
                            customer.debt_balances[sale_currency] = curr_val + float(raw_new_debt)
                            from sqlalchemy.orm.attributes import flag_modified
                            flag_modified(customer, "debt_balances")
                        _earn_on_confirm(db, sale, customer, data.paid_amount)

                    elif unconfirming:
                        if old_debt > 0:
                            customer.debt_balance = max(Decimal("0"), customer.debt_balance - old_debt)  # type: ignore

                            # Sync JSON
                            if customer.debt_balances:
                                sale_currency = "UZS"
                                if sale.currency_id:
                                    from app.models.currency import Currency
                                    curr_obj = db.query(Currency).filter(Currency.id == sale.currency_id).first()
                                    if curr_obj:
                                        sale_currency = curr_obj.code
                                        
                                if sale_currency in customer.debt_balances:
                                    curr_val = float(customer.debt_balances.get(sale_currency, 0))
                                    raw_old_debt = sale.total_amount - sale.paid_amount
                                    customer.debt_balances[sale_currency] = max(0.0, curr_val - float(raw_old_debt))
                                    from sqlalchemy.orm.attributes import flag_modified
                                    flag_modified(customer, "debt_balances")

                    elif old_status != SaleStatus.pending and new_status not in (SaleStatus.pending, SaleStatus.cancelled):
                        diff = new_debt - old_debt
                        customer.debt_balance = max(Decimal("0"), customer.debt_balance + diff)  # type: ignore

                        # Sync JSON
                        if not customer.debt_balances: customer.debt_balances = {}  # type: ignore
                        
                        sale_currency = "UZS"
                        if sale.currency_id:
                            from app.models.currency import Currency
                            curr_obj = db.query(Currency).filter(Currency.id == sale.currency_id).first()
                            if curr_obj:
                                sale_currency = curr_obj.code
                                
                        curr_val = float(customer.debt_balances.get(sale_currency, 0))
                        raw_diff = (sale.total_amount - data.paid_amount) - (sale.total_amount - sale.paid_amount)
                        customer.debt_balances[sale_currency] = max(0.0, curr_val + float(raw_diff))
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(customer, "debt_balances")

            sale.paid_amount = data.paid_amount

        if data.paid_amount is None and confirming:
            if sale.customer_id:
                customer = db.query(Customer).filter(
                    Customer.id == sale.customer_id,
                    Customer.company_id == sale.company_id,
                ).with_for_update().first()
                if not customer:
                    raise HTTPException(status_code=409, detail="Sotuvdagi mijoz boshqa korxonaga tegishli")
                if customer:
                    remaining_debt = (sale.total_amount - sale.paid_amount) * (sale.exchange_rate or Decimal("1"))
                    if remaining_debt > 0:
                        check_credit_limit(db, customer, remaining_debt)  # T2.12
                        customer.debt_balance = (customer.debt_balance or Decimal("0")) + remaining_debt  # type: ignore

                        # Sync JSON
                        if not customer.debt_balances: customer.debt_balances = {}  # type: ignore
                        
                        sale_currency = "UZS"
                        if sale.currency_id:
                            from app.models.currency import Currency
                            curr_obj = db.query(Currency).filter(Currency.id == sale.currency_id).first()
                            if curr_obj:
                                sale_currency = curr_obj.code
                                
                        curr_val = float(customer.debt_balances.get(sale_currency, 0))
                        raw_remaining = sale.total_amount - sale.paid_amount
                        customer.debt_balances[sale_currency] = curr_val + float(raw_remaining)  # type: ignore
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(customer, "debt_balances")
                    _earn_on_confirm(db, sale, customer, sale.paid_amount)

        if unconfirming and sale.customer_id:
            # T2.12: qayta yakunlanganda ikki marta yig'ilmasligi uchun yig'ilgan keshbek/ball/total_spent qaytariladi
            # (sarflangan keshbek/ball sotuvga "band qilingan" holda qoladi)
            _unc_customer = lock_customer(db, sale.customer_id, sale.company_id, allow_inactive=True, required=False)
            if _unc_customer is not None:
                reverse_sale_loyalty(_unc_customer, sale, include_redeemed=False)
                clear_sale_loyalty(sale)

        # Qoldiq yechish bosqichi (kompaniya `stock_deduct_stage`): yetkazmali sotuvda 'loaded' yoki
        # 'delivered' bosqichida qoldiq tasdiqlashda emas, ombordan yuklanganda / mijozga topshirilganda
        # chiqadi (sale_delivery_service.handle_delivery_stage_stock)
        _delivery = getattr(sale, "delivery", None)
        _has_delivery = _delivery is not None
        if confirming:
            if _confirm_mk:
                from app.routers.pharmacy_marking import apply_sale_marking
                apply_sale_marking(_confirm_mk, {_i: _it.id for _i, _it in enumerate(_confirm_items)})   # CD.1: kodlar sold
            if _confirm_rx:
                _by_pid = {}
                for _it in _confirm_items:
                    _by_pid.setdefault(_it.product_id, _it.id)
                _write_prescriptions(db, sale, _confirm_rx, _by_pid)
            from app.models.company import Company
            _comp = db.query(Company).filter(Company.id == sale.company_id).first()
            _stage = getattr(_comp, "stock_deduct_stage", "order_confirmed") or "order_confirmed"
            _deduct_now = not (_has_delivery and _stage in ("loaded", "delivered"))
            if _deduct_now:
                # Har qator o'z ombori va varianti bo'yicha; partiya (FIFO) va SaleItemBatch ham yoziladi
                for item in db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all():
                    deduct_sale_item(
                        db, sale, item, current_user, allow_negative_stock,
                        reason=f"Sotuv tasdiqlandi (sale #{sale.id})", pharmacy_ctx=_ph_ctx,
                    )
                if _has_delivery:
                    _delivery.stock_deducted = True
        elif unconfirming:
            # Tasdiqlashda qoldiq chiqqan bo'lsa (sotuv harakatlari bor) yetkazma belgisi ham tiklanadi
            from app.models.inventory import StockMovement as _SM
            _had_sale_stock = db.query(_SM.id).filter(
                _SM.reference_type == "sale", _SM.reference_id == sale.id,
            ).first() is not None
            # Nisbiy qaytarish (absolyut qty_before emas — oradagi boshqa sotuvlar saqlanadi)
            restore_sale_stock(db, sale)
            restore_sale_batches(db, sale)
            if pharmacy_context(db, sale.company_id)[0]:
                _release_sale_marking(db, sale)   # CD.1: kodlar omborga qaytadi
            if _has_delivery and _had_sale_stock:
                _delivery.stock_deducted = False
        elif cancelling_completed:
            # To'liq teskari: qoldiq, partiya, mijoz qarzi/loyalligi, Transaction va kassa
            cancel_sale_effects(db, sale, current_user, _cancel_customer)
            if pharmacy_context(db, sale.company_id)[0]:
                _release_sale_marking(db, sale)   # CD.1: bekor qilingan sotuv kodlari omborga qaytadi

        # To'lov oshgan bo'lsa (masalan buyurtma to'lov bilan tasdiqlandi) — kassaga tushadi:
        # SalePayment, Transaction va KassaMovement (smena ham, kassa X-hisoboti ham ko'radi)
        if _paid_delta > Decimal("0.01") and new_status not in (SaleStatus.pending, SaleStatus.cancelled):
            from app.models.moliya import NON_CASH_PAYMENT_TYPES as _NON_CASH
            _ptype = getattr(sale.payment_type, "value", sale.payment_type) or "cash"
            if _ptype in _NON_CASH:
                _ptype = "cash"
            _sale_currency_code = "UZS"
            if sale.currency_id:
                from app.models.currency import Currency as _Cur
                _cur_obj = db.query(_Cur).filter(_Cur.id == sale.currency_id).first()
                if _cur_obj:
                    _sale_currency_code = _cur_obj.code
            post_sale_payments(
                db, sale,
                [{"type": _ptype, "amount": _paid_delta, "rate": Decimal("1"),
                  "currency": _sale_currency_code, "km_currency": _sale_currency_code, "label": None}],
                current_user, tx_branch_id=resolve_txn_branch(db, current_user, sale=sale),
            )

    if getattr(data, "customer_id", None) is not None and data.customer_id != sale.customer_id:
        reassign_sale_customer(db=db, sale_id=sale.id, new_customer_id=data.customer_id, current_user=current_user, commit=False)

    if getattr(data, "delivery", None) is not None:
        from app.services.sale_delivery_service import upsert_sale_delivery
        upsert_sale_delivery(db, sale, data.delivery, sale.company_id)
    if str(getattr(sale.status, "value", sale.status)) in ("cancelled", "refunded"):
        from app.services.sale_delivery_service import cancel_sale_delivery
        cancel_sale_delivery(db, sale.id, "Sotuv bekor qilindi")
    # Agent buyurtmasi omborda tasdiqlandi/bekor qilindi — agentga push
    if getattr(sale, "agent_id", None) and _old_status == SaleStatus.pending and sale.status != SaleStatus.pending:
        from app.services.mobile_service import push_to_user
        ok = sale.status == SaleStatus.completed
        push_to_user(db, sale.agent_id, "✅ Buyurtma tasdiqlandi" if ok else "❌ Buyurtma bekor qilindi",
                     f"#{sale.number} — {sale.customer.name if sale.customer else ''}", {"type": "order", "sale_id": sale.id})

    log_action(
        db=db, action="SALE_UPDATE", entity_type="sale", entity_id=sale.id,  # type: ignore
        user_id=current_user.id,  # type: ignore
        new_values={"status": str(sale.status), "paid": str(sale.paid_amount)},
    )
    db.commit()
    return sale


def reassign_sale_customer(db: Session, sale_id: int, new_customer_id: int, current_user: User, commit: bool = True) -> Sale:
    """Sotuvga boshqa mijozni biriktirish yoki o'zgartirish.
    Sotuv sanasi, raqami va tarkibi o'zgarmaydi.
    Qarz balansi eski mijozdan (agar bo'lsa) yangi mijozga ko'chiriladi.
    """
    q = db.query(Sale).filter(Sale.id == sale_id)
    if current_user.role != UserRole.super_admin:
        q = q.filter(Sale.company_id == current_user.company_id)
    q = apply_sale_branch_filter(q, db, current_user)
    sale = q.first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")

    if sale.customer_id == new_customer_id:
        # Mijoz o'zgarmaydi — faqat mavjudligi tekshiriladi (qulf va arxiv tekshiruvi shart emas)
        exists = db.query(Customer.id).filter(
            Customer.id == new_customer_id,
            Customer.company_id == sale.company_id,
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
        return sale

    # T0.26: qarz/xarajat ko'chadi — ikkala mijoz ham qulflanadi (id o'sish tartibida, deadlock bo'lmasin);
    # yangi mijoz arxivlangan bo'lsa 400, eski mijoz arxivlangan bo'lsa ham qarzi kamayadi
    old_customer_id = sale.customer_id
    old_customer = None
    if old_customer_id and old_customer_id < new_customer_id:
        old_customer = lock_customer(db, old_customer_id, sale.company_id, allow_inactive=True, required=False)
    new_customer = lock_customer(db, new_customer_id, sale.company_id)
    if old_customer_id and old_customer_id > new_customer_id:
        old_customer = lock_customer(db, old_customer_id, sale.company_id, allow_inactive=True, required=False)

    raw_debt = max(Decimal("0"), Decimal(str(sale.total_amount or 0)) - Decimal(str(sale.paid_amount or 0)))
    exr = Decimal(str(sale.exchange_rate or 1))

    sale_currency = "UZS"
    if sale.currency_id:
        from app.models.currency import Currency
        curr_obj = db.query(Currency).filter(Currency.id == sale.currency_id).first()
        if curr_obj:
            sale_currency = curr_obj.code
    elif getattr(sale, "currency_code", None):
        sale_currency = sale.currency_code

    import json
    def _parse_dict(v):
        if isinstance(v, dict):
            return dict(v)
        if isinstance(v, str) and v.strip():
            try:
                res = json.loads(v)
                return res if isinstance(res, dict) else {}
            except Exception:
                return {}
        return {}

    from sqlalchemy.orm.attributes import flag_modified

    if str(getattr(sale.status, "value", sale.status)) != "pending":
        debt_amounts = _parse_dict(getattr(sale, 'debt_amounts', None))
        if debt_amounts:
            for curr_code, amt in debt_amounts.items():
                amt_d = Decimal(str(amt))
                amt_uzs = amt_d * (Decimal("1") if curr_code == "UZS" else exr)
                if old_customer:
                    old_b = _parse_dict(old_customer.debt_balances)
                    curr_val = Decimal(str(old_b.get(curr_code, 0)))
                    old_b[curr_code] = float(max(Decimal("0"), curr_val - amt_d))
                    old_customer.debt_balances = old_b
                    old_customer.debt_balance = max(Decimal("0"), (old_customer.debt_balance or Decimal("0")) - amt_uzs)

                new_b = _parse_dict(new_customer.debt_balances)
                new_curr_val = Decimal(str(new_b.get(curr_code, 0)))
                new_b[curr_code] = float(new_curr_val + amt_d)
                new_customer.debt_balances = new_b
                new_customer.debt_balance = (new_customer.debt_balance or Decimal("0")) + amt_uzs

            if old_customer:
                flag_modified(old_customer, "debt_balances")
            flag_modified(new_customer, "debt_balances")
        else:
            debt_uzs = raw_debt * exr
            if raw_debt > Decimal("0"):
                if old_customer:
                    old_customer.debt_balance = max(Decimal("0"), (old_customer.debt_balance or Decimal("0")) - debt_uzs)
                    old_b = _parse_dict(old_customer.debt_balances)
                    curr_val = Decimal(str(old_b.get(sale_currency, 0)))
                    old_b[sale_currency] = float(max(Decimal("0"), curr_val - raw_debt))
                    old_customer.debt_balances = old_b
                    flag_modified(old_customer, "debt_balances")

                new_customer.debt_balance = (new_customer.debt_balance or Decimal("0")) + debt_uzs
                new_b = _parse_dict(new_customer.debt_balances)
                curr_val = Decimal(str(new_b.get(sale_currency, 0)))
                new_b[sale_currency] = float(curr_val + raw_debt)
                new_customer.debt_balances = new_b
                flag_modified(new_customer, "debt_balances")
                sale.debt_amounts = {sale_currency: float(raw_debt)}

        if sale.total_amount:
            spent_uzs = Decimal(str(sale.total_amount)) * exr
            if old_customer:
                old_customer.total_spent = max(Decimal("0"), (old_customer.total_spent or Decimal("0")) - spent_uzs)
            new_customer.total_spent = (new_customer.total_spent or Decimal("0")) + spent_uzs

    sale.customer_id = new_customer.id

    if commit:
        log_action(
            db=db, action="SALE_ASSIGN_CUSTOMER", entity_type="sale", entity_id=sale.id,  # type: ignore
            user_id=current_user.id,  # type: ignore
            new_values={"customer_id": new_customer.id, "customer_name": new_customer.name},
        )
        db.commit()
        db.refresh(sale)
    return sale
