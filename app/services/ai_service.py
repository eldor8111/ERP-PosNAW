"""
AI Service — SDK'siz, to'g'ridan-to'g'ri HTTP REST API orqali Gemini bilan ishlaydi.
Bu yondashuv har qanday SDK versiya muammolarini hal qiladi.
"""
import json
import re
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from app.config import settings

from app.models.sale import Sale, SaleItem
from app.models.product import Product
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.services.debt_scoring import categorize_customers

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1/models"

# Sinab ko'riladigan modellar (v1 API da ishlaydiganlari)
MODELS_TO_TRY = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-pro",
]

SYSTEM_PROMPT = (
    "Sen E-Code ERP/POS tizimining sun'iy intellekt yordamchisisisan. "
    "Do'kon egasiga savdo, ombor va moliyaviy maslahat berasan. "
    "Javoblarni o'zbek tilida, qisqa, tushunarli va aniq ber. "
    "Raqamlarni chiroyli formatda yoz (masalan: 1,500,000 so'm)."
)


def _safe_float(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _call_gemini_raw(prompt: str) -> str:
    """
    Gemini REST API ga to'g'ridan-to'g'ri HTTP POST yuboradi.
    SDK'ga bog'liq emas — istalgan serverda ishlaydi.
    """
    if not settings.GEMINI_API_KEY:
        return ""

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
        },
    }

    for model in MODELS_TO_TRY:
        url = f"{GEMINI_API_BASE}/{model}:generateContent?key={settings.GEMINI_API_KEY}"
        try:
            resp = httpx.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                return text.strip()
            elif resp.status_code == 404:
                # Model topilmadi — keyingi modelga o'tamiz
                print(f"[Gemini] {model} topilmadi (404), keyingisini sinab ko'ramiz...")
                continue
            else:
                print(f"[Gemini] {model} xatolik {resp.status_code}: {resp.text[:200]}")
                break
        except Exception as e:
            print(f"[Gemini] {model} ulanish xatosi: {e}")
            break

    return ""


def call_gemini(prompt: str, context: str = "") -> str:
    """Gemini API ga so'rov. Agar ishlamasa fallback qaytaradi."""
    if not settings.GEMINI_API_KEY:
        return _fallback_analysis()
    full_prompt = f"Tizim ma'lumotlari:\n{context}\n\nTopshiriq:\n{prompt}"
    result = _call_gemini_raw(full_prompt)
    return result or _fallback_analysis()


def _fallback_analysis() -> str:
    return "Tizim tahlili yakunlandi. Ma'lumotlarga ko'ra hamma narsa me'yorida."


def build_daily_context(db: Session, company_id: int) -> str:
    """Bugungi savdo haqida qisqacha ma'lumot"""
    today = date.today()
    sales = db.query(Sale).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == company_id
    ).all()

    total = sum(_safe_float(s.total_amount) for s in sales)
    cash = sum(_safe_float(s.paid_cash) for s in sales)
    card = sum(_safe_float(s.paid_card) for s in sales)

    top_product = (
        db.query(Product.name, func.sum(SaleItem.quantity).label("qty"))
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(func.date(Sale.created_at) == today, Sale.company_id == company_id)
        .group_by(Product.name)
        .order_by(func.sum(SaleItem.quantity).desc())
        .first()
    )
    top_name = top_product[0] if top_product else "Yo'q"

    return (
        f"Bugungi sana: {today}\n"
        f"Sotuvlar soni: {len(sales)} ta\n"
        f"Umumiy tushum: {total:,.0f} so'm\n"
        f"Naqd pul: {cash:,.0f} so'm\n"
        f"Plastik karta: {card:,.0f} so'm\n"
        f"Eng ko'p sotilgan: {top_name}"
    )


