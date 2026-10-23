from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.audit import log_action
from app.models.batch import Batch
from app.models.customer import Customer
from app.models.customer_prices import CustomerPrice
from app.models.currency import Currency
from app.models.moliya import Transaction, KassaMovement, Wallet, NON_CASH_PAYMENT_TYPES
from app.models.product import Product, ProductConversion
from app.models.sale import Sale, SaleItem, SaleItemBatch, SaleStatus, PaymentType
from app.models.user import User
from app.schemas.sale import SaleCreate
from app.services.inventory_service import receive_stock
from app.services import approval_service  # T4.6: qaytarish limiti va tasdiqlash
from app.services.sale_helpers import (
    generate_return_number, apply_sale_branch_filter, refresh_original_sale_status,
    validate_sale_warehouse,
)
from app.services.loyalty_service import (
    get_loyalty_rules, reverse_sale_loyalty, reverse_return_without_sale, returned_ratio,
)
from app.services.pharmacy import pharmacy_context  # D1.4: dorixona rejimida asl partiyaga qaytarish
from app.services.tenant_guards import find_tx_branch, get_company_variant
from app.services.wallet_resolver import resolve_wallet, NEGATIVE_BALANCE_WARNING


# ─── D1.4: dorixona rejimida qaytarish — asl partiyaga ───────────────────────

