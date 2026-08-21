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
    build_daily_report,
)
from app.services.ai_tools_registry import AIToolRegistry
from app.services.openrouter_copilot_service import call_copilot_ai
import os

from app.services.debt_scoring import categorize_customers

router = APIRouter(prefix="/ai", tags=["AI Analytics & Copilot"])

class ChatRequest(BaseModel):
    message: str

@router.get("/status")
def get_ai_status():
    return {
        "status": "ok",
        "mode": "openrouter",
        "message": "OpenRouter AI tizimi ishlayapti.",
        "features": [
            "Kunlik savdo tahlili",
            "Haftalik tendensiya",
            "Zaxira va qarz holati",
            "Copilot chat (qarz to'lash / nasiya yozish)",
            "Har kuni soat 17:30 da Telegram hisoboti",
        ]
    }

@router.post("/chat")
def ai_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    forbidden_words = ["boshqa korxona", "admin", "barcha korxona", "unut", "ignore"]
    msg_lower = request.message.lower()
    if any(word in msg_lower for word in forbidden_words):
        return {"reply": "Kechirasiz, faqat o'z korxonangizga tegishli ma'lumotlarga javob bera olaman."}
        
    context = build_daily_context(db, current_user.company_id)
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    
    intent_data = call_copilot_ai(request.message, context, api_key, user=current_user)

    if intent_data.get("intent") == "execute_tool":
        tool_name = intent_data.get("tool_name")
        tool_arguments = intent_data.get("tool_arguments", {})
        
        result = AIToolRegistry.execute_tool(
            db=db,
            name=tool_name,
            kwargs=tool_arguments,
            user=current_user,
            prompt=request.message,
            conversation_id="" # Optional
        )
        
        # Agar bu analitika tool bo'lsa, javobni AI orqali "human-friendly" qilamiz
        if result.get("action") and result["action"].get("type") == "show_data":
            from app.services.openrouter_copilot_service import summarize_tool_result_with_llm
            ai_summary = summarize_tool_result_with_llm(request.message, tool_name, result["reply"], api_key)
            result["reply"] = ai_summary

        return result

    return {
        "reply": intent_data.get(
            "reply",
            "Kechirasiz, men bu so'rovni tushunmadim."
        )
    }

# Also keeping the old endpoints like /daily-summary unchanged.
\n@router.get("/daily-summary")
def get_daily_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
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
    ai_summary_data = call_copilot_ai(
        prompt,
        context,
        os.getenv("OPENROUTER_API_KEY", "")
    )
    ai_summary = ai_summary_data.get(
        "reply",
        "AI xulosa hozircha mavjud emas."
    )

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
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
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
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """Mahalliy AI xulosalari (O'sish, zaxira, tavsiya)."""
    return {"insights": get_insights(db, current_user.company_id)}


# ─── Debt Analytics ──────────────────────────────────────────────────────

@router.get("/debt-analytics")
def get_debt_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
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
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
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
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """
    AI Copilot bilan chat.
    Quyidagilarni bajaradi:
    - Qarz to'lash: «Ali 50000 so'm to'ladi»
    - Nasiya yozish: «Vali 30000 so'm nasiya oldi»
    - Savdo savollari: «Bugungi tushum qancha?»
    """
    # Qat'iy tenant izolyatsiyasi (Prompt Injection himoyasi)
    forbidden_words = ["boshqa korxona", "admin", "barcha korxona", "unut", "ignore"]
    msg_lower = request.message.lower()
    if any(word in msg_lower for word in forbidden_words):
        return {"reply": "Kechirasiz, faqat o'z korxonangizga tegishli ma'lumotlarga javob bera olaman."}
        
    context = build_daily_context(db, current_user.company_id)
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    
    # AI ga so'rov yuboramiz
    intent_data = call_copilot_ai(request.message, context, api_key)

    # Agar AI funksiya (tool) tanlagan bo'lsa, uni bajarish
    if intent_data.get("intent") in ["debt_payment", "add_debt", "check_debt"]:
        # execute_copilot_action ichida company_id qat'iy ravishda tokendan(current_user) olinadi!
        result = execute_copilot_action(
            intent_data, db, current_user.company_id, current_user.id
        )
        return result

    # Agar xato bo'lsa yoki shunchaki matnli javob bo'lsa
    return {
        "reply": intent_data.get(
            "reply",
            "Kechirasiz, men bu so'rovni tushunmadim."
        )
    }
