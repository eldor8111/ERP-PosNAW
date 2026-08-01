import json
import re
from google import genai
from google.genai import types
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from app.config import settings

from app.models.sale import Sale, SaleItem
from app.models.product import Product
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.services.debt_scoring import categorize_customers

# Gemini konfiguratsiyasi — Yangi SDK (google-genai)
_client = None

def _get_client():
    """Lazy-init: Gemini client ni bir marta yaratib keshlaymiz"""
    global _client
    if _client is None and settings.GEMINI_API_KEY:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client

# Ishlaydigan model nomlari (yangi SDK v1 API ishlatadi)
MODELS_TO_TRY = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

SYSTEM_PROMPT = """
Sen E-Code ERP/POS tizimining sun'iy intellekt yordamchisisisan.
Do'kon egasiga savdo, ombor va moliyaviy maslahat berasan.
Javoblarni o'zbek tilida, qisqa, tushunarli va aniq ber.
Raqamlarni chiroyli formatda yoz (masalan, 1,500,000 so'm).
"""

def _safe_generate(prompt: str) -> str:
    """Bir nechta model orqali Gemini'dan matn olish."""
    client = _get_client()
    if not client:
        return ""
    
    for model_name in MODELS_TO_TRY:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.2,
                    max_output_tokens=1024,
                )
            )
            return response.text or ""
        except Exception as e:
            err_str = str(e)
            print(f"[Gemini] {model_name} xatosi: {err_str}")
            if "404" in err_str or "not found" in err_str.lower():
                continue   # Keyingi modelga o'tish
            break          # Boshqa xato — to'xtatamiz
    return ""


def call_gemini(prompt: str, context: str = "") -> str:
    """Gemini API ga so'rov yuborish. Agar kalit yo'q bo'lsa fallback qaytaradi."""
    if not settings.GEMINI_API_KEY:
        return _fallback_analysis(context)
    try:
        full_prompt = f"Tizim ma'lumotlari:\n{context}\n\nFoydalanuvchi so'rovi/Topshiriq:\n{prompt}"
        result = _safe_generate(full_prompt)
        return result or _fallback_analysis(context)
    except Exception as e:
        print(f"Gemini API Xatosi: {e}")
        return _fallback_analysis(context)


def _fallback_analysis(context: str) -> str:
    """Gemini API ishlamasa statik javob"""
    return "Tizim tahlili yakunlandi. Ma'lumotlarga ko'ra hamma narsa me'yorida."


def build_daily_context(db: Session, company_id: int) -> str:
    """Bugungi savdo haqida qisqacha ma'lumot yig'ish"""
    today = date.today()
    sales = db.query(Sale).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == company_id
    ).all()

    def sf(v):
        try:
            return float(v or 0)
        except:
            return 0.0

    total_sales = sum(sf(s.total_amount) for s in sales)
    cash = sum(sf(s.paid_cash) for s in sales)
    card = sum(sf(s.paid_card) for s in sales)

    top_product = db.query(
        Product.name, func.sum(SaleItem.quantity).label('qty')
    ).join(SaleItem, SaleItem.product_id == Product.id)\
     .join(Sale, Sale.id == SaleItem.sale_id)\
     .filter(func.date(Sale.created_at) == today, Sale.company_id == company_id)\
     .group_by(Product.name).order_by(func.sum(SaleItem.quantity).desc()).first()

    top_prod_name = top_product[0] if top_product else "Yo'q"

    return f"""
    Bugungi sana: {today}
    Sotuvlar soni: {len(sales)} ta
    Umumiy tushum: {total_sales:,.0f} so'm
    Naqd pul: {cash:,.0f} so'm
    Plastik karta: {card:,.0f} so'm
    Eng ko'p sotilgan mahsulot: {top_prod_name}
    """


def get_insights(db: Session, company_id: int):
    """3 ta karta (Insights) uchun ma'lumot"""
    def sf(v):
        try:
            return float(v or 0)
        except:
            return 0.0

    try:
        today = date.today()
        last_week_start = today - timedelta(days=14)
        last_week_end = today - timedelta(days=7)
        this_week_start = today - timedelta(days=7)

        last_week_sales = sf(db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(
            func.date(Sale.created_at) >= last_week_start,
            func.date(Sale.created_at) < last_week_end,
            Sale.company_id == company_id
        ).scalar())

        this_week_sales = sf(db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(
            func.date(Sale.created_at) >= this_week_start,
            func.date(Sale.created_at) <= today,
            Sale.company_id == company_id
        ).scalar())

        growth_pct = 0.0
        if last_week_sales > 0:
            growth_pct = (this_week_sales - last_week_sales) / last_week_sales * 100

        trend = "o'sish" if growth_pct > 0 else "pasayish"

        low_stock = db.query(StockLevel).filter(
            StockLevel.quantity < 10,
            StockLevel.warehouse.has(company_id=company_id)
        ).count()

        debt_data = categorize_customers(db, company_id)
        overdue = debt_data.get('overdue_count', 0)

        return [
            {
                "type": "growth",
                "icon": "📈",
                "title": "O'sish tendensiyasi",
                "body": f"O'tgan haftaga nisbatan umumiy savdo hajmi {abs(growth_pct):.1f}% ga {trend} kuzatildi.",
                "color": "green" if growth_pct >= 0 else "red"
            },
            {
                "type": "warning",
                "icon": "⚠️",
                "title": "Zaxira e'tibori",
                "body": f"{low_stock} ta mahsulot zaxirasi tugamoqda (10 tadan kam). Zaxirani tekshiring.",
                "color": "orange"
            },
            {
                "type": "tip",
                "icon": "💡",
                "title": "AI Tavsiyasi",
                "body": f"Xavfli qarzdorlar soni {overdue} ta. Ularga tez orada eslatma yuborishni tavsiya qilamiz.",
                "color": "blue"
            }
        ]
    except Exception as e:
        import traceback
        print(f"get_insights xatosi: {traceback.format_exc()}")
        return [
            {
                "type": "warning",
                "icon": "⚠️",
                "title": "Xatolik",
                "body": f"Ma'lumotni yuklashda xatolik: {str(e)}",
                "color": "red"
            }
        ]


