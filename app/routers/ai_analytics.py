from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.core.dependencies import require_roles, get_current_user
from app.models.user import User, UserRole
from app.models.sale import Sale
from app.services.ai_service import (
    build_daily_context,
    build_daily_report,
    get_insights,
)
from app.services.ai_scope import (
    resolve_ai_scope, scope_info, scope_label, scope_sale_filter,
)
from app.services.stock_report import low_stock_count_for_scope  # T2.3: yagona "kam qoldiq" ta'rifi
from app.services.ai_tools_registry import AIToolRegistry, summarize_reply
from app.services.openrouter_copilot_service import call_copilot_ai
import os

from app.services.debt_scoring import categorize_customers

router = APIRouter(prefix="/ai", tags=["AI Analytics & Copilot"])

class ChatRequest(BaseModel):
    message: str
    conversation_id: str = ""
    branch_id: Optional[int] = None  # T2.9: tanlangan filial (ixtiyoriy)


def _inject_branch(tool_name, tool_arguments: dict, scope) -> dict:
    """Chatda filial tanlangan bo'lsa va LLM `branch` bermagan bo'lsa - shu filialni vositaga uzatadi."""
    args = dict(tool_arguments or {})
    if scope is None or scope.branch_id is None or args.get("branch"):
        return args
    tool_class = AIToolRegistry.get_tool(tool_name)
    if tool_class and "branch" in (tool_class.parameters or {}).get("properties", {}):
        args["branch_id"] = scope.branch_id
    return args

@router.get("/status")
def get_ai_status(current_user: User = Depends(get_current_user)):
    return {
        "status": "ok",
        "mode": "openrouter",
        "message": "OpenRouter AI tizimi ishlayapti.",
        "features": [
            "Kunlik savdo tahlili",
            "Haftalik tendensiya",
            "Zaxira va qarz holati",
            "Copilot chat (qarz to'lash / nasiya yozish)",
            "Har kuni sozlamada belgilangan vaqtda (standart 20:00) Telegram hisoboti",
        ]
    }


def _run_copilot_chat(request: "ChatRequest", db: Session, current_user: User) -> dict:
    """
    /chat va /copilot/chat endpointlari uchun umumiy mantiq.
    Xavfsizlik so'z filtrlariga emas, PostgreSQL RLS va tenant kontekstiga tayanadi.
    """
    from app.services.ai_db_context import ai_tenant_context

    scope = resolve_ai_scope(db, current_user, request.branch_id)
    with ai_tenant_context(db, current_user.company_id, read_only=False):
        context = build_daily_context(db, current_user.company_id, scope)
    api_key = os.getenv("OPENROUTER_API_KEY", "")

    from app.models.ai_chat_history import AiChatHistory

    # 1. Oxirgi 10 ta xabarni olish
    history_records = db.query(AiChatHistory).filter(
        AiChatHistory.user_id == current_user.id,
        AiChatHistory.company_id == current_user.company_id
    ).order_by(AiChatHistory.created_at.desc()).limit(20).all()
    history_records.reverse()

    conversation_history = [
        {"role": r.role, "content": r.message}
        for r in history_records
    ]

    # 2. Foydalanuvchi xabarini saqlash
    db.add(AiChatHistory(
        user_id=current_user.id,
        company_id=current_user.company_id,
        role="user",
        message=request.message,
        intent="pending"
    ))
    db.commit()

    # 3. call_copilot_ai ga conversation_history uzatish
    intent_data = call_copilot_ai(request.message, context, api_key, user=current_user, conversation_history=conversation_history)

    if intent_data.get("intent") == "execute_tool":
        tool_name = intent_data.get("tool_name")
        tool_arguments = _inject_branch(tool_name, intent_data.get("tool_arguments", {}), scope)

        result = AIToolRegistry.execute_tool(
            db=db,
            name=tool_name,
            kwargs=tool_arguments,
            user=current_user,
            prompt=request.message,
            conversation_id=request.conversation_id
        )

        # Agar bu analitika tool bo'lsa, javobni AI orqali "human-friendly" qilamiz
        if result.get("action") and result["action"].get("type") == "show_data":
            from app.services.openrouter_copilot_service import summarize_tool_result_with_llm
            ai_summary = summarize_tool_result_with_llm(request.message, tool_name, result["reply"], api_key)
            result["reply"] = ai_summary

        result_reply = result.get("reply", "")

        # 4. AI javobini saqlash
        db.add(AiChatHistory(
            user_id=current_user.id,
            company_id=current_user.company_id,
            role="assistant",
            message=result_reply,
            intent=intent_data.get("intent", "query")
        ))
        db.commit()
        result["scope"] = scope_info(scope)
        return result

    result_reply = intent_data.get("reply", "Kechirasiz, men bu so'rovni tushunmadim.")

    db.add(AiChatHistory(
        user_id=current_user.id,
        company_id=current_user.company_id,
        role="assistant",
        message=result_reply,
        intent=intent_data.get("intent", "query")
    ))
    db.commit()

    return {
        "reply": result_reply,
        "scope": scope_info(scope),
    }


