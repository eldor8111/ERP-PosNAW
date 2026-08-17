import requests
import json
import os
from typing import Optional, List

TIMEOUT = 12

def generate_daily_insight(
    company_name: str,
    total_sales: float,
    sales_count: int,
    cash: float,
    card: float,
    debt_added: float,
    growth_pct: float,
    low_stock_count: int,
    overdue_count: int,
    top_products: List[str],
    api_key: str
) -> Optional[str]:
    """
    Bytez API yordamida umumiylashtirilgan (Aggregated) ma'lumotlardan 
    aqlli boshqaruv xulosasini (insight) generatsiya qiladi.
    Shaxsiy ma'lumotlar (PII) jo'natilmaydi!
    """
    url = "https://api.bytez.com/v1/chat/completions"
    
    # 1. PII-siz (Shaxsiy ma'lumotlarsiz) so'rov matnini tayyorlash
    system_prompt = (
        "Siz korxona rahbarlari uchun kunlik savdo hisobotlarini yozib beruvchi professional "
        "moliyaviy tahlilchisiz. Ma'lumotlarga qarab xulosa va 1-2 ta maslahat bering. "
        "Matn qisqa, tushunarli, rasmiy va o'zbek tilida bo'lishi shart. Emojilardan foydalaning."
    )
    
    # Raqamlarni chiroyli formatlash
    fmt = lambda x: f"{x:,.0f} so'm"
    trend = f"+{growth_pct:.1f}% o'sish" if growth_pct >= 0 else f"{growth_pct:.1f}% pasayish"
    
    user_prompt = (
        f"Korxona: {company_name}\n"
        f"Bugungi tranzaksiyalar: {sales_count} ta\n"
        f"Jami tushum: {fmt(total_sales)}\n"
        f"Naqd: {fmt(cash)} | Karta: {fmt(card)} | Nasiya: {fmt(debt_added)}\n"
        f"Kechagiga nisbatan dinamika: {trend}\n"
        f"Top mahsulotlar: {', '.join(top_products) if top_products else 'yoq'}\n"
        f"Kam qolgan tovarlar turlari: {low_stock_count} ta\n"
        f"Muddati o'tgan qarzdorlar soni: {overdue_count} ta\n\n"
        "Shu ma'lumotlarga asoslanib rahbariyat uchun chiroyli xulosa yozib bering."
    )
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "openai/gpt-3.5-turbo", # Bytez unified model standard
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 300,
        "temperature": 0.5
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"].strip()
        return None
    except Exception as e:
        print(f"[AI Insight] Request failed: {e}")
        return None
