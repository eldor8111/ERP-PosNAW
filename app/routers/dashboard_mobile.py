from fastapi import APIRouter, Depends  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func  # type: ignore
from datetime import datetime, date

from app.database import get_db  # type: ignore
from app.core.dependencies import require_roles  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.sale import Sale, SaleItem  # type: ignore

router = APIRouter(prefix="/mobile/dashboard", tags=["Mobile Dashboard"])

@router.get("/summary")
def get_mobile_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    today = date.today()
    
    # Bugungi kunlik savdo 
    today_sales_query = db.query(func.sum(Sale.total_amount)).filter(
        func.date(Sale.created_at) == today
    )
    today_sales = today_sales_query.scalar() or 0
    
    # Kassadagi jami pul 
    total_paid_query = db.query(func.sum(Sale.paid_amount)).filter(
        func.date(Sale.created_at) == today
    )
    cash_in_register = total_paid_query.scalar() or 0
    
    # Qarzga berilgan
    debt_sales = db.query(func.sum(Sale.total_amount - Sale.paid_amount)).filter(
        func.date(Sale.created_at) == today,
        Sale.total_amount > Sale.paid_amount
    ).scalar() or 0

    return {
        "today_sales": float(today_sales),
        "cash_in_register": float(cash_in_register),
        "debt_sales": float(debt_sales)
    }

@router.get("/top-products")
def get_top_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    # Eng ko'p sotilgan 10 ta mahsulot
    top_items = db.query(
        SaleItem.product_id,
        func.sum(SaleItem.quantity).label("total_qty")
    ).group_by(SaleItem.product_id).order_by(
        func.sum(SaleItem.quantity).desc()
    ).limit(10).all()

    # Mahsulot ma'lumotlarini bazadan join o'rniga oddiy qilib olish
    from app.models.product import Product  # type: ignore
    result = []
    for item in top_items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
             result.append({
                 "id": product.id,
                 "name": product.name,
                 "sold_quantity": float(item.total_qty)
             })

    return result
