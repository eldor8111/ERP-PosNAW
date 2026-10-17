"""
Sotuv hisobotlari: kunlik, top mahsulotlar, kassir, ABC/XYZ, 1C eksport.
reports.py dan ajratilgan. Umumiy qoidalar → app/utils/report_utils.py
"""
import csv
import io
import re
from datetime import date, timedelta
from typing import Optional
from xml.sax.saxutils import quoteattr

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, case, cast, Date as DateType
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import company_scope_by_key_or_roles, require_roles
from app.core.report_scope import ReportScope, report_scope_dep, report_scope_key_or_user_dep
from app.core.roles import REPORT_ROLES
from app.database import get_db
from app.models.product import Product
from app.models.branch import Branch
from app.models.sale import Sale, SaleItem
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.utils.report_utils import (
    _date_range, local_today,
    is_return_doc, sale_doc_filter, sale_or_return_filter, doc_sign,
    sale_rate, item_revenue_uzs, item_cost_uzs,
    sale_branch_filter, currency_code_map,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


def _sale_filters(db: Session, company_id: int, date_from, date_to, branch_id, doc_filter):
    start, end = _date_range(date_from, date_to)
    filters = [Sale.company_id == company_id, Sale.created_at >= start, Sale.created_at < end, doc_filter]
    # T1.9: filial — sotuv snapshot'i (Sale.branch_id), ombor hozirgi filiali emas
    br_filter = sale_branch_filter(branch_id)
    if br_filter is not None:
        filters.append(br_filter)
    return filters


def _sale_branch_name(sale) -> str:
    """Sotuv filiali nomi: snapshot (`Sale.branch_id`), bo'lmasa ombor filiali; filialsiz — bo'sh."""
    if sale.branch is not None:
        return sale.branch.name or ""
    wh = sale.warehouse
    if wh is not None and wh.branch is not None:
        return wh.branch.name or ""
    return ""


def _ascii_slug(text: str) -> str:
    """Fayl nomi uchun xavfsiz qism (Content-Disposition ASCII bo'lishi kerak)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_")


def _export_filename_stem(db: Session, company_id: int, date_from, date_to, branch_id) -> str:
    """`1c_export_{date_from}_{date_to}[_{filial}]` (T2.5). Sana berilmasa: all / bugungi sana."""
    parts = ["1c_export", date_from.isoformat() if date_from else "all",
             date_to.isoformat() if date_to else local_today().isoformat()]
    if branch_id:
        if branch_id == -1:  # UNASSIGNED_BRANCH
            parts.append("filialsiz")
        else:
            name = db.query(Branch.name).filter(Branch.id == branch_id, Branch.company_id == company_id).scalar()
            parts.append(_ascii_slug(name) or f"b{branch_id}")
    return "_".join(parts)


@router.get("/daily-sales")
def daily_sales_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Kunlik sotuv hisoboti (sotuv valyutasi bo'yicha, qaytarishlar ayirilgan)"""
    cid = current_user.company_id
    branch_id = scope.branch_id  # T2.1: cheklangan menejer uchun majburan o'z filiali
    filters = _sale_filters(db, cid, date_from, date_to, branch_id, sale_or_return_filter())
    day = cast(Sale.created_at, DateType)
    rows = (
        db.query(
            day.label("day"),
            Sale.currency_id,
            func.sum(case((is_return_doc(), 0), else_=1)).label("sales_count"),
            func.sum(case((is_return_doc(), 1), else_=0)).label("returns_count"),
            func.coalesce(func.sum(case((is_return_doc(), 0), else_=Sale.total_amount / sale_rate())), 0).label("sales_amount"),
            func.coalesce(func.sum(case((is_return_doc(), Sale.total_amount / sale_rate()), else_=0)), 0).label("returns_amount"),
            func.coalesce(func.sum(case((is_return_doc(), 0), else_=Sale.discount_amount / sale_rate())), 0).label("discount"),
        )
        .filter(*filters)
        .group_by(day, Sale.currency_id)
        .order_by(day.desc())
        .all()
    )

    codes = currency_code_map(db, cid)
    day_map = {}
    for r in rows:
        d = str(r.day)
        entry = day_map.setdefault(d, {
            "date": d, "sales_count": 0, "returns_count": 0,
            "total_amount": {}, "total_discount": {}, "avg_check": {}, "_sales": {}, "_cnt": {},
        })
        code = codes.get(r.currency_id, "UZS") if r.currency_id else "UZS"
        entry["sales_count"] += int(r.sales_count or 0)
        entry["returns_count"] += int(r.returns_count or 0)
        net = float(r.sales_amount or 0) - float(r.returns_amount or 0)
        entry["total_amount"][code] = round(entry["total_amount"].get(code, 0.0) + net, 2)
        entry["total_discount"][code] = round(entry["total_discount"].get(code, 0.0) + float(r.discount or 0), 2)
        entry["_sales"][code] = entry["_sales"].get(code, 0.0) + float(r.sales_amount or 0)
        entry["_cnt"][code] = entry["_cnt"].get(code, 0) + int(r.sales_count or 0)

    for entry in day_map.values():
        for code, cnt in entry["_cnt"].items():
            entry["avg_check"][code] = round(entry["_sales"][code] / cnt, 2) if cnt else 0.0
        entry.pop("_sales")
        entry.pop("_cnt")
    return list(day_map.values())


@router.get("/top-products")
def top_products_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Eng ko'p sotilgan mahsulotlar (UZS, qaytarishlar ayirilgan)"""
    cid = current_user.company_id
    branch_id = scope.branch_id  # T2.1: cheklangan menejer uchun majburan o'z filiali
    filters = _sale_filters(db, cid, date_from, date_to, branch_id, sale_or_return_filter())
    revenue = func.sum(doc_sign() * item_revenue_uzs())
    rows = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            func.sum(doc_sign() * SaleItem.quantity).label("total_qty"),
            revenue.label("total_revenue"),
            func.sum(doc_sign() * (item_revenue_uzs() - item_cost_uzs())).label("total_profit"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(*filters)
        .group_by(Product.id, Product.name, Product.sku)
        .order_by(revenue.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "rank": idx + 1,
            "product_id": r.id,
            "product_name": r.name,
            "sku": r.sku,
            "total_qty": float(r.total_qty or 0),
            "total_revenue": round(float(r.total_revenue or 0), 2),
            "total_profit": round(float(r.total_profit or 0), 2),
        }
        for idx, r in enumerate(rows)
    ]


@router.get("/cashier-report")
def cashier_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Kassir bo'yicha sotuv hisoboti (sotuv valyutasi bo'yicha, qaytarishlar ayirilgan)"""
    cid = current_user.company_id
    branch_id = scope.branch_id  # T2.1: cheklangan menejer uchun majburan o'z filiali
    filters = _sale_filters(db, cid, date_from, date_to, branch_id, sale_or_return_filter())
    rows = (
        db.query(
            User.id,
            User.name,
            Sale.currency_id,
            func.sum(case((is_return_doc(), 0), else_=1)).label("sales_count"),
            func.sum(case((is_return_doc(), 1), else_=0)).label("returns_count"),
            func.coalesce(func.sum(case((is_return_doc(), 0), else_=Sale.total_amount / sale_rate())), 0).label("sales_amount"),
            func.coalesce(func.sum(case((is_return_doc(), Sale.total_amount / sale_rate()), else_=0)), 0).label("returns_amount"),
            func.coalesce(func.sum(case((is_return_doc(), 0), else_=Sale.discount_amount / sale_rate())), 0).label("discount"),
            func.coalesce(func.sum(doc_sign() * Sale.total_amount), 0).label("net_uzs"),
        )
        .join(Sale, Sale.cashier_id == User.id)
        .filter(*filters)
        .group_by(User.id, User.name, Sale.currency_id)
        .all()
    )

    codes = currency_code_map(db, cid)
    cashier_map = {}
    for r in rows:
        entry = cashier_map.setdefault(r.id, {
            "cashier_id": r.id,
            "cashier_name": r.name,
            "sales_count": 0,
            "returns_count": 0,
            "total_amount": {},
            "returns_amount": {},
            "total_discount": {},
            "avg_check": {},
            "_sales": {}, "_cnt": {}, "_net_uzs": 0.0,
        })
        code = codes.get(r.currency_id, "UZS") if r.currency_id else "UZS"
        sales_amount = float(r.sales_amount or 0)
        returns_amount = float(r.returns_amount or 0)
        entry["sales_count"] += int(r.sales_count or 0)
        entry["returns_count"] += int(r.returns_count or 0)
        entry["total_amount"][code] = round(entry["total_amount"].get(code, 0.0) + sales_amount - returns_amount, 2)
        if returns_amount:
            entry["returns_amount"][code] = round(entry["returns_amount"].get(code, 0.0) + returns_amount, 2)
        entry["total_discount"][code] = round(entry["total_discount"].get(code, 0.0) + float(r.discount or 0), 2)
        entry["_sales"][code] = entry["_sales"].get(code, 0.0) + sales_amount
        entry["_cnt"][code] = entry["_cnt"].get(code, 0) + int(r.sales_count or 0)
        entry["_net_uzs"] += float(r.net_uzs or 0)

    result = sorted(cashier_map.values(), key=lambda e: e["_net_uzs"], reverse=True)
    for entry in result:
        for code, cnt in entry["_cnt"].items():
            if cnt:
                entry["avg_check"][code] = round(entry["_sales"][code] / cnt, 2)
        entry.pop("_sales")
        entry.pop("_cnt")
        entry.pop("_net_uzs")
    return result


@router.get("/abc-xyz")
def abc_xyz_analysis(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """ABC/XYZ tahlil — mahsulotlarni tushum (UZS, qaytarishlar ayirilgan) va
    xarid chastotasiga (nechta chekda uchragani) ko'ra guruhlash"""
    cid = current_user.company_id
    branch_id = scope.branch_id  # T2.1: cheklangan menejer uchun majburan o'z filiali
    filters = _sale_filters(db, cid, date_from, date_to, branch_id, sale_or_return_filter())
    rows = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            func.sum(doc_sign() * item_revenue_uzs()).label("revenue"),
            func.count(func.distinct(case((is_return_doc(), None), else_=Sale.id))).label("frequency"),
            func.sum(doc_sign() * SaleItem.quantity).label("qty"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(*filters)
        .group_by(Product.id, Product.name, Product.sku)
        .all()
    )
    if not rows:
        return []

    revenue = {r.id: max(float(r.revenue or 0), 0.0) for r in rows}
    total_revenue = sum(revenue.values())
    sorted_rows = sorted(rows, key=lambda r: revenue[r.id], reverse=True)

    # Mahsulot o'zidan OLDINGI jamg'arma ulushga qarab sinflanadi — aks holda
    # yagona yirik mahsulot (masalan 100%) "C" bo'lib qolardi.
    abc_map = {}
    cumulative = 0.0
    for r in sorted_rows:
        share_before = cumulative
        cumulative += (revenue[r.id] / total_revenue * 100) if total_revenue else 0.0
        if revenue[r.id] <= 0:
            abc_map[r.id] = "C"
        elif share_before < 80:
            abc_map[r.id] = "A"
        elif share_before < 95:
            abc_map[r.id] = "B"
        else:
            abc_map[r.id] = "C"

    max_freq = max(int(r.frequency or 0) for r in rows) or 1
    xyz_map = {}
    for r in rows:
        ratio = int(r.frequency or 0) / max_freq
        xyz_map[r.id] = "X" if ratio >= 0.7 else ("Y" if ratio >= 0.4 else "Z")

    return [
        {
            "product_id": r.id,
            "product_name": r.name,
            "sku": r.sku,
            "revenue": round(float(r.revenue or 0), 2),
            "frequency": int(r.frequency or 0),
            "qty": float(r.qty or 0),
            "abc": abc_map[r.id],
            "xyz": xyz_map[r.id],
            "group": f"{abc_map[r.id]}{xyz_map[r.id]}",
        }
        for r in sorted_rows
    ]


