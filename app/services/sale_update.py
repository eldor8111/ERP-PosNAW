from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.audit import log_action
from app.models.customer import Customer
from app.models.customer_prices import CustomerPrice
from app.models.moliya import Transaction
from app.models.product import Product, ProductConversion
from app.models.sale import Sale, SaleItem, SaleStatus, PaymentType
from app.models.user import User, UserRole
from app.services.inventory_service import deduct_stock
from app.services.sale_helpers import resolve_price, resolve_branch_id


def _reverse_sale_effects(db: Session, sale: Sale) -> None:
    """Sotuvning barcha moliyaviy ta'sirlarini bekor qilish."""
    from app.models.inventory import StockMovement, StockLevel
    from app.models.sale import SaleItemBatch, SalePayment
    from app.models.batch import Batch

    old_movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "sale",
        StockMovement.reference_id == sale.id,
    ).all()
    for movement in old_movements:
        stock = db.query(StockLevel).filter(
            StockLevel.product_id == movement.product_id,
            StockLevel.warehouse_id == sale.warehouse_id,
        ).first()
        if not stock:
            stock = db.query(StockLevel).filter(
                StockLevel.product_id == movement.product_id,
                StockLevel.warehouse_id == None,
            ).first()
        if not stock:
            stock = StockLevel(
                product_id=movement.product_id,
                warehouse_id=sale.warehouse_id,
                quantity=Decimal("0"),
            )
            db.add(stock)
        stock.quantity += movement.quantity  # type: ignore
        db.delete(movement)

    for item in sale.items:
        for sib in db.query(SaleItemBatch).filter(SaleItemBatch.sale_item_id == item.id).all():
            batch = db.query(Batch).filter(Batch.id == sib.batch_id).first()
            if batch:
                batch.quantity += sib.quantity  # type: ignore
            db.delete(sib)

    if sale.customer_id and sale.status != SaleStatus.pending:
        customer = db.query(Customer).filter(
            Customer.id == sale.customer_id,
            Customer.company_id == sale.company_id,
        ).first()
        if customer:
            from app.services.loyalty_service import restore_customer_after_sale
            restore_customer_after_sale(customer, sale)

    for otx in db.query(Transaction).filter(
        Transaction.reference_type == "sale",
        Transaction.reference_id == sale.id,
        Transaction.type == "income",
    ).all():
        db.delete(otx)

    db.query(SaleItemBatch).filter(
        SaleItemBatch.sale_item_id.in_([i.id for i in sale.items])
    )

    from app.models.sale import SalePayment
    db.query(SalePayment).filter(SalePayment.sale_id == sale.id).delete()

    for item in list(sale.items):  # type: ignore
        db.delete(item)

    db.flush()


