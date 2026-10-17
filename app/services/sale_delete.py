from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.inventory import MovementType, StockMovement
from app.models.moliya import Transaction
from app.models.sale import Sale, SaleStatus
from app.models.user import User, UserRole
from app.services import approval_service  # T4.6: o'chirish limiti va tasdiqlash
from app.services.customer_service import lock_customer
from app.services.sale_cash import reverse_sale_payments
from app.services.sale_helpers import apply_sale_branch_filter
from app.services.sale_stock import (
    _movement_warehouse, _stock_row, is_return_linked, restore_sale_batches, restore_sale_stock,
)

CANNOT_DELETE_RETURNED = "Qaytarish bilan bog'liq sotuvni o'chirib bo'lmaydi"


def _restore_sale_stock_with_storno(db: Session, sale: Sale, user_id: int) -> None:
    """T1.19: sotuv o'chirilganda qoldiq qaytariladi, lekin asl `StockMovement(reference_type="sale")`
    qatorlari O'CHIRILMAYDI — ustiga teskari `IN` harakat (reference_type="sale_delete_revert") yoziladi.
    Qoldiq aynan chiqqan ombor va variant qatoriga nisbiy (`+=`) qaytadi (restore_sale_stock bilan bir xil)."""
    from app.models.sale import SaleItem

    items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()
    movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "sale",
        StockMovement.reference_id == sale.id,
    ).order_by(StockMovement.id.asc()).all()
    for movement in movements:
        wh_id = _movement_warehouse(db, sale, movement, items)
        stock = _stock_row(db, movement.product_id, wh_id, movement.variant_id)
        qty = Decimal(str(movement.quantity or 0))
        qty_before = Decimal(str(stock.quantity or 0))
        stock.quantity = qty_before + qty
        db.add(StockMovement(
            product_id=movement.product_id,
            variant_id=movement.variant_id,
            warehouse_id=wh_id,
            type=MovementType.IN,
            qty_before=qty_before,
            qty_after=stock.quantity,
            quantity=qty,
            reference_type="sale_delete_revert",
            reference_id=sale.id,
            user_id=user_id,
            reason=f"Sotuv #{sale.number} o'chirildi (storno)",
        ))
    db.flush()


def cancel_sale_effects(db: Session, sale: Sale, current_user: User, locked_customer=None,
                        keep_movement_history: bool = False) -> None:
    """Sotuvning barcha ta'sirlarini teskari qiladi (sotuv qatori o'chirilmaydi):
    qoldiq (qator ombori va variant bo'yicha), partiyalar, mijoz qarzi/loyalligi,
    `Transaction(reference_type="sale")` va kassa (`KassaMovement`, `Wallet.balance`).

    `delete_sale` va `update_sale` (completed -> cancelled) bir xil funksiyadan foydalanadi.
    Qulf tartibi: mijoz (chaqiruvchida) -> qoldiq -> hamyon.
    """
    if keep_movement_history:
        _restore_sale_stock_with_storno(db, sale, current_user.id)
    else:
        restore_sale_stock(db, sale)
    restore_sale_batches(db, sale)

    # Mijoz qarz va loyallik qaytarish
    if locked_customer is not None:
        # Qarz + keshbek/ball/total_spent: sotuv paytida saqlangan qiymatlar bo'yicha (T2.12)
        from app.services.loyalty_service import restore_customer_debt, reverse_sale_loyalty
        restore_customer_debt(locked_customer, sale)
        reverse_sale_loyalty(locked_customer, sale)

    # Moliya: kirim tranzaksiyalari o'chiriladi (avvalgi xatti-harakat), kassa esa
    # teskari harakat bilan qaytariladi — eski KassaMovement audit uchun qoladi.
    for otx in db.query(Transaction).filter(
        Transaction.reference_type == "sale",
        Transaction.reference_id == sale.id,
        Transaction.type == "income",
    ).all():
        db.delete(otx)
    reverse_sale_payments(db, sale, current_user)


def delete_sale(db: Session, sale_id: int, current_user: User, approval_id=None) -> None:
    q = db.query(Sale).filter(Sale.id == sale_id)
    if current_user.role != UserRole.super_admin:
        q = q.filter(Sale.company_id == current_user.company_id)
    q = apply_sale_branch_filter(q, db, current_user)
    # Parallel ikki o'chirish so'rovidan faqat bittasi bajarilsin (qator qulfi)
    sale = q.with_for_update().first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sotuv topilmadi")
    if sale.status == SaleStatus.cancelled:
        raise HTTPException(status_code=400, detail="Sotuv allaqachon bekor qilingan")
    # Qaytarish hujjati yoki qaytarilgan sotuv: o'chirish qoldiq va pulni ikki marta hisoblaydi
    if is_return_linked(db, sale):
        raise HTTPException(status_code=400, detail=CANNOT_DELETE_RETURNED)

    # T4.6: sotuvni o'chirish limiti (qoida yo'q bo'lsa o'zgarmaydi; admin/director ozod, faqat audit).
    # Tasdiq bo'lsa `approval_id` (router `X-Approval-Id` sarlavhasidan uzatadi) bir marta ishlatiladi.
    _consumed_approval = approval_service.enforce(
        db, current_user,
        [v for v in [approval_service.evaluate_sale_delete(db, current_user, sale.total_amount, sale.branch_id)] if v],
        payload=approval_service.sale_delete_payload(sale.id), amount=sale.total_amount, branch_id=sale.branch_id,
        approval_id=approval_id,
    )
    approval_service.link_reference(_consumed_approval, "sale", sale.id)

    # T0.26: mijoz qatori eng avval qulflanadi (qulf tartibi: mijoz -> qoldiq -> hamyon).
    # Arxivlangan mijozning eski sotuvini ham o'chirish mumkin (allow_inactive).
    locked_customer = None
    if sale.customer_id and sale.status != SaleStatus.pending:
        locked_customer = lock_customer(
            db, sale.customer_id, sale.company_id, allow_inactive=True, required=False,
        )

    from app.services.sale_delivery_service import cancel_sale_delivery
    cancel_sale_delivery(db, sale.id, "Sotuv bekor qilindi")
    if getattr(sale, "agent_id", None) and sale.status == SaleStatus.pending:
        from app.services.mobile_service import push_to_user
        push_to_user(db, sale.agent_id, "❌ Buyurtma rad etildi", f"#{sale.number}", {"type": "order", "sale_id": sale.id})

    # T1.19: o'chirishda harakatlar tarixi saqlanadi (storno), update oqimi avvalgidek
    cancel_sale_effects(db, sale, current_user, locked_customer, keep_movement_history=True)

    log_action(
        db=db, action="SALE_DELETE", entity_type="sale", entity_id=sale.id,
        user_id=current_user.id, company_id=sale.company_id,
        new_values={"number": sale.number, "total": str(sale.total_amount)},
    )

    db.delete(sale)
    db.commit()