@router.get("/1c-export")
def export_1c(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    include_returns: bool = Query(False, description="Qaytarish hujjatlarini ham (manfiy summa bilan) qo'shish"),
    format: str = Query("csv", enum=["csv", "xml"]),
    db: Session = Depends(get_db),
    cid: int = Depends(company_scope_by_key_or_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_key_or_user_dep),
):
    """1C Buxgalteriya uchun savdo ma'lumotlari eksporti (CSV yoki XML).
    Summalar UZS da. Oldingi ustunlar tartibi saqlangan, yangilari oxirida.
    Kirish: `Authorization: Bearer` (REPORT_ROLES) YOKI `X-API-Key` (faqat o'z korxonasi, faqat o'qish)."""
    branch_id = scope.branch_id  # T2.1: cheklangan menejer uchun majburan o'z filiali (API kalit — korxona darajasida)
    doc_filter = sale_or_return_filter() if include_returns else sale_doc_filter()
    filters = _sale_filters(db, cid, date_from, date_to, branch_id, doc_filter)
    sales = (
        db.query(Sale, User)
        .options(
            joinedload(Sale.currency),
            joinedload(Sale.branch),
            joinedload(Sale.warehouse).joinedload(Warehouse.branch),
            joinedload(Sale.customer),
        )
        .join(User, User.id == Sale.cashier_id)
        .filter(*filters)
        .order_by(Sale.created_at)
        .all()
    )

    def _row(s, u):
        is_return = (s.number or "").startswith("R")
        return {
            "number": s.number,
            "created_at": s.created_at,
            "cashier": u.name or "",
            "total": (-1 if is_return else 1) * float(s.total_amount or 0),
            "discount": float(s.discount_amount or 0),
            "payment": s.payment_type.value if s.payment_type else "",
            "currency": s.currency.code if s.currency else "UZS",
            "rate": float(s.exchange_rate or 1),
            "type": "return" if is_return else "sale",
            # T2.5: ombor / filial / mijoz (1C hujjatlarni omborlarga taqsimlashi uchun)
            "warehouse": s.warehouse.name if s.warehouse else "",
            "branch": _sale_branch_name(s),
            "customer": s.customer.name if s.customer else "",
        }

    filename_stem = _export_filename_stem(db, cid, date_from, date_to, branch_id)

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(["Raqam", "Sana", "Kassir", "Jami summa", "Chegirma", "To'lov turi", "Valyuta", "Kurs", "Turi",
                         "Ombor", "Filial", "Mijoz"])
        for s, u in sales:
            r = _row(s, u)
            writer.writerow([
                r["number"],
                r["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                r["cashier"],
                f"{r['total']:.2f}",
                f"{r['discount']:.2f}",
                r["payment"],
                r["currency"],
                f"{r['rate']:.2f}",
                "Qaytarish" if r["type"] == "return" else "Sotuv",
                r["warehouse"],
                r["branch"],
                r["customer"],
            ])
        return Response(
            content=buf.getvalue().encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename_stem}.csv"},
        )

    start, end = _date_range(date_from, date_to)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append(f'<Sales date_from="{start.date()}" date_to="{(end - timedelta(days=1)).date()}">')
    for s, u in sales:
        r = _row(s, u)
        attrs = {
            "number": r["number"],
            "date": r["created_at"].strftime("%Y-%m-%d"),
            "time": r["created_at"].strftime("%H:%M:%S"),
            "cashier": r["cashier"],
            "total": f"{r['total']:.2f}",
            "discount": f"{r['discount']:.2f}",
            "payment": r["payment"],
            "currency": r["currency"],
            "rate": f"{r['rate']:.2f}",
            "type": r["type"],
            "warehouse": r["warehouse"],
            "branch": r["branch"],
            "customer": r["customer"],
        }
        lines.append("  <Sale " + " ".join(f"{k}={quoteattr(str(v))}" for k, v in attrs.items()) + "/>")
    lines.append("</Sales>")
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={filename_stem}.xml"},
    )