@router.post("/chat")
def ai_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    return _run_copilot_chat(request, db, current_user)

# Also keeping the old endpoints like /daily-summary unchanged.
@router.get("/daily-summary")
def get_daily_summary(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """Bugungi kun xulosasi va mahalliy AI tahlili. `?branch_id=` - filial doirasi (T2.9)."""
    from app.utils.report_utils import local_today, day_sales_summary

    scope = resolve_ai_scope(db, current_user, branch_id)
    today = local_today()
    summary = day_sales_summary(db, current_user.company_id, today, sale_filter=scope_sale_filter(scope))

    context = build_daily_context(db, current_user.company_id, scope)
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
            "total_sales": summary["gross"],
            "total_orders": summary["count"],
            "returns": summary["returns"],
            "returns_count": summary["returns_count"],
            "net_sales": summary["net"],
            "cash": summary["cash"],
            "card": summary["card"],
            "debt": summary["debt"],
        },
        "ai_summary": ai_summary,
        "scope": scope_info(scope),
    }


# ─── Weekly Chart ─────────────────────────────────────────────────────────

@router.get("/weekly-chart")
def get_weekly_chart(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """7 kunlik savdo grafik ma'lumotlari (UZS, sotuv hujjatlari)."""
    from app.utils.report_utils import local_today, local_day_start, sale_doc_filter

    scope = resolve_ai_scope(db, current_user, branch_id)
    today = local_today()
    start_date = today - timedelta(days=6)

    day_col = func.date(Sale.created_at)
    chart_q = db.query(
        day_col.label("date"),
        func.sum(Sale.total_amount).label("total")
    ).filter(
        Sale.created_at >= local_day_start(start_date),
        Sale.company_id == current_user.company_id,
        sale_doc_filter(),
    )
    sale_flt = scope_sale_filter(scope)
    if sale_flt is not None:
        chart_q = chart_q.filter(sale_flt)
    daily_sales = chart_q.group_by(day_col).all()

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

    return {"chart": chart_data, "scope": scope_info(scope)}


# ─── Insights ─────────────────────────────────────────────────────────────

@router.get("/insights")
def get_ai_insights(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """Mahalliy AI xulosalari (O'sish, zaxira, tavsiya)."""
    scope = resolve_ai_scope(db, current_user, branch_id)
    return {"insights": get_insights(db, current_user.company_id, scope), "scope": scope_info(scope)}


# ─── Debt Analytics ──────────────────────────────────────────────────────

@router.get("/debt-analytics")
def get_debt_analytics(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """Qarz tahlili, toifalar va mahalliy AI maslahati.

    `?branch_id=` tekshiriladi (404/403), lekin qarz hozircha filial bo'yicha ajratilmagan (T2.6) -
    natija "butun korxona" yorlig'i bilan qaytadi."""
    resolve_ai_scope(db, current_user, branch_id)
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
    data["scope"] = scope_info(None)
    data["scope_note"] = "Qarz filial bo'yicha ajratilmagan: butun korxona qarzi ko'rsatilmoqda."
    return data


# ─── Daily Report (manual trigger) ───────────────────────────────────────

@router.get("/daily-report")
def get_daily_report(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    """Kunlik to'liq hisobotni ko'rish (Telegram ga yuborilgani bilan bir xil matn)."""
    from app.models.company import Company
    scope = resolve_ai_scope(db, current_user, branch_id)
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    company_name = company.name if company else "Do'kon"
    report = build_daily_report(db, current_user.company_id, company_name, scope)
    # HTML taglarini olib tashlash (API response uchun toza matn)
    import re
    clean = re.sub(r"<[^>]+>", "", report)
    return {"report": clean, "html": report, "scope": scope_info(scope)}


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
    return _run_copilot_chat(request, db, current_user)

@router.get("/recommendations")
def get_ai_recommendations(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    from datetime import datetime, timedelta, timezone
    from app.models.sale import Sale
    from app.models.customer import Customer
    from app.models.product import Product
    from app.models.inventory import StockLevel
    from sqlalchemy import func

    from app.utils.report_utils import sale_doc_filter, load_debtors

    scope = resolve_ai_scope(db, current_user, branch_id)
    recommendations = []
    
    # Recommendation 1: Inactive customers (mijozlar korxona bo'yicha umumiy)
    # NOT IN + NULL tuzog'i: mijozsiz (naqd) cheklarning customer_id NULL, ular chiqarib tashlanadi
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    subq = db.query(Sale.customer_id).filter(
        Sale.company_id == current_user.company_id,
        Sale.created_at >= cutoff,
        Sale.customer_id.isnot(None),
        sale_doc_filter(),
    ).scalar_subquery()
    inactive_count = db.query(func.count(Customer.id)).filter(
        Customer.company_id == current_user.company_id,
        ~Customer.id.in_(subq)
    ).scalar() or 0
    
    if inactive_count > 0:
        recommendations.append({
            "type": "inactive_customers",
            "title": "Passiv mijozlar bilan ishlash",
            "description": f"Sizda {inactive_count} ta mijoz oxirgi 30 kunda hech narsa xarid qilmadi. Ularni qaytarish uchun SMS yuborishni tavsiya qilaman.",
            "suggested_prompt": "Passiv mijozlarga aksiya haqida SMS qoralama tayyorla"
        })

    # Recommendation 2: Low Stock
    # (yagona ta'rif: min_stock > 0 va doiradagi jami qoldiq <= min_stock, o'chirilgan mahsulotsiz)
    low_count = low_stock_count_for_scope(db, current_user.company_id, scope)
    
    if low_count > 0:
        recommendations.append({
            "type": "low_stock",
            "title": "Tugayotgan mahsulotlar",
            "description": f"{scope_label(scope)}: {low_count} ta mahsulotning zaxirasi minimal chegaradan kam qolgan. Ular uchun yetkazib beruvchiga zayavka (Purchase Order) berishingiz mumkin.",
            "suggested_prompt": "Tugayotgan mahsulotlar uchun zayavka tayyorla"
        })

    # Recommendation 3: Debtors
    # (yagona manba - load_debtors; qarz filial bo'yicha ajratilmagan, butun korxona)
    debtors_count = len(load_debtors(db, Customer, current_user.company_id))
    
    if debtors_count > 0:
        recommendations.append({
            "type": "debtors",
            "title": "Qarzdorlar",
            "description": f"Butun korxona bo'yicha {debtors_count} ta mijozning qarzi bor. Ularga qarzini eslatuvchi SMS jo'nating.",
            "suggested_prompt": "Qarzdorlarga 'qarzni qaytaring' deb SMS tayyorla"
        })
        
    return {"recommendations": recommendations, "scope": scope_info(scope)}

from fastapi import UploadFile, File, HTTPException
import requests
import os

@router.post("/voice")
async def process_voice_command(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin, UserRole.cashier))
):
    """
    Ovozli xabarni qabul qilib, uni matnga o'giradi va AI ga yuboradi.
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY sozlanmagan. Ovozli xizmat vaqtincha o'chirilgan.")

    try:
        # Read the audio file
        audio_content = await file.read()
        
        # Call OpenAI Whisper API directly via requests
        headers = {
            "Authorization": f"Bearer {openai_api_key}"
        }
        
        files = {
            "file": (file.filename, audio_content, file.content_type),
        }
        data = {
            "model": "whisper-1",
            "language": "uz" # Uzbek tilida tanish
        }
        
        resp = requests.post("https://api.openai.com/v1/audio/transcriptions", headers=headers, files=files, data=data)
        resp.raise_for_status()
        
        transcription = resp.json().get("text", "")
        
        if not transcription:
            raise HTTPException(status_code=400, detail="Ovozni aniqlab bo'lmadi. Iltimos, qaytadan gapiring.")

        # Endi olingan matnni xuddi oddiy chat kabi AIToolRegistry orqali aylantiramiz
        from app.services.openrouter_copilot_service import call_copilot_ai
        from app.services.ai_service import build_daily_context
        
        scope = resolve_ai_scope(db, current_user, None)
        daily_context = build_daily_context(db, current_user.company_id, scope)
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        
        intent_data = call_copilot_ai(transcription, daily_context, openrouter_key, user=current_user)
        
        if intent_data.get("intent") == "execute_tool":
            tool_name = intent_data.get("tool_name")
            tool_arguments = intent_data.get("tool_arguments", {})
            
            result = AIToolRegistry.execute_tool(
                db=db,
                name=tool_name,
                kwargs=tool_arguments,
                user=current_user,
                prompt=transcription,
                conversation_id=""
            )
            
            if result.get("action") and result["action"].get("type") == "show_data":
                from app.services.openrouter_copilot_service import summarize_tool_result_with_llm
                ai_summary = summarize_tool_result_with_llm(transcription, tool_name, result["reply"], openrouter_key)
                result["reply"] = ai_summary
                
            # Add transcription to the result so the frontend can display what the user said
            result["transcription"] = transcription
            return result
            
        return {
            "transcription": transcription,
            "reply": intent_data.get("reply", "Kechirasiz, men bu so'rovni tushunmadim.")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ovozli xabarni qayta ishlashda xatolik: {str(e)}")

class ConfirmRequest(BaseModel):
    confirmation_id: Optional[str] = None
    pending_action_id: Optional[str] = None

@router.post("/confirm")
def confirm_ai_action(
    request: ConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin))
):
    from datetime import datetime, timezone
    from app.models.pending_action import PendingAction
    from app.models.ai_audit import AIAuditLog
    import time

    action_id = (request.pending_action_id or request.confirmation_id or "").strip()
    if not action_id:
        return {"reply": "❌ confirmation_id yoki pending_action_id ko'rsatilishi shart."}

    # 1. Atomik qulf (Row-level lock): with_for_update() parallel ikki marta tasdiqlashni bloklaydi
    pending = db.query(PendingAction).filter(
        PendingAction.id == action_id
    ).with_for_update().first()

    if not pending:
        # Fallback: agar eski AIAuditLog bo'lsa
        legacy_log = db.query(AIAuditLog).filter(
            AIAuditLog.confirmation_id == action_id,
            AIAuditLog.company_id == current_user.company_id,
            AIAuditLog.status == "PENDING_CONFIRMATION"
        ).with_for_update().first()
        if not legacy_log:
            return {"reply": "❌ Tasdiqlash topilmadi yoki allaqachon bajarilgan."}

        if legacy_log.user_id != current_user.id:
            return {"reply": "❌ Bu tasdiqlashni faqat uni boshlagan foydalanuvchi bajarishi mumkin."}

        tool_class = AIToolRegistry.get_tool(legacy_log.tool_name)
        if not tool_class:
            return {"reply": "❌ Tool topilmadi."}

        HIGH_RISK_ROLES = [UserRole.admin, UserRole.director, UserRole.super_admin]
        if tool_class.risk_level == "HIGH" and current_user.role not in HIGH_RISK_ROLES:
            return {"reply": "❌ Kechirasiz, sizda bu amalni tasdiqlash uchun ruxsat yo'q."}

        start_time = time.time()
        try:
            tool_instance = tool_class()
            result = tool_instance.execute(db, current_user.company_id, current_user, **legacy_log.tool_arguments)
            legacy_log.result_summary = summarize_reply(result)
            # T2.6: "❌ ..." javobi jurnalda SUCCESS emas, ERROR
            if (legacy_log.result_summary or "").lstrip().startswith("❌"):
                legacy_log.status = "ERROR"
                legacy_log.error = legacy_log.result_summary
            else:
                legacy_log.status = "SUCCESS"
            legacy_log.execution_time_ms = (time.time() - start_time) * 1000
            # Commit try ichida: IntegrityError (FK/NOT NULL) 500 emas, ERROR logi bo'lib qaytadi
            db.commit()
        except Exception as e:
            db.rollback()
            err_text = e.detail if isinstance(e, HTTPException) else str(e)
            legacy_log.status = "ERROR"
            legacy_log.error = str(err_text)
            legacy_log.execution_time_ms = (time.time() - start_time) * 1000
            result = {"reply": f"❌ Xatolik yuz berdi: {err_text}"}
            db.commit()
        return result

    # 2. Idempotentlik tekshiruvi: allaqachon bajarilgan bo'lsa darhol rad etiladi
    if pending.status == "executed":
        return {"reply": "❌ Bu amal allaqachon tasdiqlangan va bajarilgan."}
    if pending.status != "pending":
        return {"reply": f"❌ Bu amal tasdiqlash uchun yaroqsiz (holati: {pending.status})."}

    # 3. Tenant (korxona) izolyatsiyasi: boshqa korxona amalini ko'rish yoki tasdiqlash mumkin emas
    if pending.company_id != current_user.company_id:
        return {"reply": "❌ Boshqa korxona amalini tasdiqlash taqiqlangan."}

    # 4. Foydalanuvchi bog'liqligi: faqat amalni yaratgan shaxs tasdiqlay oladi
    if pending.user_id != current_user.id:
        return {"reply": "❌ Bu tasdiqlashni faqat uni boshlagan foydalanuvchi bajarishi mumkin."}

    # 5. Muddat (TTL) tekshiruvi:
    now = datetime.now(timezone.utc)
    exp = pending.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        pending.status = "expired"
        db.commit()
        return {"reply": "❌ Tasdiqlash muddati o'tib ketgan."}

    # 6. Tool mavjudligi va RBAC qayta tekshiruvi:
    tool_class = AIToolRegistry.get_tool(pending.tool_name)
    if not tool_class:
        return {"reply": "❌ Tool topilmadi."}

    HIGH_RISK_ROLES = [UserRole.admin, UserRole.director, UserRole.super_admin]
    if tool_class.risk_level == "HIGH" and current_user.role not in HIGH_RISK_ROLES:
        return {"reply": "❌ Kechirasiz, sizda bu amalni tasdiqlash uchun ruxsat yo'q."}

    # 6.5. Argumentlardagi barcha ID'lar shu korxonaga tegishli ekanini qayta tekshirish
    from app.services.ai_tools_registry import validate_arguments_company_ownership
    try:
        validate_arguments_company_ownership(db, pending.company_id, pending.tool_arguments)
    except PermissionError as pe:
        pending.status = "rejected"
        pending.result_summary = str(pe)
        db.commit()
        return {"reply": f"❌ Xavfsizlik xatosi: {str(pe)}"}

    # 7. Ijro: FAQAT serverda saqlangan pending.tool_arguments va pending.company_id ishlatiladi
    start_time = time.time()
    try:
        tool_instance = tool_class()
        from app.services.ai_db_context import ai_tenant_context
        with ai_tenant_context(db, pending.company_id, read_only=False):
            result = tool_instance.execute(db, pending.company_id, current_user, **pending.tool_arguments)
        pending.result_summary = summarize_reply(result)
        # T2.6: vosita xatoni istisno emas, "❌ ..." javobi sifatida qaytarsa — jurnalda SUCCESS emas, ERROR
        is_tool_error = (pending.result_summary or "").lstrip().startswith("❌")
        if is_tool_error:
            pending.status = "failed"
        else:
            pending.status = "executed"
            pending.executed_at = datetime.now(timezone.utc)

        # Audit jurnali bilan sinxronlashtirish
        audit_log = db.query(AIAuditLog).filter(AIAuditLog.confirmation_id == action_id).first()
        if audit_log:
            if is_tool_error:
                audit_log.status = "ERROR"
                audit_log.error = pending.result_summary
            else:
                audit_log.status = "SUCCESS"
            audit_log.result_summary = pending.result_summary
            audit_log.execution_time_ms = (time.time() - start_time) * 1000

        # Commit try ichida: IntegrityError (FK/NOT NULL) 500 emas, ERROR logi bo'lib qaytadi
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        err_text = e.detail if isinstance(e, HTTPException) else str(e)
        try:
            pending.status = "failed"
            pending.result_summary = str(err_text)
            audit_log = db.query(AIAuditLog).filter(AIAuditLog.confirmation_id == action_id).first()
            if audit_log:
                audit_log.status = "ERROR"
                audit_log.error = str(err_text)
                audit_log.execution_time_ms = (time.time() - start_time) * 1000
            db.commit()
        except Exception:
            db.rollback()
        return {"reply": f"❌ Xatolik yuz berdi: {err_text}"}



# ─── AI qoralamalarini haqiqiy yozuvga aylantirish ───────────────────────────

from decimal import Decimal
from typing import List, Optional


class ConfirmPOItem(BaseModel):
    product_id: int
    quantity: Decimal
    unit_cost: Decimal
    supplier_id: int
    warehouse_id: Optional[int] = None  # T2.9: bo'lsa umumiy ombordan ustun


class ConfirmPORequest(BaseModel):
    warehouse_id: int
    items: List[ConfirmPOItem]
    note: Optional[str] = None


@router.post("/actions/purchase-order")
def confirm_ai_purchase_order(
    request: ConfirmPORequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin)),
):
    """
    AI tomonidan tayyorlangan zayavka qoralamasini haqiqiy xarid buyurtmasi(lari)ga
    aylantiradi. Har bir yetkazib beruvchi uchun alohida PurchaseOrder yaratiladi.
    """
    if not request.items:
        raise HTTPException(status_code=400, detail="Mahsulotlar ro'yxati bo'sh")

    missing = [i for i in request.items if not i.supplier_id]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"{len(missing)} ta mahsulot uchun yetkazib beruvchi tanlanmagan. Iltimos, barcha mahsulotlarga yetkazib beruvchi tanlang.",
        )

    from collections import defaultdict
    from app.schemas.purchase_order import POCreate, POItemCreate
    from app.services.purchase_order_service import create_purchase_order

    # Ombor: elementdagi (bo'lmasa umumiy) - avval hammasi tekshiriladi, keyin PO yaratiladi
    from app.models.warehouse import Warehouse
    wh_ids = {i.warehouse_id or request.warehouse_id for i in request.items}
    found = {w.id for w in db.query(Warehouse.id).filter(
        Warehouse.id.in_(wh_ids), Warehouse.company_id == current_user.company_id).all()}
    if wh_ids - found:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    scope = resolve_ai_scope(db, current_user, None)
    if scope is not None and any(w not in scope.warehouse_ids for w in wh_ids):
        raise HTTPException(status_code=403, detail="Bu omborga ruxsat yo'q")

    groups: dict = defaultdict(list)
    for item in request.items:
        groups[(item.supplier_id, item.warehouse_id or request.warehouse_id)].append(item)

    created_pos = []
    for (supplier_id, warehouse_id), items in groups.items():
        po_data = POCreate(
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            note=request.note or "AI Copilot orqali avtomatik tayyorlangan zayavka",
            items=[
                POItemCreate(product_id=i.product_id, qty_ordered=i.quantity, unit_cost=i.unit_cost)
                for i in items
            ],
        )
        po = create_purchase_order(db, po_data, current_user)
        created_pos.append(po)

    db.commit()
    for po in created_pos:
        db.refresh(po)

    numbers = ", ".join(po.number for po in created_pos)
    return {
        "reply": f"✅ {len(created_pos)} ta xarid buyurtmasi yaratildi: {numbers}",
        "purchase_order_ids": [po.id for po in created_pos],
        "purchase_order_numbers": [po.number for po in created_pos],
    }


class ConfirmSmsRecipient(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    phone: str


class ConfirmSmsRequest(BaseModel):
    recipients: List[ConfirmSmsRecipient]
    message: str


SMS_SEND_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)


@router.post("/actions/sms-campaign")
async def confirm_ai_sms_campaign(
    request: ConfirmSmsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*SMS_SEND_ROLES)),
):
    """
    AI tomonidan tayyorlangan SMS kampaniya qoralamasini haqiqatan yuboradi
    (Eskiz orqali), har bir xabarni SMSLog'ga yozadi.
    """
    if not request.recipients:
        raise HTTPException(status_code=400, detail="Qabul qiluvchilar ro'yxati bo'sh")
    if len(request.recipients) > 50:
        raise HTTPException(status_code=400, detail="Bir martada 50 tadan ortiq mijozga yuborib bo'lmaydi")
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Xabar matni bo'sh bo'lishi mumkin emas")

    from app.models.sms_log import SMSLog
    from app.models.customer import Customer
    from app.services import eskiz_service

    # Telefon raqami klientdan olinmaydi: faqat shu kompaniya mijozlarining bazadagi raqamiga
    # yuboriladi. Aks holda kompaniya Eskiz hisobidan istalgan raqamga SMS yuborish mumkin edi.
    if any(not r.id for r in request.recipients):
        raise HTTPException(status_code=400, detail="Qabul qiluvchilar mijoz ID si bilan berilishi kerak")
    customer_ids = list(dict.fromkeys(r.id for r in request.recipients))
    customers = db.query(Customer).filter(
        Customer.company_id == current_user.company_id,
        Customer.id.in_(customer_ids),
    ).all()
    customers_by_id = {c.id: c for c in customers}
    if len(customers_by_id) != len(customer_ids):
        raise HTTPException(status_code=400, detail="Qabul qiluvchilar ichida sizning korxonangiz mijozi bo'lmaganlari bor")

    sent, failed = 0, 0
    for cid in customer_ids:
        phone = (customers_by_id[cid].phone or "").strip()
        if not phone:
            failed += 1
            continue
        result = await eskiz_service.send_sms(phone, request.message)
        db.add(SMSLog(
            company_id=current_user.company_id,
            phone=phone,
            message=request.message,
            status="sent" if result["success"] else "failed",
            eskiz_id=result.get("eskiz_id"),
            sms_type="ai_campaign",
            error=result.get("error"),
        ))
        if result["success"]:
            sent += 1
        else:
            failed += 1

    db.commit()

    reply = f"✅ {sent} ta mijozga SMS yuborildi."
    if failed:
        reply += f" {failed} tasi yuborilmadi (xato)."

    return {"reply": reply, "sent": sent, "failed": failed}