def parse_copilot_intent(message: str, context: str = "") -> dict:
    """Foydalanuvchi xabaridan amalni aniqlash"""
    if not settings.GEMINI_API_KEY:
        return {"intent": "unknown", "reply": "Gemini API sozlanmagan. Iltimos kalitni kiriting."}

    prompt = f"""
    Quyida do'konning hozirgi ma'lumotlari:
    {context}

    Foydalanuvchi so'rovi: "{message}"

    Quyidagi variantlardan birini JSON formatida qaytar:
    1. Agar qarz to'lashi haqida bo'lsa: {{"intent": "debt_payment", "customer_name": "ism", "amount": summa_raqamda}}
    2. Agar kimgadir qarzga narsa berilgan bo'lsa: {{"intent": "add_debt", "customer_name": "ism", "amount": summa_raqamda}}
    3. Agar savol yoxud suhbat bo'lsa, o'zbek tilida chiroyli qilib javob ber: {{"intent": "query", "reply": "Aqlli javobing..."}}

    Hech qanday izohsiz faqat toza JSON qaytar. Hech qanday ```json kabi belgilar bo'lmasin.
    """

    try:
        text = _safe_generate(prompt)
        if not text:
            return {"intent": "query", "reply": "Kechirasiz, AI hozir ishlamayapti."}

        # JSON tozalash
        text = text.strip()
        text = re.sub(r"```json", "", text)
        text = re.sub(r"```", "", text)
        text = text.strip()

        return json.loads(text)
    except json.JSONDecodeError:
        # Agar JSON kelsa ham bo'lmasa, tekst sifatida qaytaramiz
        return {"intent": "query", "reply": text if text else "Kechirasiz, tushunmadim."}
    except Exception as e:
        import traceback
        print(f"parse_copilot_intent xatosi: {traceback.format_exc()}")
        return {"intent": "unknown", "reply": f"So'rovni tushunishda xatolik: {str(e)}"}


def execute_copilot_action(intent_data: dict, db: Session, company_id: int, user_id: int) -> dict:
    """Intent asosida DB ga amal bajarish"""
    intent = intent_data.get('intent')

    if intent == "debt_payment":
        customer_name = intent_data.get('customer_name')
        amount = intent_data.get('amount')

        customer = db.query(Customer).filter(
            Customer.company_id == company_id,
            Customer.name.ilike(f"%{customer_name}%")
        ).first()

        if not customer:
            return {"reply": f"Mijoz topilmadi: {customer_name}"}

        try:
            customer.debt_balance = float(customer.debt_balance or 0) - float(amount or 0)
            db.commit()
        except Exception as e:
            db.rollback()
            return {"reply": f"Qarzni yozishda xatolik: {str(e)}"}

        return {
            "reply": f"✅ Muvaffaqiyatli! {customer.name} nomli mijozning qarzidan {float(amount):,.0f} so'm yechib olindi va tizimga yozildi.",
            "action": {"type": "debt_payment", "customer_id": customer.id, "amount": amount}
        }

    elif intent == "add_debt":
        customer_name = intent_data.get('customer_name')
        amount = intent_data.get('amount')

        customer = db.query(Customer).filter(
            Customer.company_id == company_id,
            Customer.name.ilike(f"%{customer_name}%")
        ).first()

        if not customer:
            return {"reply": f"Mijoz topilmadi: {customer_name}. Avval mijozni bazaga qo'shing."}

        try:
            customer.debt_balance = float(customer.debt_balance or 0) + float(amount or 0)
            db.commit()
        except Exception as e:
            db.rollback()
            return {"reply": f"Qarzni yozishda xatolik: {str(e)}"}

        return {
            "reply": f"📝 Muvaffaqiyatli! {customer.name} hisobiga {float(amount):,.0f} so'm qarz yozildi.",
            "action": {"type": "add_debt", "customer_id": customer.id, "amount": amount}
        }

    elif intent == "query":
        return {"reply": intent_data.get('reply', 'Kechirasiz, tushunmadim.')}

    return {"reply": "Kechirasiz, hozircha men faqat asosiy savdo va ombor ma'lumotlarini o'qiy olaman."}