def update_sale(db: Session, sale_id: int, data, current_user: User) -> Sale:
    """Sotuvni yangilash: holat/izoh yoki to'liq tahrirlash (items bilan)."""
    q = (
        db.query(Sale)
        .options(joinedload(Sale.items), joinedload(Sale.payments))
        .filter(Sale.id == sale_id)
    )
    if current_user.role != UserRole.super_admin:
        q = q.filter(Sale.company_id == current_user.company_id)
    sale = q.first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")

    if data.items is not None:
        # ── To'liq tahrirlash ─────────────────────────────────────────────────
        old_paid_amount = Decimal(str(sale.paid_amount or 0))
        old_payment_type = sale.payment_type
        old_paid_cash = Decimal(str(sale.paid_cash or 0))
        old_paid_card = Decimal(str(sale.paid_card or 0))

        _reverse_sale_effects(db, sale)

        wh_id = data.warehouse_id if data.warehouse_id is not None else sale.warehouse_id
        disc_amount = data.discount_amount if data.discount_amount is not None else Decimal("0")
        payment_type = data.payment_type if data.payment_type is not None else old_payment_type
        new_customer_id = data.customer_id if data.customer_id is not None else sale.customer_id

        sale_items_data = []
        total_amount = Decimal("0")

        for item_d in data.items:
            product = db.query(Product).filter(
                Product.id == item_d.product_id,
                Product.company_id == current_user.company_id,
                Product.is_deleted == False,
            ).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Mahsulot ID={item_d.product_id} topilmadi")

            _customer_price = None
            _customer = None
            if new_customer_id:
                _customer_price = db.query(CustomerPrice).filter(
                    CustomerPrice.customer_id == new_customer_id,
                    CustomerPrice.product_id == item_d.product_id,
                ).first()
                _customer = db.query(Customer).filter(Customer.id == new_customer_id).first()

            unit_price = resolve_price(item_d, product, _customer_price, _customer)
            discount = item_d.discount
            subtotal = (unit_price * item_d.quantity) - discount
            
            item_currency_code = getattr(item_d, "currency_code", "UZS")
            item_exchange_rate = getattr(item_d, "exchange_rate", Decimal("1.0"))

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
                "quantity": item_d.quantity,
                "unit_price": unit_price,
                "cost_price": cost_price,
                "discount": discount,
                "subtotal": subtotal,
                "currency_code": item_currency_code,
                "exchange_rate": item_exchange_rate,
                "item_warehouse_id": getattr(item_d, "warehouse_id", None),
            })
            total_amount += (subtotal * item_exchange_rate)

        total_amount = max(Decimal("0"), total_amount - disc_amount)
        paid_amount = data.paid_amount if data.paid_amount is not None else old_paid_amount
        paid_cash = data.paid_cash if data.paid_cash is not None else old_paid_cash
        paid_card = data.paid_card if data.paid_card is not None else old_paid_card

        final_status = data.status if data.status is not None else sale.status

        for sid in sale_items_data:
            item_wh = sid.get("item_warehouse_id") or wh_id
            db.add(SaleItem(
                sale_id=sale.id,
                product_id=sid["product"].id,
                quantity=sid["quantity"],
                unit_price=sid["unit_price"],
                cost_price=sid["cost_price"],
                discount=sid["discount"],
                subtotal=sid["subtotal"],
                currency_code=sid["currency_code"],
                exchange_rate=sid["exchange_rate"],
                warehouse_id=item_wh,
                unit=sid["product"].unit or "dona",
            ))
            if final_status != SaleStatus.pending:
                from app.utils.product_conversion import deduct_target_for_sale
                deduct_id, deduct_qty, conv, src = deduct_target_for_sale(
                    db, sid["product"].id, Decimal(str(sid["quantity"]))
                )
                reason = f"Sotuv tahrirlash (sale #{sale_id})"
                if conv and src:
                    reason += f" ({sid['product'].name} → {src.name} x{conv.ratio})"
                deduct_stock(
                    db=db, product_id=deduct_id, quantity=deduct_qty,
                    user_id=current_user.id, reason=reason,  # type: ignore
                    reference_type="sale", reference_id=sale_id,
                    warehouse_id=item_wh, allow_negative=True,  # type: ignore
                )

        if new_customer_id and final_status != SaleStatus.pending:
            new_customer = db.query(Customer).filter(
                Customer.id == new_customer_id,
                Customer.company_id == current_user.company_id,
            ).first()
            if new_customer:
                new_debt = max(Decimal("0"), (total_amount - paid_amount) * (sale.exchange_rate or Decimal("1")))
                if new_debt > 0:
                    new_customer.debt_balance = (new_customer.debt_balance or Decimal("0")) + new_debt  # type: ignore

                    # Sync with multi-currency debt_balances
                    if not new_customer.debt_balances:
                        new_customer.debt_balances = {}  # type: ignore
                    
                    if hasattr(data, "currency_totals") and data.currency_totals:
                        for curr_code, curr_debt in data.currency_totals.items():
                            curr_val = float(new_customer.debt_balances.get(curr_code, 0))
                            new_customer.debt_balances[curr_code] = curr_val + float(curr_debt)
                    else:
                        sale_currency = "UZS"
                        if sale.currency_id:
                            from app.models.currency import Currency
                            curr_obj = db.query(Currency).filter(Currency.id == sale.currency_id).first()
                            if curr_obj:
                                sale_currency = curr_obj.code
                                
                        curr_val = float(new_customer.debt_balances.get(sale_currency, 0))
                        # Note: we need to use the raw debt without exchange rate multiplication for the specific currency
                        raw_debt = max(Decimal("0"), total_amount - paid_amount)
                        new_customer.debt_balances[sale_currency] = curr_val + float(raw_debt)

                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(new_customer, "debt_balances")

                exr = sale.exchange_rate or Decimal("1")
                if getattr(new_customer, "cashback_percent", 0) > 0:
                    cashback = (total_amount * exr * new_customer.cashback_percent) / Decimal("100")
                    new_customer.bonus_balance = (new_customer.bonus_balance or Decimal("0")) + cashback  # type: ignore
                new_customer.total_spent = (new_customer.total_spent or Decimal("0")) + (total_amount * exr)  # type: ignore
                loyalty_earned = int((total_amount * exr) * Decimal("0.01"))  # type: ignore
                new_customer.loyalty_points = (new_customer.loyalty_points or 0) + loyalty_earned  # type: ignore
                sale.loyalty_points_earned = loyalty_earned  # type: ignore
            sale.loyalty_points_used = 0  # type: ignore

        if final_status != SaleStatus.pending:
            tx_branch_id = resolve_branch_id(db, current_user, wh_id)
            from app.models.sale import SalePayment as _SP
            if data.payments and len(data.payments) > 0:
                for p in data.payments:
                    if p.amount > 0:
                        p_rate = Decimal(str(getattr(p, "rate", 1.0) or 1.0))
                        p_amount_uzs = p.amount * p_rate
                        
                        db.add(_SP(sale_id=sale.id, payment_type=p.type.value, amount=p_amount_uzs))
                        if tx_branch_id:
                            _p_currency = (getattr(p, "currency", "UZS") or "UZS").upper()
                            _tx_amount = p.amount if _p_currency != "UZS" else p_amount_uzs
                            db.add(Transaction(
                                branch_id=tx_branch_id, company_id=current_user.company_id,
                                type="income", amount=_tx_amount, payment_type=p.type.value,
                                currency_code=_p_currency,
                                reference_type="sale", reference_id=sale.id,
                                description=f"Sotuv tahrirlash #{sale.number} ({p.type.value})" + (f" ({p.amount} {_p_currency})" if _p_currency != "UZS" else ""),
                                created_at=sale.created_at,
                            ))
            elif paid_amount > 0:
                db.add(_SP(sale_id=sale.id, payment_type=payment_type.value, amount=paid_amount))
                if tx_branch_id:
                    db.add(Transaction(
                        branch_id=tx_branch_id, company_id=current_user.company_id,
                        type="income", amount=paid_amount, payment_type=payment_type.value,
                        currency_code="UZS",
                        reference_type="sale", reference_id=sale.id,
                        description=f"Sotuv tahrirlash #{sale.number}",
                        created_at=sale.created_at,
                    ))

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
        if data.status is not None:
            sale.status = data.status
        if data.note is not None:
            sale.note = data.note
        if data.paid_amount is not None:
            if sale.customer_id:
                customer = db.query(Customer).filter(Customer.id == sale.customer_id).first()
                if customer:
                    old_debt = (sale.total_amount - sale.paid_amount) * (sale.exchange_rate or Decimal("1"))
                    new_debt = (sale.total_amount - data.paid_amount) * (sale.exchange_rate or Decimal("1"))
                    if old_status == SaleStatus.pending and sale.status != SaleStatus.pending:
                        if new_debt > 0:
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

                    elif old_status != SaleStatus.pending and sale.status == SaleStatus.pending:
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

                    elif old_status != SaleStatus.pending and sale.status != SaleStatus.pending:
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

        if data.paid_amount is None and old_status == SaleStatus.pending and sale.status != SaleStatus.pending:
            if sale.customer_id:
                customer = db.query(Customer).filter(Customer.id == sale.customer_id).first()
                if customer:
                    remaining_debt = (sale.total_amount - sale.paid_amount) * (sale.exchange_rate or Decimal("1"))
                    if remaining_debt > 0:
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

        if old_status == SaleStatus.pending and sale.status != SaleStatus.pending:
            from app.utils.product_conversion import deduct_target_for_sale
            for item in sale.items:
                deduct_id, deduct_qty, conv, src = deduct_target_for_sale(db, item.product_id, item.quantity)
                reason = f"Sotuv tasdiqlandi (sale #{sale.id})"
                if conv and src:
                    reason += f" ({item.product.name} → {src.name} x{conv.ratio})"
                deduct_stock(
                    db=db, product_id=deduct_id, quantity=deduct_qty,
                    user_id=current_user.id, reason=reason,  # type: ignore
                    reference_type="sale", reference_id=sale.id,  # type: ignore
                    warehouse_id=sale.warehouse_id, allow_negative=True,  # type: ignore
                )
        elif old_status != SaleStatus.pending and sale.status == SaleStatus.pending:
            from app.models.inventory import StockMovement, StockLevel
            for movement in db.query(StockMovement).filter(
                StockMovement.reference_type == "sale",
                StockMovement.reference_id == sale.id,
            ).all():
                stock = db.query(StockLevel).filter(
                    StockLevel.product_id == movement.product_id,
                    StockLevel.warehouse_id == sale.warehouse_id,
                ).first()
                if stock:
                    stock.quantity = movement.qty_before
                db.delete(movement)

    log_action(
        db=db, action="SALE_UPDATE", entity_type="sale", entity_id=sale.id,  # type: ignore
        user_id=current_user.id,  # type: ignore
        new_values={"status": str(sale.status), "paid": str(sale.paid_amount)},
    )
    db.commit()
    return sale
