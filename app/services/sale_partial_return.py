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
    sale = db.query(Sale).filter(Sale.id == sale_id, Sale.company_id == current_user.company_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")
    if sale.status in (SaleStatus.refunded, SaleStatus.cancelled):
        raise HTTPException(status_code=400, detail="Bekor qilingan yoki to'liq qaytarilgan sotuvdan tovar qaytarib bo'lmaydi")

    total_refund_amount = Decimal("0")
    returned_items_info = []

    # Barcha so'ralgan tovarlarni tekshiramiz va qaytaramiz
    for ret_item in data.items:
        sale_item = db.query(SaleItem).filter(
            SaleItem.id == ret_item.sale_item_id,
            SaleItem.sale_id == sale.id
        ).first()
        if not sale_item:
            raise HTTPException(status_code=404, detail=f"Sotuv elementi topilmadi: {ret_item.sale_item_id}")
        
        qty_to_return = Decimal(str(ret_item.quantity))
        qty_available = sale_item.quantity - getattr(sale_item, 'returned_quantity', Decimal("0"))
        if qty_to_return <= 0 or qty_to_return > qty_available:
            raise HTTPException(status_code=400, detail=f"Qaytarish miqdori noto'g'ri (Mavjud: {qty_available})")

        # Qaytarilayotgan qiymatni hisoblaymiz (sotilgan narx va chegirma asosida)
        # sale_item.subtotal / sale_item.quantity = haqiqiy o'rtacha narx
        actual_price = sale_item.subtotal / sale_item.quantity
        refund_value = actual_price * qty_to_return
        total_refund_amount += refund_value

        # Element holatini yangilaymiz
        sale_item.returned_quantity = getattr(sale_item, 'returned_quantity', Decimal("0")) + qty_to_return
        
        # Omborga qaytarish (agar u xizmat bo'lmasa)
        if sale_item.product and sale_item.product.type != "service":
            receive_stock(
                db=db,
                product_id=sale_item.product_id,
                quantity=qty_to_return,
                user_id=current_user.id,
                reason=f"Qisman qaytarish (Sotuv #{sale.number})",
                reference_type="sale_return",
                reference_id=sale.id,
                warehouse_id=sale.warehouse_id,
                purchase_price=sale_item.cost_price,
                company_id=current_user.company_id
            )
        
        returned_items_info.append(f"{sale_item.product.name} ({qty_to_return} ta)")

    # ── Moliya / Qarzni to'g'rilash ──
    # Agar mijoz qarzga olgan bo'lsa, qarzdan chegiriladi, aks holda (yoki payment_type=cash/card) to'langan pul qaytarilishi kerak
    # Mijoz ob'yekti:
    customer = None
    if sale.customer_id:
        customer = db.query(Customer).filter(Customer.id == sale.customer_id).with_for_update().first()

    sale_currency = sale.currency.code if sale.currency else "UZS"
    exchange_rate = Decimal(str(sale.exchange_rate or "1.0"))
    
    # Qaytarilayotgan summani UZS dagi qiymati
    refund_amount_uzs = total_refund_amount * exchange_rate
    
    amount_to_return_cash = total_refund_amount
    amount_to_reduce_debt = Decimal("0")
    
    if data.payment_type == PaymentType.debt:
        amount_to_reduce_debt = total_refund_amount
        amount_to_return_cash = Decimal("0")
    elif data.payment_type == PaymentType.cash:
        amount_to_return_cash = total_refund_amount
        amount_to_reduce_debt = Decimal("0")
        
    if amount_to_reduce_debt > 0 and customer:
        customer.debt_balance = max(Decimal("0"), (customer.debt_balance or Decimal("0")) - (amount_to_reduce_debt * exchange_rate))
        if customer.debt_balances and float(customer.debt_balances.get(sale_currency, 0)) > 0:
            cur_debt = Decimal(str(customer.debt_balances[sale_currency]))
            customer.debt_balances[sale_currency] = float(max(Decimal("0"), cur_debt - amount_to_reduce_debt))
            flag_modified(customer, "debt_balances")
            
        # Sale'dagi qarz summasini yangilaymiz
        if sale.debt_amounts and float(sale.debt_amounts.get(sale_currency, 0)) > 0:
            cur_sale_debt = Decimal(str(sale.debt_amounts[sale_currency]))
            sale.debt_amounts[sale_currency] = float(max(Decimal("0"), cur_sale_debt - amount_to_reduce_debt))
            flag_modified(sale, "debt_amounts")

    if amount_to_return_cash > 0:
        # Puldor (kassa) dan pul qaytarish
        tx_branch_id = resolve_branch_id(db, current_user, sale.warehouse_id)
        from app.models.moliya import Wallet
        _w = db.query(Wallet).filter(
            Wallet.company_id == current_user.company_id,
            Wallet.is_open == True,
            Wallet.is_active == True
        ).first()
        wallet_id = _w.id if _w else None
        
        if wallet_id:
            db.add(Transaction(
                company_id=current_user.company_id,
                branch_id=tx_branch_id,
                wallet_id=wallet_id,
                type="expense",
                amount=amount_to_return_cash,
                currency_code=sale_currency,
                payment_type=data.payment_type.value,
                reference_type="sale_return",
                reference_id=sale.id,
                description=f"Tovar qaytarildi. Sotuv #{sale.number}"
            ))

    sale.status = SaleStatus.partial_refund
    sale.total_amount = max(Decimal("0"), sale.total_amount - total_refund_amount)
    
    # Qarz kamaysa paid_amount bir xil qolishi kerak (mijoz naqd pul olgani yo'q, qarzi kamaydi).
    # Lekin naqd pul qaytarilsa paid_amount kamayadi.
    if amount_to_return_cash > 0:
        sale.paid_amount = max(Decimal("0"), sale.paid_amount - amount_to_return_cash)

    log_action(db, "RETURN_ITEMS", "sale", sale.id, current_user.id, {"items": returned_items_info, "amount": float(total_refund_amount)})
    
    db.commit()
    return sale
