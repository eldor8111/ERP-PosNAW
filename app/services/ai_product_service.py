import requests
import os
from typing import Optional

TIMEOUT = 30

def generate_product_description(
    name: str,
    category: str,
    api_key: str
) -> Optional[str]:
    """
    OpenRouter yordamida mahsulot uchun marketing description yaratadi.
    """

    url = "https://openrouter.ai/api/v1/chat/completions"

    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "cohere/north-mini-code:free")

    if not api_key:
        print("[AI Product] OPENROUTER_API_KEY sozlanmagan")
        return None

    prompt = (
        "Ushbu mahsulot uchun qisqa, jozibador va sotuvchi marketing "
        "ta'rifi yozing. Faqat ta'rif matnini qaytaring, ortiqcha gaplarsiz.\n\n"
        f"Mahsulot nomi: {name}\n"
        f"Kategoriyasi: {category}\n"
        "Til: O'zbek tili."
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
            {
                "role": "system",
                "content": "Siz professional marketing copywritersiz."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 200,
        "temperature": 0.7
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
                f"[AI Product] HTTP {response.status_code}: "
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
        print(f"[AI Product] Request failed: {e}")
        return None
