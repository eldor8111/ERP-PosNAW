from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.moliya import Transaction
from app.models.sale import Sale, SaleStatus
from app.models.user import User, UserRole
from app.services.sale_helpers import resolve_branch_id


def delete_sale(db: Session, sale_id: int, current_user: User) -> None:
    from app.models.inventory import StockMovement, StockLevel
    from app.models.sale import SaleItemBatch
    from app.models.batch import Batch

    q = db.query(Sale).filter(Sale.id == sale_id)
    if current_user.role != UserRole.super_admin:
        q = q.filter(Sale.company_id == current_user.company_id)
    sale = q.first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")
    if sale.status == SaleStatus.cancelled:
        raise HTTPException(status_code=400, detail="Sotuv allaqachon bekor qilingan")

    # Stock harakatlarini teskari bekor qilish
    for movement in db.query(StockMovement).filter(
        StockMovement.reference_type == "sale",
        StockMovement.reference_id == sale.id,
    ).all():
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
        stock.quantity += movement.quantity
        db.delete(movement)

    # FIFO Batch larni tiklash
    for item in sale.items:
        for sib in db.query(SaleItemBatch).filter(SaleItemBatch.sale_item_id == item.id).all():
            batch = db.query(Batch).filter(Batch.id == sib.batch_id).first()
            if batch:
                batch.quantity += sib.quantity
            db.delete(sib)

    # Mijoz qarz va loyallik qaytarish
    if sale.customer_id and sale.status != SaleStatus.pending:
        from app.models.customer import Customer
        customer = db.query(Customer).filter(
            Customer.id == sale.customer_id,
            Customer.company_id == sale.company_id,
        ).first()
        if customer:
            from app.services.loyalty_service import restore_customer_after_sale
            restore_customer_after_sale(customer, sale)

    # Moliya tranzaksiyalarini qaytarish
    if sale.paid_amount > 0:
        old_transactions = db.query(Transaction).filter(
            Transaction.reference_type == "sale",
            Transaction.reference_id == sale.id,
            Transaction.type == "income",
        ).all()
        if old_transactions:
            for otx in old_transactions:
                db.delete(otx)
        else:
            tx_branch_id = resolve_branch_id(db, current_user, sale.warehouse_id)
            if tx_branch_id:
                db.add(Transaction(
                    branch_id=tx_branch_id,
                    company_id=current_user.company_id,
                    type="expense",
                    amount=sale.paid_amount,
                    reference_type="sale_refund",
                    reference_id=sale.id,
                    description=f"Sotuv bekor qilish #{sale.number}",
                ))

    log_action(
        db=db, action="SALE_DELETE", entity_type="sale", entity_id=sale.id,
        user_id=current_user.id,
        new_values={"number": sale.number, "total": str(sale.total_amount)},
    )

    db.delete(sale)
    db.commit()
