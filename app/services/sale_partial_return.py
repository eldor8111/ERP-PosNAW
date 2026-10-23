from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.audit import log_action
from app.models.sale import Sale, SaleItem, SaleStatus, PaymentType
from app.models.product import ProductConversion
from app.models.customer import Customer
from app.models.user import User
from app.models.moliya import Transaction, KassaMovement, Wallet
from app.schemas.sale import SaleReturnRequest
from app.services.inventory_service import receive_stock
from app.services import approval_service  # T4.6: qaytarish limiti va tasdiqlash
from app.services.sale_helpers import (
    generate_return_number, apply_sale_branch_filter, refresh_original_sale_status,
    validate_sale_warehouse,
)
from app.services.loyalty_service import get_loyalty_rules, reverse_sale_loyalty, returned_ratio
from app.services.pharmacy import pharmacy_context  # D1.4: dorixona rejimida asl partiyaga qaytarish
from app.services.sale_return import plan_pharmacy_batch_return, apply_pharmacy_batch_return
from app.services.tenant_guards import find_tx_branch
from app.services.wallet_resolver import resolve_wallet, NEGATIVE_BALANCE_WARNING
import datetime

def process_partial_return(
    db: Session,
    sale_id: int,
    data: SaleReturnRequest,
    current_user: User,
    ip: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Sale:
    original_q = db.query(Sale).filter(Sale.id == sale_id, Sale.company_id == current_user.company_id)
    original_sale = apply_sale_branch_filter(original_q, db, current_user).first()
    if not original_sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")
    if original_sale.status in (SaleStatus.refunded, SaleStatus.cancelled):
        raise HTTPException(status_code=400, detail="Bekor qilingan yoki to'liq qaytarilgan sotuvdan tovar qaytarib bo'lmaydi")

    # mixed/cashback KassaMovement.payment_type ga mavjud bo'lmagan qiymat yozardi (T0.29)
    if data.payment_type in (PaymentType.mixed, PaymentType.cashback):
        raise HTTPException(status_code=400, detail="Qisman qaytarishda bu to'lov turi qo'llab-quvvatlanmaydi")

    # Zaxira ombor (qator va sotuv omborlari bo'sh bo'lsa) — faqat shu korxonaning faol ombori
    fallback_warehouse_id = None
    if data.warehouse_id:
        fallback_warehouse_id = validate_sale_warehouse(db, current_user, data.warehouse_id).id

    # D1.4: dorixona moduli yoqilgan korxonada qaytgan tovar aynan sotilgan partiyaga qaytadi
    pharmacy_on, _ph_settings = pharmacy_context(db, current_user.company_id)
    batch_used = {}
    marking_used = set()   # CD.1/D3.2: bir so'rovda bir kod ikki marta qaytmasin

    sale_currency = original_sale.currency.code if original_sale.currency else "UZS"
    exchange_rate = Decimal(str(original_sale.exchange_rate or "1.0")) or Decimal("1")

    # Sotuv qatori summasi mahsulot valyutasida saqlanadi; hujjat jami (Sale.total_amount)
    # esa sotuvdagi kabi UZS da yig'iladi (hisobotlar va chek shunga tayanadi).
    total_refund_uzs = Decimal("0")
    returned_items_info = []
    new_sale_items = []
    # returned_quantity hamyon aniqlangandan KEYIN oshiriladi (400 bo'lsa hech narsa o'zgarmasin)
    items_to_mark = []
    taken_qty = {}

    # 1. Barcha so'ralgan tovarlarni tekshiramiz va qaytaramiz
    for ret_item in data.items:
        sale_item = db.query(SaleItem).filter(
            SaleItem.id == ret_item.sale_item_id,
            SaleItem.sale_id == original_sale.id
        ).with_for_update().first()
        if not sale_item:
            raise HTTPException(status_code=404, detail=f"Sotuv elementi topilmadi: {ret_item.sale_item_id}")
        
        qty_to_return = Decimal(str(ret_item.quantity))
        qty_available = (
            Decimal(str(sale_item.quantity))
            - Decimal(str(getattr(sale_item, 'returned_quantity', None) or 0))
            - taken_qty.get(sale_item.id, Decimal("0"))
        )
        if qty_to_return <= 0 or qty_to_return > qty_available:
            raise HTTPException(status_code=400, detail=f"Qaytarish miqdori noto'g'ri (Mavjud: {qty_available})")

        actual_price = sale_item.subtotal / sale_item.quantity
        refund_value = actual_price * qty_to_return  # mahsulot valyutasida
        item_rate = Decimal(str(sale_item.exchange_rate or 1)) or Decimal("1")
        total_refund_uzs += refund_value * item_rate

        # Asl sale_item da faqat returned_quantity oshiriladi (double return oldini olish uchun)
        taken_qty[sale_item.id] = taken_qty.get(sale_item.id, Decimal("0")) + qty_to_return
        items_to_mark.append((sale_item, qty_to_return))

        # Tovar sotilgan omborga qaytadi: qator ombori -> sotuv ombori -> so'rovdagi ombor
        item_warehouse_id = sale_item.warehouse_id or original_sale.warehouse_id or fallback_warehouse_id
        if not item_warehouse_id:
            raise HTTPException(status_code=400, detail="Ombor aniqlanmadi")

        # Virtual (tarkibiy, product_type == "sell") mahsulot: manba mahsulotga qty*ratio qaytariladi
        conversion = None
        if sale_item.product is not None and sale_item.product.product_type == "sell":
            conversion = db.query(ProductConversion).filter(
                ProductConversion.sell_product_id == sale_item.product_id
            ).first()
            if not conversion:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{sale_item.product.name}' uchun konversiya topilmadi",
                )

        # D1.4: dorixona rejimida partiya rejasi (yozishdan oldin; asl ajratma yo'q bo'lsa seriya/muddat majburiy, aks holda 400)
        batch_plan = None
        if pharmacy_on and sale_item.product is not None and sale_item.product.product_type != "service":
            _ratio = Decimal(str(conversion.ratio)) or Decimal("1") if conversion is not None else Decimal("1")
            batch_plan = plan_pharmacy_batch_return(
                db, sale_item, qty_to_return * _ratio, _ratio, batch_used, ret_item, sale_item.product,
            )

        # CD.1/D3.2: dorixona rejimida markirovkali dori kodlari (sold -> in_stock); to'liq qaytarishdagi (sale_return) qoida
        marking_rows = []
        if pharmacy_on and sale_item.product is not None and sale_item.product.requires_marking:
            from app.models.product import Product as _Product
            from app.models.product_units import SaleItemUnit as _SIU
            from app.routers.pharmacy_marking import plan_return_marking
            _codes_qty = qty_to_return
            _siu = db.query(_SIU).filter(_SIU.sale_item_id == sale_item.id).first()
            if _siu is not None and Decimal(str(_siu.unit_ratio or 0)) > 0:
                # Qutida sotilgan qator: kod har bir quti uchun — qaytarilayotgan quti soni (butun)
                from app.services.sale_stock import pack_ratio_of
                _pack = pack_ratio_of(db, sale_item.product_id, current_user.company_id)
                _codes_qty = (qty_to_return // _pack) if _pack else Decimal("0")
            marking_rows = plan_return_marking(
                db, current_user.company_id, product=sale_item.product,
                source=db.get(_Product, conversion.source_product_id) if conversion is not None else None,
                original_item=sale_item, codes=getattr(ret_item, "marking_codes", None), qty=_codes_qty,
                used_ids=marking_used,
            )

        returned_items_info.append(f"{sale_item.product.name} ({qty_to_return} ta)")
        
        # Yangi return document (Sale) uchun item yaratamiz
        new_sale_items.append({
            'product_id': sale_item.product_id,
            'variant_id': sale_item.variant_id,
            # Qaysi ombordan sotilgan bo'lsa, o'sha omborga qaytadi (qator ombori, T0.30)
            'warehouse_id': item_warehouse_id,
            'conversion': conversion,
            'quantity': qty_to_return,
            'unit_price': sale_item.unit_price,
            'cost_price': sale_item.cost_price,
            'discount': sale_item.discount,
            'subtotal': refund_value,
            'currency_code': sale_item.currency_code or "UZS",
            'exchange_rate': item_rate,
            'product': sale_item.product,
            'batch_plan': batch_plan,
            'marking_rows': marking_rows,
        })

    # 2. Yangi Return hujjatini (Sale ob'ektini) yaratamiz.
    # Pul va qarz mantig'i sotuv valyutasida ishlaydi.
    total_refund_amount = total_refund_uzs / exchange_rate

    # T4.6: qaytarish summasi limiti (qoida yo'q korxonada o'zgarmaydi; admin/director ozod, faqat audit)
    _ref_branch = original_sale.branch_id or find_tx_branch(db, current_user, warehouse_id=original_sale.warehouse_id)
    _consumed_approval = approval_service.enforce(
        db, current_user, [v for v in [approval_service.evaluate_refund(db, current_user, total_refund_uzs, _ref_branch)] if v],
        payload=approval_service.partial_return_payload(sale_id, data), amount=total_refund_uzs, branch_id=_ref_branch,
        approval_id=getattr(data, "approval_id", None),
    )

    # debt bo'lmagan har qanday to'lov turi (cash, card, uzcard, humo, bank,
    # click, payme, visa, uzum) uchun pul kassadan/hisobdan qaytariladi.
    amount_to_return_money = total_refund_amount if data.payment_type != PaymentType.debt else Decimal("0")
    amount_to_reduce_debt = total_refund_amount if data.payment_type == PaymentType.debt else Decimal("0")
    money_payment_type = data.payment_type

    # "Qarzdan chegirish" tanlangan bo'lsa-yu, lekin original sotuvda
    # shuncha qarz qolmagan bo'lsa (masalan allaqachon pay_debt orqali
    # tolangan), ortiqcha summani mijozning boshqa sotuvlaridagi qarzidan
    # emas, naqd sifatida qaytaramiz - aks holda boshqa sotuvning qonuniy
    # qarzi notogri kamayib ketishi mumkin (2.6 dagi kabi).
    if amount_to_reduce_debt > 0:
        # original_sale.total_amount/paid_amount larga solishtirish uchun
        # amount_to_reduce_debt ni xuddi pastdagi "new_paid" hisoblanishidagi
        # kabi exchange_rate bilan bir xil birlik tizimiga o'tkazamiz.
        outstanding_on_sale = max(
            Decimal("0"),
            Decimal(str(original_sale.total_amount or 0)) - Decimal(str(original_sale.paid_amount or 0)),
        )
        reduce_converted = amount_to_reduce_debt * exchange_rate
        if reduce_converted > outstanding_on_sale:
            excess_converted = reduce_converted - outstanding_on_sale
            excess_as_cash = excess_converted / exchange_rate if exchange_rate else excess_converted
            amount_to_reduce_debt = amount_to_reduce_debt - excess_as_cash
            amount_to_return_money += excess_as_cash
            money_payment_type = PaymentType.cash

    # Pul chiqadigan kassa: hech narsa yozilishidan OLDIN aniqlanadi — topilmasa 400 va
    # hech narsa o'zgarmaydi (avval pul jim hisobsiz qaytib ketardi).
    refund_wallet = None
    if amount_to_return_money > 0:
        # T1.10: yagona qoida — so'ralgan kassa -> asl sotuv kassasi -> qaytaruvchi kassasi (asl kassa nofaol bo'lsa filial kassasi)
        refund_wallet = resolve_wallet(
            db, current_user, purpose="refund", requested_wallet_id=data.wallet_id, original_sale=original_sale,
            branch_id=original_sale.branch_id or find_tx_branch(db, current_user, warehouse_id=original_sale.warehouse_id),
            for_update=True,
        )

    # T2.12: keshbek/ball teskarisi qaytarilgan SUMMA ulushiga mutanosib: Δ = ratio_after - ratio_before
    # (Σ returned_quantity*unit_price / Σ quantity*unit_price), shunda to'liq qaytarishda jami 1.0 bo'ladi
    _ratio_before = returned_ratio(db.query(SaleItem).filter(SaleItem.sale_id == original_sale.id).all())
    for _si, _qty in items_to_mark:
        _si.returned_quantity = Decimal(str(_si.returned_quantity or 0)) + _qty
    db.flush()
    _ratio_after = returned_ratio(db.query(SaleItem).filter(SaleItem.sale_id == original_sale.id).all())

    from app.models.shift import Shift as _Shift
    _open_shift = db.query(_Shift).filter(
        _Shift.cashier_id == current_user.id,
        _Shift.company_id == current_user.company_id,  # T1.2: boshqa korxonadagi smenaga bog'lanmasin
        _Shift.status == "open",
    ).first()

    return_sale = Sale(
        number=generate_return_number(
            db, current_user.company_id,
            find_tx_branch(db, current_user, warehouse_id=original_sale.warehouse_id),
        ),
        shift_id=_open_shift.id if _open_shift else None,
        cashier_id=current_user.id,
        company_id=current_user.company_id,
        warehouse_id=original_sale.warehouse_id,
        customer_id=original_sale.customer_id,
        total_amount=total_refund_uzs,
        discount_amount=Decimal("0"),
        paid_amount=amount_to_return_money,
        paid_cash=amount_to_return_money if money_payment_type == PaymentType.cash else Decimal("0"),
        paid_card=amount_to_return_money if money_payment_type not in (PaymentType.cash, PaymentType.debt) else Decimal("0"),
        payment_type=data.payment_type,
        status=SaleStatus.refunded,
        note=f"Qisman qaytarish (Sotuv #{original_sale.number})",
        currency_id=original_sale.currency_id,
        exchange_rate=exchange_rate,
        loyalty_points_earned=0,
        loyalty_points_used=0,
        original_sale_id=original_sale.id,
        idempotency_key=idempotency_key,
        wallet_id=refund_wallet.id if refund_wallet is not None else None,
    )
    db.add(return_sale)
    db.flush() # return_sale.id ni olish uchun
    approval_service.link_reference(_consumed_approval, "sale_return", return_sale.id)   # T4.6
    
    # 3. Yangi SaleItem larni bazaga yozish va Stockni yangilash
    for item_data in new_sale_items:
        db.add(SaleItem(
            sale_id=return_sale.id,
            product_id=item_data['product_id'],
            variant_id=item_data['variant_id'],
            warehouse_id=item_data['warehouse_id'],
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price'],
            cost_price=item_data['cost_price'],
            discount=item_data['discount'],
            subtotal=item_data['subtotal'],
            currency_code=item_data['currency_code'],
            exchange_rate=item_data['exchange_rate'],
            marking_codes=[r.code for r in item_data.get('marking_rows') or []] or None,
        ))
        if item_data.get('marking_rows'):
            from app.routers.pharmacy_marking import apply_return_marking
            apply_return_marking(item_data['marking_rows'], item_data['warehouse_id'])   # CD.1/D3.2

        product = item_data['product']
        conversion = item_data['conversion']
        batch_plan = item_data.get('batch_plan')
        if conversion is not None:
            ratio = Decimal(str(conversion.ratio)) or Decimal("1")
            # D1.4: dorixona rejimida purchase_price berilmaydi — qoldiq oshadi, partiyani esa pastda asl partiyalarga yozamiz
            receive_stock(
                db=db,
                product_id=conversion.source_product_id,
                quantity=item_data['quantity'] * ratio,
                user_id=current_user.id,
                reason=f"Qisman qaytarish (Sotuv #{original_sale.number}, Tarkibiy: {product.name})",
                reference_type="sale_refund",
                reference_id=return_sale.id,
                warehouse_id=item_data['warehouse_id'],
                purchase_price=None if batch_plan is not None else Decimal(str(item_data['cost_price'] or 0)) / ratio,
                company_id=None if batch_plan is not None else current_user.company_id,
            )
            if batch_plan is not None:
                apply_pharmacy_batch_return(
                    db, batch_plan, product_id=conversion.source_product_id, variant_id=None,
                    warehouse_id=item_data['warehouse_id'], company_id=current_user.company_id,
                    purchase_price=Decimal(str(item_data['cost_price'] or 0)) / ratio,
                )
        elif product and product.product_type != "service":
            receive_stock(
                db=db,
                product_id=item_data['product_id'],
                quantity=item_data['quantity'],
                user_id=current_user.id,
                reason=f"Qisman qaytarish (Sotuv #{original_sale.number})",
                reference_type="sale_refund",
                reference_id=return_sale.id,
                warehouse_id=item_data['warehouse_id'],
                purchase_price=None if batch_plan is not None else item_data['cost_price'],
                company_id=None if batch_plan is not None else current_user.company_id,
                variant_id=item_data['variant_id'],
            )
            if batch_plan is not None:
                apply_pharmacy_batch_return(
                    db, batch_plan, product_id=item_data['product_id'], variant_id=item_data['variant_id'],
                    warehouse_id=item_data['warehouse_id'], company_id=current_user.company_id,
                    purchase_price=item_data['cost_price'],
                )

    # 4. Moliya / Qarzni to'g'rilash (Yangi return hujjatiga bog'langan holda)
    customer = None
    if original_sale.customer_id:
        customer = db.query(Customer).filter(
            Customer.id == original_sale.customer_id,
            Customer.company_id == original_sale.company_id,
        ).with_for_update().first()
        
    if amount_to_reduce_debt > 0 and customer:
        # Mijoz qarz balansini kamaytirish
        customer.debt_balance = max(Decimal("0"), (customer.debt_balance or Decimal("0")) - (amount_to_reduce_debt * exchange_rate))
        if customer.debt_balances and float(customer.debt_balances.get(sale_currency, 0)) > 0:
            cur_debt = Decimal(str(customer.debt_balances[sale_currency]))
            customer.debt_balances[sale_currency] = float(max(Decimal("0"), cur_debt - amount_to_reduce_debt))
            flag_modified(customer, "debt_balances")
        
        # Original sotuvning paid_amount ni oshirish
        original_paid = Decimal(str(original_sale.paid_amount or "0"))
        original_total = Decimal(str(original_sale.total_amount or "0"))
        new_paid = min(original_total, original_paid + (amount_to_reduce_debt * exchange_rate))
        original_sale.paid_amount = new_paid  # type: ignore
        # debt_amounts ni ham yangilash
        if original_sale.debt_amounts and sale_currency in (original_sale.debt_amounts or {}):
            cur_sale_debt = Decimal(str(original_sale.debt_amounts[sale_currency]))
            original_sale.debt_amounts[sale_currency] = float(max(Decimal("0"), cur_sale_debt - amount_to_reduce_debt))
            flag_modified(original_sale, "debt_amounts")
            
    if amount_to_return_money > 0 and refund_wallet is not None:
        wallet = refund_wallet
        wallet_id = wallet.id
        # Wallet.balance / WalletBalance faqat UZS (sale_create bilan simmetriya); boshqa
        # valyutada faqat Transaction va KassaMovement (sotuv valyutasida) yoziladi.
        if (sale_currency or "UZS").upper() == "UZS":
            from app.models.moliya import WalletBalance
            wallet.balance = Decimal(str(wallet.balance or 0)) - amount_to_return_money

            wb = db.query(WalletBalance).filter(
                WalletBalance.wallet_id == wallet_id,
                WalletBalance.payment_type == money_payment_type.value
            ).first()
            if wb:
                wb.balance = Decimal(str(wb.balance or 0)) - amount_to_return_money
            else:
                wb = WalletBalance(wallet_id=wallet_id, payment_type=money_payment_type.value, balance=-amount_to_return_money)
                db.add(wb)

        tx_branch_id = wallet.branch_id or find_tx_branch(db, current_user, wallet=wallet, warehouse_id=original_sale.warehouse_id)
        db.add(Transaction(
            company_id=current_user.company_id,
            branch_id=tx_branch_id,
            wallet_id=wallet_id,
            type="expense",
            amount=amount_to_return_money,
            currency_code=sale_currency,
            payment_type=money_payment_type.value,
            reference_type="sale_refund",
            reference_id=return_sale.id,
            description=f"Qisman qaytarish (Sotuv #{original_sale.number})"
        ))

        if money_payment_type.value not in ("debt", "cashback"):
            from app.models.moliya import KassaSession as _KS
            _ks = db.query(_KS).filter(_KS.wallet_id == wallet_id, _KS.status == "open").first()
            db.add(KassaMovement(
                wallet_id=wallet_id, company_id=current_user.company_id,
                session_id=_ks.id if _ks else None,
                direction="out", payment_type=money_payment_type.value, amount=amount_to_return_money,
                currency=sale_currency,
                reference_type="sale_refund", reference_id=return_sale.id,
                description=f"Qisman qaytarish (Sotuv #{original_sale.number})",
                created_by=current_user.id,
            ))

    # Original sotuv statusini to'lov turidan qat'iy nazar, MIQDOR asosida yangilaymiz
    # (umumiy funksiya — /sales/return ham shuni ishlatadi).
    # Keshbek/ball/total_spent: sotuvda saqlangan qiymatlar bo'yicha, har qaytarishda faqat yangi ulush (Δ).
    # `refresh_original_sale_status` ga mijoz berilmaydi — u to'liq qaytarishda joriy qiymatlar bilan
    # ikkinchi marta ayirib yuborardi.
    if customer is not None and _ratio_after > _ratio_before:
        _rules = get_loyalty_rules(db, original_sale.company_id, branch_id=original_sale.branch_id,
                                   warehouse_id=original_sale.warehouse_id)
        if _rules.return_reverses_loyalty:
            reverse_sale_loyalty(customer, original_sale, ratio=_ratio_after - _ratio_before, ratio_before=_ratio_before)
    refresh_original_sale_status(db, original_sale, None)

    log_action(db, "RETURN_ITEMS", "sale", return_sale.id, current_user.id, {"items": returned_items_info, "amount": float(total_refund_amount), "original_sale_id": original_sale.id})

    _neg_warning = (
        NEGATIVE_BALANCE_WARNING
        if refund_wallet is not None and Decimal(str(refund_wallet.balance or 0)) < 0 else None
    )
    db.commit()
    db.refresh(original_sale)
    # T1.10: yozuv saqlanadi, lekin kassa balansi manfiyga tushsa javobda ogohlantirish (SaleOut.warning)
    original_sale.warning = _neg_warning  # type: ignore[attr-defined]
    return original_sale
