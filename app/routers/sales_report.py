"""
Sotuv hisobotlari: kunlik, top mahsulotlar, kassir, ABC/XYZ, 1C eksport.
reports.py dan ajratilgan.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.product import Product
from app.models.currency import Currency
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.user import User, UserRole
from app.utils.report_utils import _date_range

router = APIRouter(prefix="/reports", tags=["Reports"])

REPORT_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.super_admin)


@router.get("/daily-sales")
def daily_sales_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Kunlik sotuv hisoboti (agregatsiya)"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(
            func.date(Sale.created_at).label("day"),
            func.sum(case((Sale.status == SaleStatus.completed, 1), else_=0)).label("sales_count"),
            func.sum(case((Sale.status == SaleStatus.refunded, 1), else_=0)).label("returns_count"),
            func.coalesce(Currency.code, 'UZS').label("currency"),
            func.sum(
                case(
                    (Sale.status == SaleStatus.completed, Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)),
                    (Sale.status == SaleStatus.refunded, -Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)),
                    else_=0
                )
            ).label("total_amount"),
            func.sum(
                case(
                    (Sale.status == SaleStatus.completed, Sale.discount_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)),
                    (Sale.status == SaleStatus.refunded, -Sale.discount_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)),
                    else_=0
                )
            ).label("total_discount"),
            func.avg(
                case(
                    (Sale.status == SaleStatus.completed, Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)),
                    else_=None
                )
            ).label("avg_check"),
        )
        .select_from(Sale)
        .outerjoin(Currency, Currency.id == Sale.currency_id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status.in_([SaleStatus.completed, SaleStatus.refunded]))
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    rows = (
        q.group_by(func.date(Sale.created_at), func.coalesce(Currency.code, 'UZS'))
        .order_by(func.date(Sale.created_at).desc())
        .all()
    )
    
    # Merge currencies by date
    day_map = {}
    for r in rows:
        d = str(r.day)
        if d not in day_map:
            day_map[d] = {
                "date": d,
                "sales_count": 0,
                "returns_count": 0,
                "total_amount": {},
                "total_discount": {},
                "avg_check": {}
            }
        
        curr = r.currency
        day_map[d]["sales_count"] += (r.sales_count or 0)
        day_map[d]["returns_count"] += (r.returns_count or 0)
        day_map[d]["total_amount"][curr] = float(r.total_amount or 0)
        day_map[d]["total_discount"][curr] = float(r.total_discount or 0)
        day_map[d]["avg_check"][curr] = float(r.avg_check or 0)
        
    return list(day_map.values())


@router.get("/top-products")
def top_products_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Eng ko'p sotilgan mahsulotlar"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            func.sum(SaleItem.quantity).label("total_qty"),
            func.coalesce(SaleItem.currency_code, 'UZS').label("currency"),
            func.sum(SaleItem.subtotal).label("total_revenue"),
            func.sum((SaleItem.unit_price - SaleItem.cost_price) * SaleItem.quantity).label("total_profit"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    rows = (
        q.group_by(Product.id, Product.name, Product.sku, func.coalesce(SaleItem.currency_code, 'UZS'))
        .order_by(func.sum(SaleItem.subtotal).desc())
        .limit(limit)
        .all()
    )
    
    # Merge currencies
    prod_map = {}
    for r in rows:
        pid = r.id
        if pid not in prod_map:
            prod_map[pid] = {
                "product_id": r.id,
                "product_name": r.name,
                "sku": r.sku,
                "total_qty": 0.0,
                "total_revenue": {},
                "total_profit": {}
            }
        
        curr = r.currency
        prod_map[pid]["total_qty"] += float(r.total_qty or 0)
        prod_map[pid]["total_revenue"][curr] = float(r.total_revenue or 0)
        prod_map[pid]["total_profit"][curr] = float(r.total_profit or 0)
        
    sorted_prods = sorted(prod_map.values(), key=lambda x: sum(x["total_revenue"].values()), reverse=True)[:limit]
    for idx, p in enumerate(sorted_prods):
        p["rank"] = idx + 1
        
    return sorted_prods


@router.get("/cashier-report")
def cashier_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Kassir bo'yicha sotuv hisoboti"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(
            User.id,
            User.name,
            func.sum(case((Sale.status == SaleStatus.completed, 1), else_=0)).label("sales_count"),
            func.sum(case((Sale.status == SaleStatus.refunded, 1), else_=0)).label("returns_count"),
            func.coalesce(Currency.code, 'UZS').label("currency"),
            func.coalesce(func.sum(
                case(
                    (Sale.status == SaleStatus.completed, Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)),
                    (Sale.status == SaleStatus.refunded, -Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)),
                    else_=0
                )
            ), 0).label("total_amount"),
            func.coalesce(func.sum(
                case(
                    (Sale.status == SaleStatus.completed, Sale.discount_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)),
                    (Sale.status == SaleStatus.refunded, -Sale.discount_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)),
                    else_=0
                )
            ), 0).label("total_discount"),
            func.coalesce(func.avg(
                case(
                    (Sale.status == SaleStatus.completed, Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)),
                    else_=None
                )
            ), 0).label("avg_check"),
        )
        .join(Sale, Sale.cashier_id == User.id)
        .outerjoin(Currency, Currency.id == Sale.currency_id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status.in_([SaleStatus.completed, SaleStatus.refunded]))
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    rows = (
        q.group_by(User.id, User.name, func.coalesce(Currency.code, 'UZS'))
        .order_by(func.sum(Sale.total_amount).desc())
        .all()
    )

    # Merge currencies
    cashier_map = {}
    for r in rows:
        cid = r.id
        if cid not in cashier_map:
            cashier_map[cid] = {
                "cashier_id": r.id,
                "cashier_name": r.name,
                "sales_count": 0,
                "returns_count": 0,
                "total_amount": {},
                "total_discount": {},
                "avg_check": {}
            }
        
        curr = r.currency
        cashier_map[cid]["sales_count"] += (r.sales_count or 0)
        cashier_map[cid]["returns_count"] += (r.returns_count or 0)
        cashier_map[cid]["total_amount"][curr] = float(r.total_amount or 0)
        cashier_map[cid]["total_discount"][curr] = float(r.total_discount or 0)
        cashier_map[cid]["avg_check"][curr] = float(r.avg_check or 0)
        
    return list(cashier_map.values())


@router.get("/abc-xyz")
def abc_xyz_analysis(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """ABC/XYZ tahlil — mahsulotlarni qiymat va chastotaga ko'ra guruhlash"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            func.sum(SaleItem.subtotal * func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)).label("revenue"),
            func.count(SaleItem.id).label("frequency"),
            func.sum(SaleItem.quantity).label("qty"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    rows = q.group_by(Product.id, Product.name, Product.sku).all()

    if not rows:
        return []

    total_revenue = sum(float(r.revenue or 0) for r in rows)
    sorted_rev = sorted(rows, key=lambda r: float(r.revenue or 0), reverse=True)
    cumulative = 0.0
    abc_map = {}
    for r in sorted_rev:
        cumulative += float(r.revenue or 0) / total_revenue * 100 if total_revenue else 0.0
        abc_map[r.id] = "A" if cumulative <= 80 else ("B" if cumulative <= 95 else "C")

    max_freq = max(r.frequency for r in rows) or 1
    xyz_map = {}
    for r in rows:
        ratio = r.frequency / max_freq
        xyz_map[r.id] = "X" if ratio >= 0.7 else ("Y" if ratio >= 0.4 else "Z")

    return [
        {
            "product_id": r.id,
            "product_name": r.name,
            "sku": r.sku,
            "revenue": float(r.revenue or 0),
            "frequency": r.frequency,
            "qty": float(r.qty or 0),
            "abc": abc_map.get(r.id, "C"),
            "xyz": xyz_map.get(r.id, "Z"),
            "group": f"{abc_map.get(r.id, 'C')}{xyz_map.get(r.id, 'Z')}",
        }
        for r in sorted_rev
    ]


@router.get("/1c-export")
def export_1c(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    format: str = Query("csv", enum=["csv", "xml"]),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """1C Buxgalteriya uchun savdo ma'lumotlari eksporti (CSV yoki XML)"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(Sale, User)
        .join(User, User.id == Sale.cashier_id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    sales = q.order_by(Sale.created_at).all()

    filename_date = date.today().isoformat()

    if format == "csv":
        lines = ["Raqam,Sana,Kassir,Jami summa,Chegirma,To'lov turi"]
        for s, u in sales:
            lines.append(
                f"{s.number},"
                f"{s.created_at.strftime('%Y-%m-%d %H:%M:%S')},"
                f"{u.name},"
                f"{float(s.total_amount):.2f},"
                f"{float(s.discount_amount):.2f},"
                f"{s.payment_type.value}"
            )
        content = "\n".join(lines)
        return Response(
            content=content.encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=1c_export_{filename_date}.csv"},
        )
    else:
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append(f'<Sales date_from="{start.date()}" date_to="{end.date()}">')
        for s, u in sales:
            lines.append(
                f'  <Sale number="{s.number}" '
                f'date="{s.created_at.strftime("%Y-%m-%d")}" '
                f'time="{s.created_at.strftime("%H:%M:%S")}" '
                f'cashier="{u.name}" '
                f'total="{float(s.total_amount):.2f}" '
                f'discount="{float(s.discount_amount):.2f}" '
                f'payment="{s.payment_type.value}"/>'
            )
        lines.append("</Sales>")
        content = "\n".join(lines)
        return Response(
            content=content.encode("utf-8"),
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename=1c_export_{filename_date}.xml"},
        )