def _parse_return_expiry(value, product_name: str) -> Optional[datetime]:
    """So'rovdagi yaroqlilik muddatini (date / datetime / 'YYYY-MM-DD') Batch.expiry_date (DateTime) ga o'tkazadi."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    try:
        return datetime.combine(date.fromisoformat(str(value).strip()[:10]), time.min)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"'{product_name}': yaroqlilik muddati (expiry_date) noto'g'ri formatda (YYYY-MM-DD kerak)",
        )


def plan_pharmacy_batch_return(
    db: Session,
    sale_item: Optional[SaleItem],
    src_qty: Decimal,
    ratio: Decimal,
    used: dict,
    item_req,
    product,
) -> dict:
    """Dorixona rejimi: qaytgan `src_qty` (manba mahsulot birligida) qaysi partiyalarga yozilishini REJALAYDI
    (bazaga hech narsa yozmaydi — xato bo'lsa hech narsa o'zgarmasin).

    1) `SaleItemBatch` bo'yicha aynan sotilgan partiyalarga, oxirgi ajratilgandan boshlab. Oldingi qisman
       qaytarishlar ham oxiridan olingan deb hisoblanadi (`returned_quantity`), shuning uchun ustun kerak emas.
    2) Asl ajratma topilmasa yoki yetmasa (eski sotuv, sotuvsiz qaytarish): so'rovdagi `lot_number` va
       `expiry_date` majburiy (400), shu bilan yangi partiya ochiladi.
    Muddati o'tgan partiyaga ham shu partiyaning o'ziga yoziladi (sotilishini D1.2 to'sadi).
    `used` — bir so'rov ichida bir xil ajratmadan ikki marta olmaslik uchun ({sib.id: miqdor}).
    """
    remainder = Decimal(str(src_qty))
    allocs = []
    if sale_item is not None:
        sibs = (
            db.query(SaleItemBatch)
            .filter(SaleItemBatch.sale_item_id == sale_item.id)
            .order_by(SaleItemBatch.id.asc())
            .all()
        )
        prev = Decimal(str(sale_item.returned_quantity or 0)) * ratio
        for sib in reversed(sibs):
            sib_qty = Decimal(str(sib.quantity or 0))
            already = min(prev, sib_qty)
            prev -= already
            avail = sib_qty - already - used.get(sib.id, Decimal("0"))
            take = min(remainder, avail)
            if take <= 0:
                continue
            allocs.append((sib.batch_id, take))
            used[sib.id] = used.get(sib.id, Decimal("0")) + take
            remainder -= take

    new_batch = None
    if remainder > 0:
        lot = (getattr(item_req, "lot_number", None) or "").strip() if item_req is not None else ""
        expiry = _parse_return_expiry(getattr(item_req, "expiry_date", None), product.name) if item_req is not None else None
        if not lot or expiry is None:
            raise HTTPException(
                status_code=400,
                detail=f"'{product.name}': asl sotuv partiyasi topilmadi — qaytarish uchun seriya raqami "
                       f"(lot_number) va yaroqlilik muddati (expiry_date) majburiy",
            )
        new_batch = {"lot_number": lot[:100], "expiry_date": expiry, "quantity": remainder}
    return {"allocs": allocs, "new_batch": new_batch}


def apply_pharmacy_batch_return(
    db: Session, plan: dict, *, product_id: int, variant_id: Optional[int], warehouse_id: Optional[int],
    company_id: int, purchase_price,
) -> None:
    """`plan_pharmacy_batch_return` natijasini qo'llaydi: asl partiyalar qoldig'i oshadi, yetmagan qism uchun
    kiritilgan seriya/muddat bilan yangi partiya ochiladi (RETURN-<raqam> partiya ochilmaydi)."""
    for batch_id, qty in plan["allocs"]:
        batch = db.query(Batch).filter(Batch.id == batch_id).with_for_update().first()
        if batch is not None:
            batch.quantity = Decimal(str(batch.quantity or 0)) + qty
    nb = plan["new_batch"]
    if nb is not None:
        db.add(Batch(
            product_id=product_id, variant_id=variant_id, warehouse_id=warehouse_id,
            lot_number=nb["lot_number"], expiry_date=nb["expiry_date"],
            initial_quantity=nb["quantity"], quantity=nb["quantity"],
            purchase_price=purchase_price, company_id=company_id,
        ))
    db.flush()


def create_return_sale(
    db: Session,
    data: SaleCreate,
    current_user: User,
    ip: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Sale:
    # warehouse_id majburiy — bo'lmasa qaytarilgan tovar "hech kimga tegishli
    # bo'lmagan" NULL-warehouse StockLevel'ga tushib, real ombor balansida
    # ko'rinmay qoladi (inventarizatsiyada yo'qolib qoladi).
    if not data.warehouse_id:
        raise HTTPException(status_code=400, detail="Ombor tanlanmagan — qaytarish uchun ombor majburiy")
    # Ombor shu korxonaning faol ombori bo'lishi shart (T0.13); filial ruxsati joriy korxona bo'yicha
    # (T1.2: uc.branch_id ∪ user_branches), global users.branch_id bo'yicha emas
    validate_sale_warehouse(db, current_user, data.warehouse_id)
    # D1.4: dorixona moduli yoqilgan korxonada qaytgan tovar asl partiyaga qaytadi (oddiy do'konda o'zgarmaydi)
    pharmacy_on, _ph_settings = pharmacy_context(db, current_user.company_id)
    batch_used = {}
    marking_used = set()   # D3.2: bir so'rovda bir kod ikki marta qaytmasin

    # Asl sotuv (ixtiyoriy): shu korxonadan, xodimning filial ruxsati doirasida, qaytarilmagan
    original_sale = None
    original_items = []
    taken_qty = {}
    if data.original_sale_id:
        original_q = db.query(Sale).filter(
            Sale.id == data.original_sale_id, Sale.company_id == current_user.company_id,
        )
        original_sale = apply_sale_branch_filter(original_q, db, current_user).first()
        if not original_sale:
            raise HTTPException(status_code=404, detail="Asl sotuv topilmadi")
        if original_sale.status in (SaleStatus.refunded, SaleStatus.cancelled):
            raise HTTPException(status_code=400, detail="Bekor qilingan yoki to'liq qaytarilgan sotuvdan tovar qaytarib bo'lmaydi")
        original_items = db.query(SaleItem).filter(SaleItem.sale_id == original_sale.id).with_for_update().all()

    # Valyuta va kurs aniqlash
    currency = None
    exchange_rate = Decimal("1")
    if data.currency_id:
        currency = db.query(Currency).filter(Currency.id == data.currency_id).first()
        if currency:
            exchange_rate = Decimal(str(currency.rate or 1)) or Decimal("1")
    sale_currency = currency.code if currency else "UZS"

    # Jami (total_amount) sotuvdagi kabi UZS da yig'iladi: qator summasi
    # mahsulot valyutasida, UZS = subtotal * qator kursi (sale_create.py).
    total_amount = Decimal("0")
    sale_items_data = []

    for item_d in data.items:
        product = db.query(Product).filter(
            Product.id == item_d.product_id,
            Product.company_id == current_user.company_id,
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Mahsulot topilmadi: {item_d.product_id}")

        qty = Decimal(str(item_d.quantity))

        # Asl sotuv berilsa: narx va valyuta asl qatordan olinadi (mijoz yuborgan narx e'tiborsiz)
        original_item = None
        if original_sale is not None:
            candidates = [
                oi for oi in original_items
                if oi.product_id == item_d.product_id
                and (item_d.variant_id is None or oi.variant_id == item_d.variant_id)
            ]
            if not candidates:
                raise HTTPException(status_code=400, detail=f"'{product.name}' asl sotuvda mavjud emas")
            original_item = next(
                (oi for oi in candidates
                 if Decimal(str(oi.quantity)) - Decimal(str(oi.returned_quantity or 0))
                 - taken_qty.get(oi.id, Decimal("0")) >= qty),
                None,
            )
            if original_item is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{product.name}' qaytarish miqdori asl sotuvdagi qoldiqdan oshib ketdi",
                )
            taken_qty[original_item.id] = taken_qty.get(original_item.id, Decimal("0")) + qty
            variant_id = original_item.variant_id
        else:
            variant_id = item_d.variant_id
            if variant_id:
                get_company_variant(db, product.id, variant_id)

        _customer_price = None
        if data.customer_id and original_item is None:
            _customer_price = db.query(CustomerPrice).filter(
                CustomerPrice.customer_id == data.customer_id,
                CustomerPrice.product_id == item_d.product_id,
            ).first()

        if original_item is not None:
            # Asl qatorning haqiqiy to'langan birlik narxi (chegirma allaqachon hisobga olingan)
            price = Decimal(str(original_item.subtotal)) / Decimal(str(original_item.quantity))
            discount = Decimal("0")
            subtotal = price * qty
        else:
            price = (
                Decimal(str(item_d.unit_price)) if item_d.unit_price is not None
                else (Decimal(str(_customer_price.price)) if _customer_price else product.sale_price)
            )
            discount = Decimal(str(item_d.discount))
            # Chegirma — butun qator uchun (POS shunday yuboradi, sale_create.py ham shunday hisoblaydi)
            subtotal = max(Decimal("0"), price * qty - discount)
        # Mijoz qator valyutasini yubormagan bo'lsa — narx sotuv valyutasida deb olinadi
        if original_item is not None:
            item_currency = (original_item.currency_code or "UZS").upper()
            item_rate = Decimal(str(original_item.exchange_rate or 1)) or Decimal("1")
        elif "exchange_rate" in item_d.model_fields_set or "currency_code" in item_d.model_fields_set:
            item_currency = (item_d.currency_code or "UZS").upper()
            item_rate = Decimal(str(item_d.exchange_rate or 1)) or Decimal("1")
        else:
            item_currency = sale_currency
            item_rate = exchange_rate
        total_amount += subtotal * item_rate

        conversion = db.query(ProductConversion).filter(
            ProductConversion.sell_product_id == product.id
        ).first()
        cost_price = product.cost_price
        if conversion:
            source = db.query(Product).filter(Product.id == conversion.source_product_id).first()
            if source:
                cost_price = (source.cost_price or Decimal("0")) * conversion.ratio

        # D1.4: dorixona rejimida partiya rejasi (yozishdan oldin; seriya/muddat yetishmasa 400)
        batch_plan = None
        if pharmacy_on and getattr(product, "product_type", "stock") != "service":
            _is_virtual = getattr(product, "product_type", "stock") == "sell"
            if not (_is_virtual and not conversion):   # konversiyasiz virtual mahsulot pastda o'z xatosini beradi
                _ratio = Decimal(str(conversion.ratio)) if (_is_virtual and conversion) else Decimal("1")
                batch_plan = plan_pharmacy_batch_return(
                    db, original_item, qty * _ratio, _ratio, batch_used, item_d, product,
                )

        # D3.2: dorixona rejimida markirovkali dori kodlari (sold -> in_stock); modul o'chiq bo'lsa bo'sh
        marking_rows = []
        if pharmacy_on and product.requires_marking:
            from app.routers.pharmacy_marking import plan_return_marking
            marking_rows = plan_return_marking(
                db, current_user.company_id, product=product,
                source=db.get(Product, conversion.source_product_id) if conversion else None,
                original_item=original_item, codes=getattr(item_d, "marking_codes", None), qty=qty,
                used_ids=marking_used,
            )

        sale_items_data.append({
            "product": product,
            "variant_id": variant_id,
            "quantity": qty,
            "unit_price": price,
            "discount": discount,
            "subtotal": subtotal,
            "cost_price": cost_price,
            "currency_code": item_currency,
            "exchange_rate": item_rate,
            "batch_plan": batch_plan,
            "marking_rows": marking_rows,
        })

    total_amount = max(Decimal("0"), total_amount - data.discount_amount)
    total_in_sale_currency = total_amount / exchange_rate

    # T4.6: qaytarish summasi limiti (qoida yo'q korxonada o'zgarmaydi; admin/director ozod, faqat audit)
    _ref_branch = (original_sale.branch_id if original_sale is not None else None) \
        or find_tx_branch(db, current_user, warehouse_id=data.warehouse_id)
    _consumed_approval = approval_service.enforce(
        db, current_user, [v for v in [approval_service.evaluate_refund(db, current_user, total_amount, _ref_branch)] if v],
        payload=approval_service.return_payload(data), amount=total_amount, branch_id=_ref_branch,
        approval_id=getattr(data, "approval_id", None),
    )

    # Qaytarilayotgan summadan ortiq pul chiqarib bo'lmaydi
    if Decimal(str(data.paid_amount)) * exchange_rate > total_amount + Decimal("0.01"):
        raise HTTPException(status_code=400, detail="To'langan summa qaytarish summasidan oshmasligi kerak")

    # Qarz/keshbek bo'yicha qaytarishda haqiqiy pul chiqmaydi (aralash bundan mustasno:
    # u cash/card qismlarga bo'linadi) — Transaction, KassaMovement va wallet.balance o'zgarmaydi (T0.29).
    _real_cash_refund = (
        data.payment_type == PaymentType.mixed
        or data.payment_type.value not in NON_CASH_PAYMENT_TYPES
    )
    # Pul chiqadigan kassa hech narsa yozilishidan OLDIN aniqlanadi: topilmasa 400 (jim o'tkazilmaydi)
    refund_wallet = None
    if data.paid_amount > 0 and _real_cash_refund:
        # T1.10: yagona qoida — so'ralgan kassa -> asl sotuv kassasi -> qaytaruvchi kassasi (asl kassa nofaol bo'lsa filial kassasi)
        refund_wallet = resolve_wallet(
            db, current_user, purpose="refund", requested_wallet_id=data.wallet_id, original_sale=original_sale,
            branch_id=(original_sale.branch_id if original_sale is not None else None)
            or find_tx_branch(db, current_user, warehouse_id=data.warehouse_id),
            for_update=True,
        )

    # ─── Mijoz qarz mantig'i ─────────────────────────────────────────────────
    # Qaytarishda:
    #   payment_type = "debt"   → barcha tovar qiymati qarzdan ayiriladi (naqd berilmaydi)
    #   payment_type = "cash"   → paid_amount kassadan chiqariladi (mijoz naqd oladi)
    #   Qisman to'lov           → paid_amount naqd, qolgan (total - paid) qarzdan ayiriladi
    # ─────────────────────────────────────────────────────────────────────────
    _ret_customer = None
    if data.customer_id:
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).with_for_update().first()
        if not customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
        _ret_customer = customer

        # Qarzdan ayiriladigan qism: qarzga yopilgan vazvrat uchun
        # "debt" to'lov turida paid_amount = 0, debt_reduction = total_amount
        # Naqd to'lovda paid_amount = total_amount, debt_reduction = 0
        _paid = data.paid_amount
        if data.payment_type == PaymentType.debt:
            # Qarzga yopiladigan vazvrat: kassaga hech narsa berilmaydi
            _paid = Decimal("0")

        # total_amount — UZS, _paid — sotuv valyutasida
        debt_reduction = total_amount - _paid * exchange_rate

        if debt_reduction > Decimal("0"):
            customer.debt_balance = max(Decimal("0"), customer.debt_balance - debt_reduction)

            # Ko'p valyutali debt_balances ni ham yangilash
            if not customer.debt_balances:
                customer.debt_balances = {}

            if data.currency_totals:
                for curr_code, curr_debt in data.currency_totals.items():
                    curr_val = float(customer.debt_balances.get(curr_code, 0))
                    customer.debt_balances[curr_code] = max(0, curr_val - float(curr_debt))
            else:
                actual_debt_in_currency = total_in_sale_currency - _paid
                curr_val = float(customer.debt_balances.get(sale_currency, 0))
                customer.debt_balances[sale_currency] = max(0, curr_val - float(actual_debt_in_currency))

            flag_modified(customer, "debt_balances")

        # Kassa uchun asl paid_amount ni qayta belgilash
        # debt tipida paid_amount 0 bo'lishi kerak
        if data.payment_type == PaymentType.debt:
            data = data.model_copy(update={"paid_amount": Decimal("0"), "paid_cash": Decimal("0"), "paid_card": Decimal("0")})

    from app.models.shift import Shift as _Shift
    _open_shift = db.query(_Shift).filter(
        _Shift.cashier_id == current_user.id,
        _Shift.company_id == current_user.company_id,  # T1.2: boshqa korxonadagi smenaga bog'lanmasin
        _Shift.status == "open",
    ).first()

    sale = Sale(
        number=generate_return_number(
            db, current_user.company_id, find_tx_branch(db, current_user, warehouse_id=data.warehouse_id)
        ),
        shift_id=_open_shift.id if _open_shift else None,
        cashier_id=current_user.id,
        company_id=current_user.company_id,
        warehouse_id=data.warehouse_id,
        customer_id=data.customer_id,
        total_amount=total_amount,
        discount_amount=data.discount_amount,
        paid_amount=data.paid_amount,
        paid_cash=data.paid_cash,
        paid_card=data.paid_card,
        payment_type=data.payment_type,
        status=SaleStatus.refunded,
        note="Vazvrat: " + (data.note or ""),
        currency_id=data.currency_id,
        exchange_rate=exchange_rate,
        loyalty_points_earned=0,
        loyalty_points_used=0,
        original_sale_id=original_sale.id if original_sale is not None else None,
        idempotency_key=idempotency_key,
        wallet_id=refund_wallet.id if refund_wallet is not None else None,
    )
    db.add(sale)
    db.flush()
    approval_service.link_reference(_consumed_approval, "sale_return", sale.id)   # T4.6

    # Pul qaytarilsa — expense tranzaksiya + kassa harakati (kassa topilmasa yuqorida 400 bo'lgan).
    if refund_wallet is not None:
        wallet = refund_wallet
        tx_branch_id = wallet.branch_id or find_tx_branch(db, current_user, wallet=wallet, warehouse_id=data.warehouse_id)
        if data.payment_type == PaymentType.mixed:
            refund_parts = [(_pt, Decimal(str(_amt))) for _pt, _amt in
                            [("cash", data.paid_cash), ("card", data.paid_card)] if _amt > 0]
            if not refund_parts:
                refund_parts = [("cash", Decimal(str(data.paid_amount)))]
        else:
            refund_parts = [(data.payment_type.value, Decimal(str(data.paid_amount)))]

        from app.models.moliya import KassaSession as _KS
        _ks = db.query(_KS).filter(_KS.wallet_id == wallet.id, _KS.status == "open").first()
        open_session_id = _ks.id if _ks else None
        mixed_label = " (Aralash/{})" if data.payment_type == PaymentType.mixed else ""

        for _pt, _amt in refund_parts:
            _lbl = mixed_label.format(_pt)
            db.add(Transaction(
                branch_id=tx_branch_id, company_id=current_user.company_id,
                wallet_id=wallet.id,
                type="expense", amount=_amt, payment_type=_pt,
                currency_code=sale_currency,
                reference_type="sale_refund", reference_id=sale.id,
                description=f"Vazvrat to'lovi #{sale.number}{_lbl}",
            ))
            db.add(KassaMovement(
                wallet_id=wallet.id, company_id=current_user.company_id,
                session_id=open_session_id,
                direction="out", payment_type=_pt, amount=_amt,
                currency=sale_currency,
                reference_type="sale_refund", reference_id=sale.id,
                description=f"Vazvrat #{sale.number}{_lbl}",
                created_by=current_user.id,
            ))
            # Wallet.balance faqat UZS (sale_create bilan simmetriya)
            if (sale_currency or "UZS").upper() == "UZS":
                wallet.balance = Decimal(str(wallet.balance or 0)) - _amt

    # Stock oshirish + SaleItem yozish
    for item_d in sale_items_data:
        product = item_d["product"]
        qty_needed = Decimal(str(item_d["quantity"]))
        is_virtual = getattr(product, "product_type", "stock") == "sell"

        if is_virtual:
            conversion = db.query(ProductConversion).filter(
                ProductConversion.sell_product_id == product.id
            ).first()
            if not conversion:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{product.name}' uchun konversiya topilmadi",
                )
            conv_qty = conversion.ratio * qty_needed
            receive_stock(
                db=db, product_id=conversion.source_product_id, quantity=conv_qty,
                user_id=current_user.id, reason=f"Vazvrat #{sale.number} (Tarkibiy: {product.name})",
                reference_type="sale_refund", reference_id=sale.id, warehouse_id=data.warehouse_id,
            )
            source_prod = db.query(Product).filter(Product.id == conversion.source_product_id).first()
            if item_d.get("batch_plan") is not None:
                apply_pharmacy_batch_return(
                    db, item_d["batch_plan"], product_id=conversion.source_product_id, variant_id=None,
                    warehouse_id=data.warehouse_id, company_id=current_user.company_id,
                    purchase_price=source_prod.cost_price if source_prod else Decimal("0"),
                )
            else:
                db.add(Batch(
                    product_id=conversion.source_product_id, warehouse_id=data.warehouse_id,
                    lot_number=f"RETURN-{sale.number}", initial_quantity=conv_qty, quantity=conv_qty,
                    purchase_price=source_prod.cost_price if source_prod else Decimal("0"),
                    company_id=current_user.company_id,
                ))
        else:
            receive_stock(
                db=db, product_id=product.id, quantity=qty_needed,
                user_id=current_user.id, reason=f"Vazvrat #{sale.number}",
                reference_type="sale_refund", reference_id=sale.id, warehouse_id=data.warehouse_id,
                variant_id=item_d["variant_id"],
            )
            if item_d.get("batch_plan") is not None:
                apply_pharmacy_batch_return(
                    db, item_d["batch_plan"], product_id=product.id, variant_id=item_d["variant_id"],
                    warehouse_id=data.warehouse_id, company_id=current_user.company_id,
                    purchase_price=product.cost_price,
                )
            else:
                db.add(Batch(
                    product_id=product.id, variant_id=item_d["variant_id"], warehouse_id=data.warehouse_id,
                    lot_number=f"RETURN-{sale.number}", initial_quantity=qty_needed, quantity=qty_needed,
                    purchase_price=product.cost_price, company_id=current_user.company_id,
                ))

        db.add(SaleItem(
            sale_id=sale.id, product_id=product.id, variant_id=item_d["variant_id"],
            warehouse_id=data.warehouse_id, quantity=qty_needed,
            unit_price=item_d["unit_price"], cost_price=item_d["cost_price"],
            discount=item_d["discount"], subtotal=item_d["subtotal"],
            currency_code=item_d["currency_code"], exchange_rate=item_d["exchange_rate"],
            marking_codes=[r.code for r in item_d["marking_rows"]] or None,
        ))
        if item_d["marking_rows"]:
            from app.routers.pharmacy_marking import apply_return_marking
            apply_return_marking(item_d["marking_rows"], data.warehouse_id)   # D3.2

    # T2.12: sodiqlik qoidalari (korxona + filial)
    _loy_rules = get_loyalty_rules(db, current_user.company_id, warehouse_id=data.warehouse_id)

    # Asl sotuv berilgan bo'lsa: qaytarilgan miqdor oshiriladi va status yangilanadi
    if original_sale is not None:
        # Keshbek/ball teskarisi qaytarilgan summa ulushiga mutanosib (Δ), asl sotuvda saqlangan qiymatlar bo'yicha
        _ratio_before = returned_ratio(original_items)
        for oi in original_items:
            if oi.id in taken_qty:
                oi.returned_quantity = Decimal(str(oi.returned_quantity or 0)) + taken_qty[oi.id]
        original_customer = None
        if original_sale.customer_id:
            original_customer = db.query(Customer).filter(
                Customer.id == original_sale.customer_id,
                Customer.company_id == original_sale.company_id,
            ).with_for_update().first()
        db.flush()
        _ratio_after = returned_ratio(original_items)
        if original_customer is not None and _ratio_after > _ratio_before and _loy_rules.return_reverses_loyalty:
            reverse_sale_loyalty(original_customer, original_sale, ratio=_ratio_after - _ratio_before,
                                 ratio_before=_ratio_before)
        # Mijoz berilmaydi: to'liq qaytarishda ikkinchi marta ayirilmasin (yuqorida Δ bo'yicha ayirildi)
        refresh_original_sale_status(db, original_sale, None)
    elif _ret_customer is not None and _loy_rules.return_reverses_loyalty:
        # Asl sotuvga bog'lanmagan POS "Vazvrat": qaytarilgan summa bo'yicha keshbek/ball/total_spent kamayadi
        _loy_log = reverse_return_without_sale(_ret_customer, total_amount, _loy_rules)
        if _loy_log:
            log_action(
                db=db, action="RETURN_LOYALTY_REVERSE", entity_type="customer", entity_id=_ret_customer.id,
                user_id=current_user.id, ip_address=ip,
                new_values={"return_sale_id": sale.id, **_loy_log},
            )

    log_action(
        db=db, action="SALE_RETURN", entity_type="sale", entity_id=sale.id,
        user_id=current_user.id, ip_address=ip,
    )
    _neg_warning = (
        NEGATIVE_BALANCE_WARNING
        if refund_wallet is not None and Decimal(str(refund_wallet.balance or 0)) < 0 else None
    )
    db.commit()
    db.refresh(sale)
    # T1.10: yozuv saqlanadi, lekin kassa balansi manfiyga tushsa javobda ogohlantirish (SaleListOut.warning)
    sale.warning = _neg_warning  # type: ignore[attr-defined]
    return sale
