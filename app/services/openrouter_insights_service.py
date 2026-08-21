import requests
import os
from typing import Optional, List

TIMEOUT = 30

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
    OpenRouter yordamida kunlik savdo bo'yicha AI insight yaratadi.
    Shaxsiy ma'lumotlar yuborilmaydi.
    """

    url = "https://openrouter.ai/api/v1/chat/completions"

    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")

    if not api_key:
        print("[AI Insight] OPENROUTER_API_KEY sozlanmagan")
        return None

    system_prompt = (
        "Siz korxona rahbarlari uchun kunlik savdo hisobotlarini yozuvchi "
        "professional moliyaviy tahlilchisiz. "
        "Ma'lumotlarga qarab qisqa xulosa va 1-2 ta amaliy maslahat bering. "
        "Matn tushunarli, rasmiy va o'zbek tilida bo'lsin. "
        "Emojilardan me'yorida foydalaning."
    )

    fmt = lambda x: f"{x:,.0f} so'm"

    trend = (
        f"+{growth_pct:.1f}% o'sish"
        if growth_pct >= 0
        else f"{growth_pct:.1f}% pasayish"
    )

    user_prompt = (
        f"Korxona: {company_name}\n"
        f"Bugungi tranzaksiyalar: {sales_count} ta\n"
        f"Jami tushum: {fmt(total_sales)}\n"
        f"Naqd: {fmt(cash)} | Karta: {fmt(card)} | Nasiya: {fmt(debt_added)}\n"
        f"Kechagiga nisbatan dinamika: {trend}\n"
        f"Top mahsulotlar: "
        f"{', '.join(top_products) if top_products else "yo'q"}\n"
        f"Kam qolgan tovarlar turlari: {low_stock_count} ta\n"
        f"Muddati o'tgan qarzdorlar soni: {overdue_count} ta\n\n"
        "Shu ma'lumotlarga asoslanib rahbariyat uchun chiroyli, "
        "qisqa xulosa va maslahat yozing."
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "E-Code ERP POS"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 300,
        "temperature": 0.5
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=TIMEOUT
        )

        if response.status_code != 200:
            print(
                f"[AI Insight] HTTP {response.status_code}: "
                f"{response.text[:2000]}"
            )
            return None

        data = response.json()
        choices = data.get("choices", [])

        if not choices:
            return None

        content = choices[0].get("message", {}).get("content")
        return content.strip() if content else None

    except Exception as e:
        print(f"[AI Insight] Request failed: {e}")
        return None
