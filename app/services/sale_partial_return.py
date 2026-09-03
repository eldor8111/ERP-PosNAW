from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.audit import log_action
from app.models.sale import Sale, SaleItem, SaleStatus, PaymentType
from app.models.customer import Customer
from app.models.user import User
from app.models.moliya import Transaction, KassaMovement, Wallet
from app.schemas.sale import SaleReturnRequest
from app.services.inventory_service import receive_stock
from app.services.sale_helpers import generate_return_number, resolve_branch_id
import datetime

def process_partial_return(
    db: Session,
    sale_id: int,
    data: SaleReturnRequest,
    current_user: User,
    ip: Optional[str] = None,
) -> Sale:
    original_sale = db.query(Sale).filter(Sale.id == sale_id, Sale.company_id == current_user.company_id).first()
    if not original_sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")
    if original_sale.status in (SaleStatus.refunded, SaleStatus.cancelled):
        raise HTTPException(status_code=400, detail="Bekor qilingan yoki to'liq qaytarilgan sotuvdan tovar qaytarib bo'lmaydi")

    total_refund_amount = Decimal("0")
    returned_items_info = []
    new_sale_items = []

    # 1. Barcha so'ralgan tovarlarni tekshiramiz va qaytaramiz
    for ret_item in data.items:
        sale_item = db.query(SaleItem).filter(
            SaleItem.id == ret_item.sale_item_id,
            SaleItem.sale_id == original_sale.id
        ).first()
        if not sale_item:
            raise HTTPException(status_code=404, detail=f"Sotuv elementi topilmadi: {ret_item.sale_item_id}")
        
        qty_to_return = Decimal(str(ret_item.quantity))
        qty_available = sale_item.quantity - getattr(sale_item, 'returned_quantity', Decimal("0"))
        if qty_to_return <= 0 or qty_to_return > qty_available:
            raise HTTPException(status_code=400, detail=f"Qaytarish miqdori noto'g'ri (Mavjud: {qty_available})")

        actual_price = sale_item.subtotal / sale_item.quantity
        refund_value = actual_price * qty_to_return
        total_refund_amount += refund_value

        # Asl sale_item da faqatgina returned_quantity ni oshiramiz (double return oldini olish uchun)
        sale_item.returned_quantity = getattr(sale_item, 'returned_quantity', Decimal("0")) + qty_to_return
        
        returned_items_info.append(f"{sale_item.product.name} ({qty_to_return} ta)")
        
        # Yangi return document (Sale) uchun item yaratamiz
        new_sale_items.append({
            'product_id': sale_item.product_id,
            'quantity': qty_to_return,
            'unit_price': sale_item.unit_price,
            'cost_price': sale_item.cost_price,
            'discount': sale_item.discount,
            'subtotal': refund_value,
            'product': sale_item.product
        })

    # 2. Yangi Return hujjatini (Sale ob'ektini) yaratamiz
    sale_currency = original_sale.currency.code if original_sale.currency else "UZS"
    exchange_rate = Decimal(str(original_sale.exchange_rate or "1.0"))
    
    amount_to_return_cash = total_refund_amount if data.payment_type == PaymentType.cash else Decimal("0")
    amount_to_reduce_debt = total_refund_amount if data.payment_type == PaymentType.debt else Decimal("0")
    
    return_sale = Sale(
        number=generate_return_number(db),
        cashier_id=current_user.id,
        company_id=current_user.company_id,
        warehouse_id=original_sale.warehouse_id,
        customer_id=original_sale.customer_id,
        total_amount=total_refund_amount,
        discount_amount=Decimal("0"),
        paid_amount=amount_to_return_cash,
        paid_cash=amount_to_return_cash if data.payment_type == PaymentType.cash else Decimal("0"),
        paid_card=Decimal("0"), # Hozircha partial return modalida faqat naqd/qarz bor
        payment_type=data.payment_type,
        status=SaleStatus.refunded,
        note=f"Qisman qaytarish (Sotuv #{original_sale.number})",
        currency_id=original_sale.currency_id,
        exchange_rate=exchange_rate,
        loyalty_points_earned=0,
        loyalty_points_used=0,
    )
    db.add(return_sale)
    db.flush() # return_sale.id ni olish uchun
    
    # 3. Yangi SaleItem larni bazaga yozish va Stockni yangilash
    for item_data in new_sale_items:
        db.add(SaleItem(
            sale_id=return_sale.id,
            product_id=item_data['product_id'],
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price'],
            cost_price=item_data['cost_price'],
            discount=item_data['discount'],
            subtotal=item_data['subtotal']
        ))
        
        product = item_data['product']
        if product and product.product_type != "service":
            receive_stock(
                db=db,
                product_id=item_data['product_id'],
                quantity=item_data['quantity'],
                user_id=current_user.id,
                reason=f"Qisman qaytarish (Sotuv #{original_sale.number})",
                reference_type="sale_refund",
                reference_id=return_sale.id,
                warehouse_id=original_sale.warehouse_id,
                purchase_price=item_data['cost_price'],
                company_id=current_user.company_id,
            )

    # 4. Moliya / Qarzni to'g'rilash (Yangi return hujjatiga bog'langan holda)
    customer = None
    if original_sale.customer_id:
        customer = db.query(Customer).filter(Customer.id == original_sale.customer_id).with_for_update().first()
        
    if amount_to_reduce_debt > 0 and customer:
        # Mijoz qarz balansini kamaytirish
        customer.debt_balance = max(Decimal("0"), (customer.debt_balance or Decimal("0")) - (amount_to_reduce_debt * exchange_rate))
        if customer.debt_balances and float(customer.debt_balances.get(sale_currency, 0)) > 0:
            cur_debt = Decimal(str(customer.debt_balances[sale_currency]))
            customer.debt_balances[sale_currency] = float(max(Decimal("0"), cur_debt - amount_to_reduce_debt))
            flag_modified(customer, "debt_balances")
        
        # Original sotuvning paid_amount ni oshirish va statusini yangilash
        original_paid = Decimal(str(original_sale.paid_amount or "0"))
        original_total = Decimal(str(original_sale.total_amount or "0"))
        new_paid = min(original_total, original_paid + (amount_to_reduce_debt * exchange_rate))
        original_sale.paid_amount = new_paid  # type: ignore
        # Agar to'liq to'langan bo'lsa statusni yangilash
        if new_paid >= original_total:
            original_sale.status = SaleStatus.partial_refund  # type: ignore
        # debt_amounts ni ham yangilash
        if original_sale.debt_amounts and sale_currency in (original_sale.debt_amounts or {}):
            cur_sale_debt = Decimal(str(original_sale.debt_amounts[sale_currency]))
            original_sale.debt_amounts[sale_currency] = float(max(Decimal("0"), cur_sale_debt - amount_to_reduce_debt))
            flag_modified(original_sale, "debt_amounts")
            
    if amount_to_return_cash > 0:
        tx_branch_id = resolve_branch_id(db, current_user, original_sale.warehouse_id)
        _w = db.query(Wallet).filter(
            Wallet.company_id == current_user.company_id,
            Wallet.is_open == True,
            Wallet.is_active == True
        ).first()
        wallet_id = _w.id if _w else None
        
        if wallet_id:
            from app.models.moliya import WalletBalance
            if _w.balance is not None:
                _w.balance = Decimal(str(_w.balance)) - amount_to_return_cash
            else:
                _w.balance = -amount_to_return_cash
            
            wb = db.query(WalletBalance).filter(
                WalletBalance.wallet_id == wallet_id,
                WalletBalance.payment_type == data.payment_type.value
            ).first()
            if wb:
                wb.balance = Decimal(str(wb.balance or 0)) - amount_to_return_cash
            else:
                wb = WalletBalance(wallet_id=wallet_id, payment_type=data.payment_type.value, balance=-amount_to_return_cash)
                db.add(wb)

            db.add(Transaction(
                company_id=current_user.company_id,
                branch_id=tx_branch_id,
                wallet_id=wallet_id,
                type="expense",
                amount=amount_to_return_cash,
                currency_code=sale_currency,
                payment_type=data.payment_type.value,
                reference_type="sale_refund",
                reference_id=return_sale.id,
                description=f"Qisman qaytarish (Sotuv #{original_sale.number})"
            ))

    log_action(db, "RETURN_ITEMS", "sale", return_sale.id, current_user.id, {"items": returned_items_info, "amount": float(total_refund_amount), "original_sale_id": original_sale.id})
    
    db.commit()
    db.refresh(original_sale)
    return original_sale
