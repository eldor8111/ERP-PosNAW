from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.batch import Batch
from app.models.customer_prices import CustomerPrice
from app.models.moliya import Transaction
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

    # Mijoz qarzi qaytarish
    if data.customer_id:
        from app.models.customer import Customer
        customer = db.query(Customer).filter(
            Customer.id == data.customer_id,
            Customer.company_id == current_user.company_id,
        ).with_for_update().first()
        if not customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
        if data.paid_amount < total_amount:
            debt_amount = total_amount - data.paid_amount
            customer.debt_balance = max(Decimal("0"), customer.debt_balance - debt_amount)

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
        exchange_rate=1,
        loyalty_points_earned=0,
        loyalty_points_used=0,
    )
    db.add(sale)
    db.flush()

    # Pul qaytarilsa — expense tranzaksiya
    if data.paid_amount > 0:
        tx_branch_id = resolve_branch_id(db, current_user, data.warehouse_id)
        if tx_branch_id:
            if data.payment_type == PaymentType.mixed:
                for _pt, _amt in [("cash", data.paid_cash), ("card", data.paid_card)]:
                    if _amt > 0:
                        db.add(Transaction(
                            branch_id=tx_branch_id, company_id=current_user.company_id,
                            type="expense", amount=_amt, reference_type="sale_refund",
                            reference_id=sale.id,
                            description=f"Vazvrat to'lovi #{sale.number} (Aralash/{_pt})",
                        ))
            else:
                db.add(Transaction(
                    branch_id=tx_branch_id, company_id=current_user.company_id,
                    type="expense", amount=data.paid_amount,
                    reference_type="sale_refund", reference_id=sale.id,
                    description=f"Vazvrat to'lovi #{sale.number}",
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
