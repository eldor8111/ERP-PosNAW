from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.core.dependencies import require_roles
from app.models.user import User, UserRole
from app.models.sale import Sale, SaleStatus
from app.services.ai_service import (
    build_daily_context,
    call_gemini,
    get_insights,
    parse_copilot_intent,
    execute_copilot_action,
    build_daily_report,
)
from app.services.debt_scoring import categorize_customers

router = APIRouter(prefix="/ai", tags=["AI Analytics & Copilot"])


class ChatRequest(BaseModel):
    message: str


# ─── Status ──────────────────────────────────────────────────────────────

@router.get("/status")
def get_ai_status():
    """AI tizimi holati — Mahalliy AI faol, Gemini API kerak emas."""
    return {
        "status": "ok",
        "mode": "local",
        "message": "Mahalliy AI tizimi ishlayapti. Hech qanday tashqi API kerak emas.",
        "features": [
            "Kunlik savdo tahlili",
            "Haftalik tendensiya",
            "Zaxira va qarz holati",
            "Copilot chat (qarz to'lash / nasiya yozish)",
            "Har kuni soat 17:30 da Telegram hisoboti",
        ]
    }


# ─── Daily Summary ────────────────────────────────────────────────────────

@router.get("/daily-summary")
def get_daily_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """Bugungi kun xulosasi va mahalliy AI tahlili."""
    def sf(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    today = date.today()
    sales = db.query(Sale).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == current_user.company_id,
        Sale.status == SaleStatus.completed
    ).all()

    total_sales = sum(sf(s.total_amount) for s in sales)
    cash = sum(sf(s.paid_cash) for s in sales)
    card = sum(sf(s.paid_card) for s in sales)
    debt = sum(sf(s.total_amount) - sf(s.paid_amount) for s in sales)

    context = build_daily_context(db, current_user.company_id)
    prompt = "Bugungi savdoga qisqacha ta'rif ber."
    ai_summary = call_gemini(prompt, context)

    return {
        "date": str(today),
        "stats": {
            "total_sales": total_sales,
            "total_orders": len(sales),
            "cash": cash,
            "card": card,
            "debt": debt,
        },
        "ai_summary": ai_summary,
    }


# ─── Weekly Chart ─────────────────────────────────────────────────────────

@router.get("/weekly-chart")
def get_weekly_chart(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """7 kunlik savdo grafik ma'lumotlari."""
    today = date.today()
    start_date = today - timedelta(days=6)

    daily_sales = db.query(
        func.date(Sale.created_at).label("date"),
        func.sum(Sale.total_amount).label("total")
    ).filter(
        func.date(Sale.created_at) >= start_date,
        Sale.company_id == current_user.company_id,
        Sale.status == SaleStatus.completed
    ).group_by(func.date(Sale.created_at)).all()

    sales_dict = {str(d): float(t or 0) for d, t in daily_sales}
    days_map = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]

    chart_data = []
    for i in range(7):
        current_d = start_date + timedelta(days=i)
        str_d = str(current_d)
        chart_data.append({
            "day": days_map[current_d.weekday()],
            "date": str_d,
            "amount": sales_dict.get(str_d, 0),
        })

    return {"chart": chart_data}


# ─── Insights ─────────────────────────────────────────────────────────────

@router.get("/insights")
def get_ai_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """Mahalliy AI xulosalari (O'sish, zaxira, tavsiya)."""
    return {"insights": get_insights(db, current_user.company_id)}


# ─── Debt Analytics ──────────────────────────────────────────────────────

@router.get("/debt-analytics")
def get_debt_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """Qarz tahlili, toifalar va mahalliy AI maslahati."""
    data = categorize_customers(db, current_user.company_id)

    overdue = data.get("overdue_count", 0)
    total_debt = data.get("total_debt", 0)
    total_debtors = data.get("total_debtors", 0)

    if overdue > 0:
        advice = (
            f"Muddati o'tgan {overdue} ta mijozga zudlik bilan Telegram yoki "
            f"telefon orqali eslatma yuboring. Umumiy muddati o'tgan qarz: "
            f"{total_debt:,.0f} so'm."
        )
    elif total_debtors > 0:
        advice = (
            f"{total_debtors} ta mijozda jami {total_debt:,.0f} so'm nasiya bor. "
            f"To'lov muddatlariga e'tibor bering."
        )
    else:
        advice = "Barcha mijozlar bo'yicha nasiya holati me'yorda. Yaxshi ish!"

    data["ai_advice"] = advice
    return data


# ─── Daily Report (manual trigger) ───────────────────────────────────────

@router.get("/daily-report")
def get_daily_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """Kunlik to'liq hisobotni ko'rish (Telegram ga yuborilgani bilan bir xil matn)."""
    from app.models.company import Company
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    company_name = company.name if company else "Do'kon"
    report = build_daily_report(db, current_user.company_id, company_name)
    # HTML taglarini olib tashlash (API response uchun toza matn)
    import re
    clean = re.sub(r"<[^>]+>", "", report)
    return {"report": clean, "html": report}


# ─── Copilot Chat ─────────────────────────────────────────────────────────

@router.post("/copilot/chat")
def chat_with_copilot(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """
    AI Copilot bilan chat.
    Quyidagilarni bajaradi:
    - Qarz to'lash: «Ali 50000 so'm to'ladi»
    - Nasiya yozish: «Vali 30000 so'm nasiya oldi»
    - Savdo savollari: «Bugungi tushum qancha?»
    """
    context = build_daily_context(db, current_user.company_id)
    intent_data = parse_copilot_intent(request.message, context)

    if intent_data.get("intent") in ["debt_payment", "add_debt"]:
        result = execute_copilot_action(
            intent_data, db, current_user.company_id, current_user.id
        )
        return result

    return {
        "reply": intent_data.get(
            "reply",
            "Kechirasiz, bu so'rovni tushunmadim. "
            "Masalan: «Ali 50000 so'm qarzini to'ladi» deb yozing."
        )
    }
