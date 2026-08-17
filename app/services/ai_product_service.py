import requests
from typing import Optional

# Standard timeout to prevent blocking (10 seconds)
TIMEOUT = 10 

def generate_product_description(name: str, category: str, api_key: str) -> Optional[str]:
    """
    Generates a marketing description for a product using Bytez API (OpenAI format).
    Returns None if there is an error or timeout.
    """
    # Bytez uses the standard OpenAI chat/completions schema
    url = "https://api.bytez.com/v1/chat/completions"
    
    prompt = (
        f"Iltimos, ushbu mahsulot uchun qisqa, jozibador va sotuvchi (marketing) "
        f"ta'rif (description) yozib bering. Faqat ta'rif matnini qaytaring, ortiqcha gaplarsiz.\n"
        f"Mahsulot nomi: {name}\n"
        f"Kategoriyasi: {category}\n"
        f"Til: O'zbek tili."
    )
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # We use Qwen or Llama, or just general OpenAI format models via Bytez
    # Fallback to openai/gpt-3.5-turbo if needed, Bytez proxies this.
    payload = {
        "model": "openai/gpt-3.5-turbo", 
        "messages": [
            {"role": "system", "content": "You are a professional marketing copywriter."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 200,
        "temperature": 0.7
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"].strip()
        else:
            print(f"[AI Service] Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"[AI Service] Request failed: {e}")
        return None
