from collections import defaultdict
from decimal import Decimal
from typing import Optional
import threading

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.batch import Batch
from app.models.customer import Customer
from app.models.customer_prices import CustomerPrice
from app.models.currency import Currency
from app.models.company import Company
from app.models.moliya import Transaction, KassaMovement
from app.models.product import Product, ProductConversion, ProductStatus
from app.models.sale import Sale, SaleItem, SaleStatus, PaymentType, SaleItemBatch, SalePayment
from app.models.user import User
from app.schemas.sale import SaleCreate
from app.services.sale_helpers import (
    generate_sale_number, send_tg_sync, resolve_price, resolve_branch_id
)


def create_sale(
    db: Session,
    data: SaleCreate,
    current_user: User,
    ip: Optional[str] = None,
    background_tasks=None,
) -> Sale:
    # ── Warehouse aniqlash ────────────────────────────────────────────────────
    if data.warehouse_id is None:
        from app.models.warehouse import Warehouse
        from app.models.inventory import StockLevel as _SL
        wh_q = db.query(Warehouse).filter(
            Warehouse.company_id == current_user.company_id,
            Warehouse.is_active == True,
        )
        if current_user.branch_id:
            wh = wh_q.filter(Warehouse.branch_id == current_user.branch_id).first()
            if not wh:
                wh = wh_q.first()
            if wh:
                data.warehouse_id = wh.id
        else:
            if data.items:
                first_pid = data.items[0].product_id
                stock_row = (
                    db.query(_SL)
                    .join(Warehouse, Warehouse.id == _SL.warehouse_id)
                    .filter(
                        _SL.product_id == first_pid,
                        _SL.quantity > 0,
                        _SL.warehouse_id.isnot(None),
                        Warehouse.is_active == True,
                    )
                    .order_by(_SL.quantity.desc())
                    .first()
                )
                if stock_row:
                    data.warehouse_id = stock_row.warehouse_id

    # ── Mahsulotlar narxi hisoblash ───────────────────────────────────────────
    sale_items_data = []
    total_amount = Decimal("0")

    for item_data in data.items:
        product = db.query(Product).filter(
            Product.id == item_data.product_id,
            Product.company_id == current_user.company_id,
            Product.is_deleted == False,
            Product.status == ProductStatus.active,
        ).first()
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Mahsulot ID={item_data.product_id} topilmadi yoki nofaol",
            )

        _customer_price = None
        _customer = None
        if data.customer_id:
            _customer_price = db.query(CustomerPrice).filter(
                CustomerPrice.customer_id == data.customer_id,
                CustomerPrice.product_id == item_data.product_id,
            ).first()
            _customer = db.query(Customer).filter(Customer.id == data.customer_id).first()

        unit_price = resolve_price(item_data, product, _customer_price, _customer)

        discount = item_data.discount
        if discount > unit_price * item_data.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"'{product.name}' uchun chegirma ({discount}) narxdan oshib ketdi",
            )
        subtotal = (unit_price * item_data.quantity) - discount

        conversion = db.query(ProductConversion).filter(
            ProductConversion.sell_product_id == product.id
        ).first()
        source_product = None
        if conversion:
            source_product = db.query(Product).filter(
                Product.id == conversion.source_product_id,
                Product.is_deleted == False,
            ).first()
            if not source_product:
                conversion = None

        sale_items_data.append({
            "product": product,
            "quantity": item_data.quantity,
            "unit_price": unit_price,
            "cost_price": product.cost_price,
            "discount": discount,
            "subtotal": subtotal,
            "conversion": conversion,
            "source_product": source_product,
            "item_warehouse_id": item_data.warehouse_id,
        })
        total_amount += subtotal

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
        for _field, _ptype in _field_type_map:
            _val = getattr(data, _field, Decimal("0")) or Decimal("0")
            if _val > 0:
                from app.schemas.sale import PaymentItem as _PI
                _auto_payments.append(_PI(type=PaymentType(_ptype), amount=_val))
        if _auto_payments:
            data.payments = _auto_payments

    paid_cashback_amount = getattr(data, "paid_cashback", Decimal("0")) or Decimal("0")
    if not paid_cashback_amount and data.payments:
        for _p in data.payments:
            if _p.type == PaymentType.cashback:
                paid_cashback_amount += _p.amount
    if paid_cashback_amount > 0 and not data.customer_id:
        raise HTTPException(status_code=400, detail="Keshbekdan foydalanish uchun mijozni tanlash majburiy")

    # ── Valyuta ───────────────────────────────────────────────────────────────
    exchange_rate = Decimal(1.0)
    if data.currency_id:
        currency = db.query(Currency).filter(Currency.id == data.currency_id).first()
        if currency:
            exchange_rate = currency.rate

    # ── CRM / Loyallik ────────────────────────────────────────────────────────
    loyalty_earned = 0
    prev_debt_balance = 0.0
    if data.customer_id:
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
        prev_debt_balance = float(customer.debt_balance or 0)

        if data.loyalty_points_used > 0:
            if data.loyalty_points_used > customer.loyalty_points:
                raise HTTPException(status_code=400, detail="Mijozda yetarli loyallik ballari yo'q")
            total_amount -= Decimal(data.loyalty_points_used)
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

        if getattr(customer, "cashback_percent", 0) > 0:
            cashback_amount = (total_amount * exchange_rate * customer.cashback_percent) / Decimal("100")
            customer.bonus_balance = (customer.bonus_balance or Decimal("0")) + cashback_amount
        customer.total_spent = (customer.total_spent or Decimal("0")) + (total_amount * exchange_rate)

        loyalty_earned = int((total_amount * exchange_rate) * Decimal("0.01"))
        customer.loyalty_points += loyalty_earned

        if data.paid_amount < total_amount:
            debt_amount = (total_amount - data.paid_amount) * exchange_rate
            if customer.debt_limit > 0 and (customer.debt_balance + debt_amount) > customer.debt_limit:
                raise HTTPException(status_code=400, detail="Mijozning qarz limiti oshib ketdi")
            
            customer.debt_balance += debt_amount
            
            # Sync with multi-currency debt_balances
            if not customer.debt_balances:
                customer.debt_balances = {}
            
            # The actual debt amount in the sale's currency
            actual_debt_in_currency = total_amount - data.paid_amount
            
            # Sale currency code
            sale_currency = "UZS"
            if data.currency_id:
                from app.models.currency import Currency
                curr_obj = db.query(Currency).filter(Currency.id == data.currency_id).first()
                if curr_obj:
                    sale_currency = curr_obj.code
            
            curr_val = float(customer.debt_balances.get(sale_currency, 0))
            customer.debt_balances[sale_currency] = curr_val + float(actual_debt_in_currency)
            
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(customer, "debt_balances")

    if data.paid_amount < total_amount and not data.customer_id:
        raise HTTPException(status_code=400, detail="Qarzga sotish uchun mijozni tanlash majburiy")

    # ── Sale yozuvi ───────────────────────────────────────────────────────────
    sale = Sale(
        number=generate_sale_number(db),
        cashier_id=current_user.id,
        company_id=current_user.company_id,
        warehouse_id=data.warehouse_id,
        customer_id=data.customer_id,
        total_amount=total_amount,
        discount_amount=data.discount_amount,
        paid_amount=data.paid_amount,
        paid_cash=data.paid_cash,
        paid_card=data.paid_card,
        paid_cashback=paid_cashback_amount,
        payment_type=data.payment_type,
        status=SaleStatus.completed,
        note=data.note,
        currency_id=data.currency_id,
        exchange_rate=exchange_rate,
        loyalty_points_earned=loyalty_earned,
        loyalty_points_used=data.loyalty_points_used,
        debt_due_date=data.debt_due_date,
    )
    db.add(sale)
    db.flush()

    # ── To'lovlar + tranzaksiyalar ────────────────────────────────────────────
    tx_branch_id = resolve_branch_id(db, current_user, data.warehouse_id)

    _cashier_wallet_id = None
    try:
        _sa_text = __import__("sqlalchemy").text
        _uw_row = db.execute(
            _sa_text("SELECT wallet_id FROM user_wallets WHERE user_id=:uid ORDER BY is_default DESC LIMIT 1"),
            {"uid": current_user.id},
        ).fetchone()
        _cashier_wallet_id = _uw_row[0] if _uw_row else None
    except Exception:
        db.rollback()
        _cashier_wallet_id = None

    if _cashier_wallet_id:
        sale.wallet_id = _cashier_wallet_id

    if data.payments and len(data.payments) > 0:
        for p in data.payments:
            if p.amount > 0:
                db.add(SalePayment(sale_id=sale.id, payment_type=p.type.value, amount=p.amount))
                if tx_branch_id:
                    db.add(Transaction(
                        branch_id=tx_branch_id, company_id=current_user.company_id,
                        wallet_id=_cashier_wallet_id,
                        type="income", amount=p.amount, payment_type=p.type.value,
                        reference_type="sale", reference_id=sale.id,
                        description=f"Sotuv to'lovi #{sale.number} ({p.type.value})",
                    ))
                if _cashier_wallet_id and p.type.value not in ("debt", "cashback"):
                    db.add(KassaMovement(
                        wallet_id=_cashier_wallet_id, company_id=current_user.company_id,
                        direction="in", payment_type=p.type.value, amount=p.amount,
                        reference_type="sale", reference_id=sale.id,
                        description=f"Sotuv #{sale.number}", created_by=current_user.id,
                    ))
    elif data.paid_amount > 0:
        if data.payment_type == PaymentType.mixed:
            for _pt, _amt in [("cash", data.paid_cash), ("card", data.paid_card)]:
                if _amt > 0:
                    db.add(SalePayment(sale_id=sale.id, payment_type=_pt, amount=_amt))
                    if tx_branch_id:
                        db.add(Transaction(
                            branch_id=tx_branch_id, company_id=current_user.company_id,
                            type="income", amount=_amt, payment_type=_pt,
                            reference_type="sale", reference_id=sale.id,
                            description=f"Sotuv to'lovi #{sale.number} (Aralash/{_pt})",
                        ))
                    if _cashier_wallet_id:
                        db.add(KassaMovement(
                            wallet_id=_cashier_wallet_id, company_id=current_user.company_id,
                            direction="in", payment_type=_pt, amount=_amt,
                            reference_type="sale", reference_id=sale.id,
                            description=f"Sotuv #{sale.number}", created_by=current_user.id,
                        ))
        else:
            db.add(SalePayment(sale_id=sale.id, payment_type=data.payment_type.value, amount=data.paid_amount))
            if tx_branch_id:
                db.add(Transaction(
                    branch_id=tx_branch_id, company_id=current_user.company_id,
                    type="income", amount=data.paid_amount, payment_type=data.payment_type.value,
                    reference_type="sale", reference_id=sale.id,
                    description=f"Sotuv to'lovi #{sale.number}",
                ))
            if _cashier_wallet_id and data.payment_type.value not in ("debt", "cashback"):
                db.add(KassaMovement(
                    wallet_id=_cashier_wallet_id, company_id=current_user.company_id,
                    direction="in", payment_type=data.payment_type.value, amount=data.paid_amount,
                    reference_type="sale", reference_id=sale.id,
                    description=f"Sotuv #{sale.number}", created_by=current_user.id,
                ))

    # ── Stock kamaytirish (FIFO Batch) ────────────────────────────────────────
    virtual_source_ids = list({
        d["source_product"].id for d in sale_items_data if d.get("source_product")
    })
    regular_ids = list({
        d["product"].id for d in sale_items_data if not d.get("source_product")
    })
    all_stock_ids = list(set(virtual_source_ids + regular_ids))

    all_batches = db.query(Batch).filter(
        Batch.product_id.in_(all_stock_ids),
        Batch.quantity > 0,
        Batch.company_id == current_user.company_id,
    ).order_by(Batch.created_at.asc(), Batch.id.asc()).all()

    batches_by_product = defaultdict(list)
    for b in all_batches:
        batches_by_product[b.product_id].append(b)

    from app.models.inventory import StockLevel as _SL
    stocks_by_product = defaultdict(list)
    if all_stock_ids:
        for s in db.query(_SL).filter(_SL.product_id.in_(all_stock_ids)).order_by(_SL.quantity.desc()).with_for_update().all():
            stocks_by_product[s.product_id].append(s)

    preferred_wh_id = data.warehouse_id
    new_sale_items = []
    new_movements = []

    for item_d in sale_items_data:
        product = item_d["product"]
        qty_needed = Decimal(item_d["quantity"])
        is_virtual = item_d.get("conversion") is not None
        source_product = item_d.get("source_product")
        stock_product = source_product if is_virtual else product
        ratio = Decimal(str(item_d["conversion"].ratio)) if is_virtual else Decimal("1")
        qty_to_deduct = qty_needed * ratio if is_virtual else qty_needed

        item_preferred_wh = item_d.get("item_warehouse_id") or preferred_wh_id
        stocks = stocks_by_product.get(stock_product.id, [])

        preferred_stock = next((s for s in stocks if s.warehouse_id == item_preferred_wh), None) if item_preferred_wh else None

        if preferred_stock:
            selected_stock = preferred_stock
        elif item_preferred_wh:
            from app.models.inventory import StockLevel as _SL2
            new_sl = _SL2(product_id=stock_product.id, warehouse_id=item_preferred_wh, quantity=Decimal("0"))
            db.add(new_sl)
            stocks.append(new_sl)
            stocks_by_product[stock_product.id] = stocks
            selected_stock = new_sl
        elif stocks:
            selected_stock = max(stocks, key=lambda s: s.quantity)
        else:
            from app.models.inventory import StockLevel as _SL2
            new_sl = _SL2(product_id=stock_product.id, warehouse_id=None, quantity=Decimal("0"))
            db.add(new_sl)
            stocks = [new_sl]
            stocks_by_product[stock_product.id] = stocks
            selected_stock = new_sl

        item_warehouse_id = selected_stock.warehouse_id
        qty_before = selected_stock.quantity
        selected_stock.quantity -= qty_to_deduct

        from app.models.inventory import StockMovement, MovementType
        new_movements.append(StockMovement(
            product_id=stock_product.id,
            type=MovementType.OUT,
            qty_before=qty_before,
            qty_after=selected_stock.quantity,
            quantity=qty_to_deduct,
            reference_type="sale",
            reference_id=sale.id,
            user_id=current_user.id,
            reason=f"Sotuv #{sale.number}" + (f" ({product.name} → {stock_product.name} x{ratio})" if is_virtual else ""),
        ))

        batches = batches_by_product.get(stock_product.id, [])
        remaining = qty_to_deduct
        total_cost = Decimal("0")
        allocated_batches = []
        for batch in batches:
            if remaining <= 0:
                break
            qty_from = min(remaining, batch.quantity)
            batch.quantity -= qty_from
            remaining -= qty_from
            cost = qty_from * (batch.purchase_price or Decimal("0"))
            total_cost += cost
            allocated_batches.append({"batch_id": batch.id, "quantity": qty_from, "unit_cost": batch.purchase_price or Decimal("0")})
        if remaining > 0:
            fallback = source_product.cost_price if is_virtual else product.cost_price
            total_cost += remaining * (fallback or Decimal("0"))

        exact_unit_cost = total_cost / qty_needed if qty_needed > 0 else Decimal("0")

        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            warehouse_id=item_warehouse_id,
            unit=product.unit or "dona",
            quantity=qty_needed,
            unit_price=item_d["unit_price"],
            cost_price=exact_unit_cost,
            discount=item_d["discount"],
            subtotal=item_d["subtotal"],
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

    log_action(
        db=db, action="SALE", entity_type="sale", entity_id=sale.id,
        user_id=current_user.id,
        new_values={"number": sale.number, "total": str(total_amount), "payment": data.payment_type.value},
        ip_address=ip,
    )
    db.commit()

    # ── Telegram notification ─────────────────────────────────────────────────
    if getattr(data, "customer_id", None):
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).first()
        if customer and getattr(customer, "tg_chat_id", None):
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
                            _sale = (
                                _db.query(_Sale)
                                .options(_jl(_Sale.items).joinedload(_SI.product), _jl(_Sale.payments))
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

                            receipt = (
                                f"🧾 <b>Sotuv cheki</b>\n\n"
                                f"Mijoz: {cust_name}\n"
                                f"💴 Savdodan oldingi balans: som {FMT(prev_debt)}\n"
                                f"💰 Hozirgi balans: som {FMT(new_debt)}\n"
                                f"Savdo: #{_sale.number}\n"
                                f"Mahsulotlar:\n" + "\n".join(item_lines) +
                                f"\nTashkilot: {comp_name}\n"
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
) -> Sale:
    """Ulgurji sotuv — to'lovsiz (pending). Stock va tranzaksiyalarga tegmaydi."""
    if data.warehouse_id is None:
        from app.models.warehouse import Warehouse
        wh_q = db.query(Warehouse).filter(
            Warehouse.company_id == current_user.company_id,
            Warehouse.is_active == True,
        )
        if current_user.branch_id:
            wh = wh_q.filter(Warehouse.branch_id == current_user.branch_id).first()
            if wh:
                data.warehouse_id = wh.id
        if not data.warehouse_id:
            wh = wh_q.first()
            if wh:
                data.warehouse_id = wh.id

    sale_items_data = []
    total_amount = Decimal("0")

    for item_data in data.items:
        product = db.query(Product).filter(
            Product.id == item_data.product_id,
            Product.company_id == current_user.company_id,
            Product.is_deleted == False,
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Mahsulot ID={item_data.product_id} topilmadi")

        _customer_price = None
        _customer = None
        if data.customer_id:
            _customer_price = db.query(CustomerPrice).filter(
                CustomerPrice.customer_id == data.customer_id,
                CustomerPrice.product_id == item_data.product_id,
            ).first()
            _customer = db.query(Customer).filter(Customer.id == data.customer_id).first()

        unit_price = resolve_price(item_data, product, _customer_price, _customer)
        discount = item_data.discount
        subtotal = max(Decimal("0"), (unit_price * item_data.quantity) - discount)

        conversion = db.query(ProductConversion).filter(
            ProductConversion.sell_product_id == product.id
        ).first()
        cost_price = product.cost_price
        if conversion:
            source = db.query(Product).filter(Product.id == conversion.source_product_id).first()
            if source:
                cost_price = (source.cost_price or Decimal("0")) * conversion.ratio

        sale_items_data.append({
            "product": product,
            "quantity": item_data.quantity,
            "unit_price": unit_price,
            "cost_price": cost_price,
            "discount": discount,
            "subtotal": subtotal,
        })
        total_amount += subtotal

    total_amount = max(Decimal("0"), total_amount - data.discount_amount)

    sale = Sale(
        number=generate_sale_number(db),
        cashier_id=current_user.id,
        company_id=current_user.company_id,
        warehouse_id=data.warehouse_id,
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
        ))

    log_action(
        db=db, action="SALE_PENDING", entity_type="sale", entity_id=sale.id,
        user_id=current_user.id,
        new_values={"number": sale.number, "total": str(total_amount), "status": "pending"},
        ip_address=ip,
    )
    db.commit()
    return sale
