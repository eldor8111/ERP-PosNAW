from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import date, timedelta
import os
from cachetools import TTLCache

from app.database import get_db
from app.core.dependencies import require_roles
from app.models.user import User, UserRole
from app.models.company import Company
from app.models.sale import Sale, SaleItem, PaymentType, SaleStatus
from app.models.product import Product
from app.models.inventory import StockLevel
from app.services.debt_scoring import categorize_customers
from app.services.bytez_insights_service import generate_daily_insight
from app.services.ai_service import build_daily_report

router = APIRouter(prefix="/ai/reports", tags=["AI Reports"])

# Bitta kompaniya hisobotini kuniga bitta marta AI orqali keshlab olamiz (Byudjetni tejash uchun - 1 soat)
cache = TTLCache(maxsize=100, ttl=3600)

def _sf(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0

@router.get("/daily-insight")
def get_daily_insight(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """
    Kompaniyaning bugungi moliyaviy holatini umumiylashtirib AI orqali chiroyli matnga aylantirib beradi.
    Multi-tenant xavfsizligi ta'minlangan (Faqat tokendagi company_id bo'yicha).
    """
    today = date.today()
    company_id = current_user.company_id
    cache_key = f"daily_insight_{company_id}_{today}"
    
    # 1. Kesh tekshirish (1 soat ichida so'ralsa yana AI ni chaqirmaslik)
    if cache_key in cache:
        return {"report": cache[cache_key], "cached": True, "type": "ai"}
        
    company = db.query(Company).filter(Company.id == company_id).first()
    company_name = company.name if company else "Korxona"
    
    # 2. XAVFSIZ AGREGATSIYA (Faqat joriy korxona bo'yicha)
    yesterday = today - timedelta(days=1)
    
    # Bugungi sotuvlar
    sales = db.query(Sale).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == company_id,
        Sale.status == SaleStatus.completed
    ).all()
    
    total_sales = sum(_sf(s.total_amount) for s in sales)
    cash = sum(_sf(s.paid_cash) for s in sales)
    card = sum(_sf(s.paid_card) for s in sales)
    debt_sales = [s for s in sales if s.payment_type == PaymentType.debt]
    debt_added = sum(_sf(s.total_amount) - _sf(s.paid_amount) for s in debt_sales)
    sales_count = len(sales)
    
    # Kechagi bilan solishtirish (growth)
    yest_total = _sf(
        db.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(
            func.date(Sale.created_at) == yesterday,
            Sale.company_id == company_id,
            Sale.status == SaleStatus.completed
        ).scalar()
    )
    growth_pct = ((total_sales - yest_total) / yest_total * 100) if yest_total > 0 else 0.0
    
    # Top 3 mahsulot (faqat nomlari, ID yo'q)
    top_products_db = (
        db.query(Product.name)
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            func.date(Sale.created_at) == today,
            Sale.company_id == company_id,
            Sale.status == SaleStatus.completed
        )
        .group_by(Product.name)
        .order_by(desc(func.sum(SaleItem.quantity)))
        .limit(3)
        .all()
    )
    top_products = [p[0] for p in top_products_db]
    
    # Zaxira va Qarz (Umumiy agregat)
    low_stock_count = db.query(StockLevel).filter(
        StockLevel.quantity < 10,
        StockLevel.warehouse.has(company_id=company_id)
    ).count()
    
    try:
        debt_data = categorize_customers(db, company_id)
        overdue_count = debt_data.get("overdue_count", 0)
    except Exception:
        overdue_count = 0
        
    # 3. AI API ni chaqirish
    api_key = os.getenv("BYTEZ_API_KEY", "42444b53b260f17105d68352fe7e9b3f")
    ai_report = generate_daily_insight(
        company_name=company_name,
        total_sales=total_sales,
        sales_count=sales_count,
        cash=cash,
        card=card,
        debt_added=debt_added,
        growth_pct=growth_pct,
        low_stock_count=low_stock_count,
        overdue_count=overdue_count,
        top_products=top_products,
        api_key=api_key
    )
    
    # 4. FALLBACK mexanizmi (Agar AI server qulagan bo'lsa yoki API limit tugasa)
    if not ai_report:
        # Eski statik shablonni qaytaramiz (lekin xatosiz ishlashda davom etadi)
        fallback_report = build_daily_report(db, company_id, company_name)
        # Fallback uchun HTML taglarni olib tashlaymiz mobil ko'rinish uchun
        import re
        clean_fallback = re.sub(r"<[^>]+>", "", fallback_report)
        return {"report": clean_fallback, "cached": False, "type": "fallback_static"}
        
    # AI muvaffaqiyatli ishlasa keshga saqlaymiz
    cache[cache_key] = ai_report
    
    return {"report": ai_report, "cached": False, "type": "ai"}
