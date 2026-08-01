from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.core.dependencies import require_roles
from app.models.user import User, UserRole
from app.models.sale import Sale
from app.services.ai_service import (
    build_daily_context, 
    call_gemini, 
    get_insights,
    parse_copilot_intent,
    execute_copilot_action
)
from app.services.debt_scoring import categorize_customers

router = APIRouter(prefix="/ai", tags=["AI Analytics & Copilot"])

class ChatRequest(BaseModel):
    message: str

@router.get("/status")
def get_ai_status():
    """AI tizimi holati (debug uchun)"""
    import httpx
    from app.config import settings
    
    if not settings.GEMINI_API_KEY:
        return {"status": "error", "message": "GEMINI_API_KEY .env da yo'q!"}
    
    key_preview = settings.GEMINI_API_KEY[:12] + "..."
    
    # Har ikkala API versiyasini sinab ko'ramiz
    results = []
    models_to_test = [
        ("v1", "gemini-1.5-flash"),
    ]
    
    for api_ver, model in models_to_test:
        url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"
        try:
            resp = httpx.post(url, json={
                "contents": [{"parts": [{"text": "salom"}]}]
            }, timeout=5)
            results.append({
                "api": api_ver, "model": model,
                "status": resp.status_code,
                "ok": resp.status_code == 200,
                "error": resp.json().get("error", {}).get("message", "") if resp.status_code != 200 else ""
            })
            if resp.status_code == 200:
                break  # Ishlaydigan topildi
        except Exception as e:
            results.append({"api": api_ver, "model": model, "status": 0, "ok": False, "error": type(e).__name__ + ": " + str(e)})
    
    working = [r for r in results if r["ok"]]
    return {
        "api_key_preview": key_preview,
        "working_model": working[0] if working else None,
        "all_results": results
    }

@router.get("/daily-summary")
def get_daily_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """Bugungi kun xulosasi va AI tahlili"""
    def sf(v):
        try: return float(v or 0)
        except: return 0.0

    today = date.today()
    sales = db.query(Sale).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == current_user.company_id
    ).all()
    
    total_sales = sum(sf(s.total_amount) for s in sales)
    cash = sum(sf(s.paid_cash) for s in sales)
    card = sum(sf(s.paid_card) for s in sales)
    debt = sum(sf(s.total_amount) - sf(s.paid_amount) for s in sales)
    
    context = build_daily_context(db, current_user.company_id)
    prompt = "Ushbu ma'lumotlarga asoslanib 1-2 ta gap bilan bugungi savdoga ta'rif ber."
    ai_summary = call_gemini(prompt, context)
    
    return {
        "date": str(today),
        "stats": {
            "total_sales": total_sales,
            "total_orders": len(sales),
            "cash": cash,
            "card": card,
            "debt": debt
        },
        "ai_summary": ai_summary
    }

@router.get("/weekly-chart")
def get_weekly_chart(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """7 kunlik savdo grafik ma'lumotlari"""
    today = date.today()
    start_date = today - timedelta(days=6)
    
    # Guruhlash sana bo'yicha
    daily_sales = db.query(
        func.date(Sale.created_at).label('date'),
        func.sum(Sale.total_amount).label('total')
    ).filter(
        func.date(Sale.created_at) >= start_date,
        Sale.company_id == current_user.company_id
    ).group_by(func.date(Sale.created_at)).all()
    
    sales_dict = {str(d): float(t) for d, t in daily_sales}
    
    chart_data = []
    days_map = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
    
    for i in range(7):
        current_d = start_date + timedelta(days=i)
        str_d = str(current_d)
        chart_data.append({
            "day": days_map[current_d.weekday()],
            "date": str_d,
            "amount": sales_dict.get(str_d, 0)
        })
        
    return {"chart": chart_data}

@router.get("/insights")
def get_ai_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """Sun'iy intellekt xulosalari (O'sish, zaxira, tavsiya)"""
    return {"insights": get_insights(db, current_user.company_id)}

@router.get("/debt-analytics")
def get_debt_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """Qarz tahlili va ishonch bali"""
    data = categorize_customers(db, current_user.company_id)
    
    # AI dan qisqacha maslahat
    context = f"Qarzdorlar: {data['total_debtors']} ta. Umumiy qarz: {data['total_debt']}. Kechikkanlar: {data['overdue_count']} ta."
    prompt = "Ushbu holat bo'yicha qarzni yig'ish yuzasidan 1 ta qisqa maslahat ber."
    data["ai_advice"] = call_gemini(prompt, context)
    
    return data

@router.post("/copilot/chat")
def chat_with_copilot(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """AI Copilot bilan chat va harakatlar"""
    # Chat uchun do'konning hozirgi holati haqida qisqacha ma'lumot beramiz
    context = build_daily_context(db, current_user.company_id)
    intent_data = parse_copilot_intent(request.message, context)
    
    if intent_data.get('intent') in ["debt_payment", "add_debt"]:
        result = execute_copilot_action(intent_data, db, current_user.company_id, current_user.id)
        return result
        
    return {"reply": intent_data.get('reply', 'Men sizning xabaringizni tushuna olmadim.')}
