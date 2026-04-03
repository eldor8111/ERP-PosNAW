from fastapi import APIRouter, Depends  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func  # type: ignore
from datetime import datetime, date

from app.database import get_db  # type: ignore
from app.core.dependencies import require_roles  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.sale import Sale, SaleItem  # type: ignore
from app.models.product import Product  # type: ignore

router = APIRouter(prefix="/mobile/dashboard", tags=["Mobile Dashboard"])

@router.get("/summary")
def get_mobile_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    today = date.today()
    base = db.query(Sale).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == current_user.company_id
    )
    today_sales    = base.with_entities(func.coalesce(func.sum(Sale.total_amount), 0)).scalar() or 0
    cash_in_register = base.with_entities(func.coalesce(func.sum(Sale.paid_amount), 0)).scalar() or 0
    debt_sales = db.query(
        func.coalesce(func.sum(Sale.total_amount - Sale.paid_amount), 0)
    ).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == current_user.company_id,
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
    """Eng ko'p sotilgan 10 ta mahsulot — JOIN bilan bir so'rovda"""
    rows = (
        db.query(
            Product.id,
            Product.name,
            func.coalesce(func.sum(SaleItem.quantity), 0).label("total_qty")
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.company_id == current_user.company_id,
            Product.company_id == current_user.company_id,
        )
        .group_by(Product.id, Product.name)
        .order_by(func.sum(SaleItem.quantity).desc())
        .limit(10)
        .all()
    )
    return [
        {"id": r.id, "name": r.name, "sold_quantity": float(r.total_qty)}
        for r in rows
    ]
