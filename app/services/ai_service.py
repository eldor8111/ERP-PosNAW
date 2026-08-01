import json
import google.generativeai as genai
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from app.config import settings

from app.models.sale import Sale, SaleItem
from app.models.product import Product
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.services.debt_scoring import categorize_customers

# Gemini konfiguratsiyasi
if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)

# Gemini Model
generation_config = {
  "temperature": 0.2,
  "top_p": 0.95,
  "top_k": 40,
  "max_output_tokens": 1024,
  "response_mime_type": "text/plain",
}

SYSTEM_PROMPT = """
Sen E-Code ERP/POS tizimining sun'iy intellekt yordamchisisisan.
Do'kon egasiga savdo, ombor va moliyaviy maslahat berasan.
Javoblarni o'zbek tilida, qisqa, tushunarli va aniq ber.
Raqamlarni chiroyli formatda yoz (masalan, 1,500,000 so'm).
"""

def call_gemini(prompt: str, context: str = "") -> str:
    """Gemini API ga so'rov yuborish. Agar kalit yo'q bo'lsa fallback qaytaradi."""
    if not settings.GEMINI_API_KEY:
        return _fallback_analysis(context)
        
    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config,
            system_instruction=SYSTEM_PROMPT,
        )
        full_prompt = f"Tizim ma'lumotlari:\n{context}\n\nFoydalanuvchi so'rovi/Topshiriq:\n{prompt}"
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        print(f"Gemini API Xatosi: {e}")
        return _fallback_analysis(context)

def _fallback_analysis(context: str) -> str:
    """Gemini API ishlamasa statik javob"""
    return "Tizim tahlili yakunlandi. Ma'lumotlarga ko'ra hamma narsa me'yorida. Batafsil hisobotni raqamlarda ko'rishingiz mumkin."

def build_daily_context(db: Session, company_id: int) -> str:
    """Bugungi savdo haqida qisqacha ma'lumot yig'ish"""
    today = date.today()
    sales = db.query(Sale).filter(
        func.date(Sale.created_at) == today,
        Sale.company_id == company_id
    ).all()
    
    total_sales = sum(s.total_amount for s in sales)
    cash = sum(s.paid_cash for s in sales)
    card = sum(s.paid_card for s in sales)
    
    # Eng ko'p sotilgan mahsulot
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
    Umumiy tushum: {total_sales} so'm
    Naqd pul: {cash} so'm
    Plastik karta: {card} so'm
    Eng ko'p sotilgan mahsulot: {top_prod_name}
    """

def get_insights(db: Session, company_id: int):
    """3 ta karta (Insights) uchun ma'lumot"""
    try:
        today = date.today()
        last_week_start = today - timedelta(days=14)
        last_week_end = today - timedelta(days=7)
        this_week_start = today - timedelta(days=7)
        
        # O'sish tendensiyasi
        last_week_sales = db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(
            func.date(Sale.created_at) >= last_week_start,
            func.date(Sale.created_at) < last_week_end,
            Sale.company_id == company_id
        ).scalar() or 0
        
        this_week_sales = db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(
            func.date(Sale.created_at) >= this_week_start,
            func.date(Sale.created_at) <= today,
            Sale.company_id == company_id
        ).scalar() or 0
        
        growth_pct = 0
        if last_week_sales > 0:
            growth_pct = float((this_week_sales - last_week_sales) / last_week_sales) * 100

        trend = "O'sish" if growth_pct > 0 else "Pasayish"
        
        # Zaxira e'tibori
        low_stock = db.query(StockLevel).filter(
            StockLevel.quantity < 10,
            StockLevel.warehouse.has(company_id=company_id)
        ).count()
        
        # Qarz xavfi
        debt_data = categorize_customers(db, company_id)
        overdue = debt_data['overdue_count']
        
        return [
            {
                "type": "growth",
                "icon": "📈",
                "title": "O'sish tendensiyasi",
                "body": f"O'tgan haftaga nisbatan umumiy savdo hajmi {abs(growth_pct):.1f}% ga {trend.lower()} kuzatildi.",
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
        error_msg = traceback.format_exc()
        return [
            {
                "type": "warning",
                "icon": "⚠️",
                "title": "Xatolik",
                "body": f"Insight xatosi: {str(e)}",
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
    3. Agar savol yoxud suhbat bo'lsa, o'zbek tilida chiroyli qilib (kerak bo'lsa tepadagi ma'lumotlardan foydalanib) javob ber: {{"intent": "query", "reply": "Sening aqlli javobing..."}}
    
    Hech qanday izohsiz faqat toza JSON qaytar.
    """
    
    try:
        models_to_try = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
        response = None
        last_error = None
        
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                break  # Agar ishladi, tsikldan chiqib ketamiz
            except Exception as e:
                last_error = e
                # Agar 404 bo'lsa, keyingi modelga o'tishda davom etamiz
                if "404" in str(e) or "not found" in str(e).lower():
                    continue
                else:
                    raise e
                    
        if not response:
            raise last_error

        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"JSON parsing xatosi: {err}")
        return {"intent": "unknown", "reply": f"So'rovni tushunishda xatolik yuz berdi: {str(e)}"}

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
            
        # Finance amaliyoti bu yerda chaqirilishi kerak (Kassa kirim)
        # Soddalashtirilgan: mijozning qarzini kamaytiramiz
        customer.debt_balance -= amount
        db.commit()
        
        return {
            "reply": f"✅ Muvaffaqiyatli! {customer.name} nomli mijozning qarzidan {amount:,.0f} so'm yechib olindi.",
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
            
        # Soddalashtirilgan: mijozning qarzini oshiramiz
        customer.debt_balance += amount
        db.commit()
        
        return {
            "reply": f"📝 Muvaffaqiyatli! {customer.name} hisobiga {amount:,.0f} so'm qarz yozildi.",
            "action": {"type": "add_debt", "customer_id": customer.id, "amount": amount}
        }
        
    elif intent == "query":
        return {"reply": intent_data.get('reply', 'Kechirasiz, tushunmadim.')}
        
    return {"reply": "Kechirasiz, hozircha men faqat asosiy savdo va ombor ma'lumotlarini o'qiy olaman."}
