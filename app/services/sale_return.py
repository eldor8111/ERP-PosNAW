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
from app.models.moliya import Transaction, KassaMovement, Wallet
from app.models.product import Product, ProductConversion
from app.models.sale import Sale, SaleItem, SaleStatus, PaymentType
from app.models.user import User
from app.schemas.sale import SaleCreate
from app.services.inventory_service import receive_stock
from app.services.sale_helpers import generate_return_number, resolve_branch_id


def create_return_sale(
    db: Session,
    data: SaleCreate,
    current_user: User,
    ip: Optional[str] = None,
) -> Sale:
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
        _customer_price = None
        if data.customer_id:
            _customer_price = db.query(CustomerPrice).filter(
                CustomerPrice.customer_id == data.customer_id,
                CustomerPrice.product_id == item_d.product_id,
            ).first()

        price = (
            Decimal(str(item_d.unit_price)) if item_d.unit_price is not None
            else (Decimal(str(_customer_price.price)) if _customer_price else product.sale_price)
        )
        discount = Decimal(str(item_d.discount))
        subtotal = (price - discount) * qty
        total_amount += subtotal

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
            "quantity": qty,
            "unit_price": price,
            "discount": discount,
            "subtotal": subtotal,
            "cost_price": cost_price,
        })

    total_amount = max(Decimal("0"), total_amount - data.discount_amount)

    # Valyuta va kurs aniqlash
    currency = None
    exchange_rate = Decimal("1")
    if data.currency_id:
        currency = db.query(Currency).filter(Currency.id == data.currency_id).first()
        if currency:
            exchange_rate = currency.rate

    # ─── Mijoz qarz mantig'i ─────────────────────────────────────────────────
    # Qaytarishda:
    #   payment_type = "debt"   → barcha tovar qiymati qarzdan ayiriladi (naqd berilmaydi)
    #   payment_type = "cash"   → paid_amount kassadan chiqariladi (mijoz naqd oladi)
    #   Qisman to'lov           → paid_amount naqd, qolgan (total - paid) qarzdan ayiriladi
    # ─────────────────────────────────────────────────────────────────────────
    if data.customer_id:
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).with_for_update().first()
        if not customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")

        # Qarzdan ayiriladigan qism: qarzga yopilgan vazvrat uchun
        # "debt" to'lov turida paid_amount = 0, debt_reduction = total_amount
        # Naqd to'lovda paid_amount = total_amount, debt_reduction = 0
        _paid = data.paid_amount
        if data.payment_type == PaymentType.debt:
            # Qarzga yopiladigan vazvrat: kassaga hech narsa berilmaydi
            _paid = Decimal("0")

        debt_reduction = (total_amount - _paid) * exchange_rate

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
                actual_debt_in_currency = total_amount - _paid
                sale_currency = currency.code if currency else "UZS"
                curr_val = float(customer.debt_balances.get(sale_currency, 0))
                customer.debt_balances[sale_currency] = max(0, curr_val - float(actual_debt_in_currency))

            flag_modified(customer, "debt_balances")

        # Kassa uchun asl paid_amount ni qayta belgilash
        # debt tipida paid_amount 0 bo'lishi kerak
        if data.payment_type == PaymentType.debt:
            data = data.model_copy(update={"paid_amount": Decimal("0"), "paid_cash": Decimal("0"), "paid_card": Decimal("0")})

    sale = Sale(
        number=generate_return_number(db),
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
    )
    db.add(sale)
    db.flush()

    # Pul qaytarilsa — expense tranzaksiya
    if data.paid_amount > 0:
        tx_branch_id = resolve_branch_id(db, current_user, data.warehouse_id)
        wallet = None
        if data.wallet_id:
            wallet = db.query(Wallet).filter(
                Wallet.id == data.wallet_id,
                Wallet.company_id == current_user.company_id
            ).first()
        if not wallet:
            wallet = db.query(Wallet).filter(
                Wallet.company_id == current_user.company_id,
                Wallet.is_open == True,
                Wallet.is_active == True,
            ).order_by(Wallet.id.asc()).first()

        if wallet:
            wallet.balance = Decimal(str(wallet.balance or 0)) - Decimal(str(data.paid_amount))

        open_session_id = None
        if wallet:
            from app.models.moliya import KassaSession as _KS
            _ks = db.query(_KS).filter(_KS.wallet_id == wallet.id, _KS.status == "open").first()
            if _ks:
                open_session_id = _ks.id

        if tx_branch_id:
            if data.payment_type == PaymentType.mixed:
                for _pt, _amt in [("cash", data.paid_cash), ("card", data.paid_card)]:
                    if _amt > 0:
                        db.add(Transaction(
                            branch_id=tx_branch_id, company_id=current_user.company_id,
                            wallet_id=wallet.id if wallet else None,
                            type="expense", amount=_amt, reference_type="sale_refund",
                            reference_id=sale.id, payment_type=_pt,
                            description=f"Vazvrat to'lovi #{sale.number} (Aralash/{_pt})",
                        ))
                        if wallet and _pt not in ("debt", "cashback"):
                            db.add(KassaMovement(
                                wallet_id=wallet.id, company_id=current_user.company_id,
                                session_id=open_session_id,
                                direction="out", payment_type=_pt, amount=_amt,
                                reference_type="sale_refund", reference_id=sale.id,
                                description=f"Vazvrat #{sale.number} (Aralash/{_pt})",
                                created_by=current_user.id,
                            ))
            else:
                db.add(Transaction(
                    branch_id=tx_branch_id, company_id=current_user.company_id,
                    wallet_id=wallet.id if wallet else None,
                    type="expense", amount=data.paid_amount, payment_type=data.payment_type.value,
                    reference_type="sale_refund", reference_id=sale.id,
                    description=f"Vazvrat to'lovi #{sale.number}",
                ))
                if wallet and data.payment_type.value not in ("debt", "cashback"):
                    db.add(KassaMovement(
                        wallet_id=wallet.id, company_id=current_user.company_id,
                        session_id=open_session_id,
                        direction="out", payment_type=data.payment_type.value, amount=data.paid_amount,
                        reference_type="sale_refund", reference_id=sale.id,
                        description=f"Vazvrat #{sale.number}",
                        created_by=current_user.id,
                    ))

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
            )
            db.add(Batch(
                product_id=product.id, warehouse_id=data.warehouse_id,
                lot_number=f"RETURN-{sale.number}", initial_quantity=qty_needed, quantity=qty_needed,
                purchase_price=product.cost_price, company_id=current_user.company_id,
            ))

        db.add(SaleItem(
            sale_id=sale.id, product_id=product.id, quantity=qty_needed,
            unit_price=item_d["unit_price"], cost_price=item_d["cost_price"],
            discount=item_d["discount"], subtotal=item_d["subtotal"],
        ))

    log_action(
        db=db, action="SALE_RETURN", entity_type="sale", entity_id=sale.id,
        user_id=current_user.id, ip_address=ip,
    )
    db.commit()
    db.refresh(sale)
    return sale