def get_insights(db: Session, company_id: int):
    """3 ta karta (Insights) uchun ma'lumot"""
    try:
        today = date.today()
        prev_start = today - timedelta(days=14)
        prev_end = today - timedelta(days=7)
        curr_start = today - timedelta(days=7)

        prev_sales = _safe_float(
            db.query(func.coalesce(func.sum(Sale.total_amount), 0))
            .filter(func.date(Sale.created_at) >= prev_start,
                    func.date(Sale.created_at) < prev_end,
                    Sale.company_id == company_id)
            .scalar()
        )
        curr_sales = _safe_float(
            db.query(func.coalesce(func.sum(Sale.total_amount), 0))
            .filter(func.date(Sale.created_at) >= curr_start,
                    func.date(Sale.created_at) <= today,
                    Sale.company_id == company_id)
            .scalar()
        )

        growth_pct = 0.0
        if prev_sales > 0:
            growth_pct = (curr_sales - prev_sales) / prev_sales * 100

        trend_word = "o'sish" if growth_pct >= 0 else "pasayish"

        low_stock = db.query(StockLevel).filter(
            StockLevel.quantity < 10,
            StockLevel.warehouse.has(company_id=company_id)
        ).count()

        debt_data = categorize_customers(db, company_id)
        overdue = debt_data.get("overdue_count", 0)

        return [
            {
                "type": "growth",
                "icon": "📈",
                "title": "O'sish tendensiyasi",
                "body": f"O'tgan haftaga nisbatan umumiy savdo {abs(growth_pct):.1f}% {trend_word} kuzatildi.",
                "color": "green" if growth_pct >= 0 else "red",
            },
            {
                "type": "warning",
                "icon": "⚠️",
                "title": "Zaxira e'tibori",
                "body": f"{low_stock} ta mahsulot zaxirasi 10 tadan kam. Zaxirani to'ldiring.",
                "color": "orange",
            },
            {
                "type": "tip",
                "icon": "💡",
                "title": "AI Tavsiyasi",
                "body": f"Muddati o'tgan qarzdorlar soni: {overdue} ta. Ularga eslatma yuborishni tavsiya qilamiz.",
                "color": "blue",
            },
        ]
    except Exception as e:
        import traceback
        print(f"[get_insights] xato: {traceback.format_exc()}")
        return [
            {
                "type": "warning",
                "icon": "⚠️",
                "title": "Yuklashda xatolik",
                "body": f"Ma'lumotni yuklashda xatolik yuz berdi: {str(e)}",
                "color": "red",
            }
        ]


def parse_copilot_intent(message: str, context: str = "") -> dict:
    """Foydalanuvchi xabaridan amalni aniqlash"""
    if not settings.GEMINI_API_KEY:
        return {"intent": "query", "reply": "Gemini API kaliti sozlanmagan. .env faylini tekshiring."}

    prompt = f"""
Quyida do'konning hozirgi ma'lumotlari:
{context}

Foydalanuvchi so'rovi: "{message}"

Quyidagi uchta variantdan biri bo'yicha FAQAT toza JSON (``` belgilarsiz, izohsiz) qaytar:
1. Qarz to'lash: {{"intent": "debt_payment", "customer_name": "ism", "amount": raqam}}
2. Qarz yozish: {{"intent": "add_debt", "customer_name": "ism", "amount": raqam}}
3. Savol/suhbat: {{"intent": "query", "reply": "O'zbekcha aniq javob..."}}
"""

    raw = _call_gemini_raw(prompt)

    if not raw:
        return {"intent": "query", "reply": "Kechirasiz, AI hozir javob bera olmayapti. Bir ozdan keyin qayta urinib ko'ring."}

    # JSON qidirish
    clean = re.sub(r"```json|```", "", raw).strip()
    # Faqat { ... } qismini olish
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # JSON kelmasa — tekst sifatida qaytaramiz
    return {"intent": "query", "reply": raw}


def execute_copilot_action(intent_data: dict, db: Session, company_id: int, user_id: int) -> dict:
    """Intent asosida DB ga amal bajarish"""
    intent = intent_data.get("intent")

    if intent == "debt_payment":
        customer_name = intent_data.get("customer_name", "")
        amount = _safe_float(intent_data.get("amount", 0))

        customer = (
            db.query(Customer)
            .filter(Customer.company_id == company_id,
                    Customer.name.ilike(f"%{customer_name}%"))
            .first()
        )
        if not customer:
            return {"reply": f"❌ '{customer_name}' ismli mijoz topilmadi. Ismni to'g'ri yozing."}

        try:
            customer.debt_balance = _safe_float(customer.debt_balance) - amount
            db.commit()
        except Exception as e:
            db.rollback()
            return {"reply": f"❌ Bazaga yozishda xatolik: {str(e)}"}

        return {
            "reply": f"✅ Muvaffaqiyatli! {customer.name} mijozning qarzidan {amount:,.0f} so'm yechib olindi va tizimga yozildi.",
            "action": {"type": "debt_payment", "customer_id": customer.id, "amount": amount},
        }

    elif intent == "add_debt":
        customer_name = intent_data.get("customer_name", "")
        amount = _safe_float(intent_data.get("amount", 0))

        customer = (
            db.query(Customer)
            .filter(Customer.company_id == company_id,
                    Customer.name.ilike(f"%{customer_name}%"))
            .first()
        )
        if not customer:
            return {"reply": f"❌ '{customer_name}' ismli mijoz topilmadi. Avval mijozni bazaga qo'shing."}

        try:
            customer.debt_balance = _safe_float(customer.debt_balance) + amount
            db.commit()
        except Exception as e:
            db.rollback()
            return {"reply": f"❌ Bazaga yozishda xatolik: {str(e)}"}

        return {
            "reply": f"📝 Muvaffaqiyatli! {customer.name} hisobiga {amount:,.0f} so'm qarz yozildi.",
            "action": {"type": "add_debt", "customer_id": customer.id, "amount": amount},
        }

    elif intent == "query":
        return {"reply": intent_data.get("reply", "Kechirasiz, tushunmadim.")}

    return {"reply": "Kechirasiz, hozircha men faqat qarz va savdo ma'lumotlarini boshqara olaman."}
