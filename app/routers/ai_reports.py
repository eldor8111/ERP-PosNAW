from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timedelta
import os
from cachetools import TTLCache

from app.database import get_db
from app.core.dependencies import require_roles
from app.models.user import User, UserRole
from app.models.company import Company
from app.models.sale import Sale, SaleItem
from app.models.product import Product
from app.utils.report_utils import (
    _date_range, local_today, day_sales_summary, sale_or_return_filter, doc_sign,
)
from app.models.inventory import StockLevel
from app.services.debt_scoring import categorize_customers
from app.services.openrouter_insights_service import generate_daily_insight
from app.services.ai_service import build_daily_report
from app.services.ai_scope import (
    resolve_ai_scope, scope_cache_part, scope_info, scope_label, scope_sale_filter,
)
from app.services.stock_report import low_stock_count_for_scope  # T2.3: yagona "kam qoldiq" ta'rifi

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
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """
    Kompaniyaning bugungi moliyaviy holatini umumiylashtirib AI orqali chiroyli matnga aylantirib beradi.
    Multi-tenant xavfsizligi ta'minlangan (Faqat tokendagi company_id bo'yicha).
    `?branch_id=` - filial doirasi (T2.9); kesh filial bo'yicha ajratilgan.
    """
    today = local_today()
    company_id = current_user.company_id
    scope = resolve_ai_scope(db, current_user, branch_id)
    sale_flt = scope_sale_filter(scope)
    info = scope_info(scope)
    cache_key = f"daily_insight_{company_id}_{scope_cache_part(scope)}_{today}"
    
    # 1. Kesh tekshirish (1 soat ichida so'ralsa yana AI ni chaqirmaslik)
    if cache_key in cache:
        return {"report": cache[cache_key], "cached": True, "type": "ai", "scope": info}
        
    company = db.query(Company).filter(Company.id == company_id).first()
    company_name = company.name if company else "Korxona"
    ai_company_name = f"{company_name} ({scope_label(scope)})" if scope is not None else company_name
    
    # 2. XAVFSIZ AGREGATSIYA (Faqat joriy korxona bo'yicha)
    yesterday = today - timedelta(days=1)
    
    # Bugungi sotuvlar — sof tushum (qaytarishlar ayirilgan), UZS
    summary = day_sales_summary(db, company_id, today, sale_filter=sale_flt)
    total_sales = summary["net"]
    cash = summary["cash"]
    card = summary["card"]
    debt_added = summary["debt"]
    sales_count = summary["count"]

    # Kechagi bilan solishtirish (growth)
    yest_total = day_sales_summary(db, company_id, yesterday, sale_filter=sale_flt)["net"]
    growth_pct = ((total_sales - yest_total) / yest_total * 100) if yest_total > 0 else 0.0

    # Top 3 mahsulot (faqat nomlari, ID yo'q)
    start, end = _date_range(today, today)
    net_qty = func.sum(doc_sign() * SaleItem.quantity)
    top_q = (
        db.query(Product.name)
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.created_at >= start,
            Sale.created_at < end,
            Sale.company_id == company_id,
            sale_or_return_filter(),
        )
    )
    if sale_flt is not None:
        top_q = top_q.filter(sale_flt)
    top_products_db = (
        top_q.group_by(Product.id, Product.name)
        .order_by(net_qty.desc())
        .limit(3)
        .all()
    )
    top_products = [p[0] for p in top_products_db]
    
    # Zaxira (mahsulotlar soni, doiradagi omborlar bo'yicha) va Qarz (T2.6 gacha butun korxona)
    low_stock_total = low_stock_count_for_scope(db, company_id, scope)
    
    try:
        debt_data = categorize_customers(db, company_id)
        overdue_count = debt_data.get("overdue_count", 0)
    except Exception:
        overdue_count = 0
        
    # 3. AI API ni chaqirish
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    ai_report = generate_daily_insight(
        company_name=ai_company_name,
        total_sales=total_sales,
        sales_count=sales_count,
        cash=cash,
        card=card,
        debt_added=debt_added,
        growth_pct=growth_pct,
        low_stock_count=low_stock_total,
        overdue_count=overdue_count,
        top_products=top_products,
        api_key=api_key
    )
    
    # 4. FALLBACK mexanizmi (Agar AI server qulagan bo'lsa yoki API limit tugasa)
    if not ai_report:
        # Eski statik shablonni qaytaramiz (lekin xatosiz ishlashda davom etadi)
        fallback_report = build_daily_report(db, company_id, company_name, scope)
        # Fallback uchun HTML taglarni olib tashlaymiz mobil ko'rinish uchun
        import re
        clean_fallback = re.sub(r"<[^>]+>", "", fallback_report)
        return {"report": clean_fallback, "cached": False, "type": "fallback_static", "scope": info}
        
    # AI muvaffaqiyatli ishlasa keshga saqlaymiz
    cache[cache_key] = ai_report
    
    return {"report": ai_report, "cached": False, "type": "ai", "scope": info}
