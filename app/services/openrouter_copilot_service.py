import requests
import json
import os
from typing import Dict, Any

from app.models.user import User
from app.services.ai_tools_registry import AIToolRegistry

TIMEOUT = 30

def call_copilot_ai(message: str, daily_context: str, api_key: str, user: User = None) -> Dict[str, Any]:
    """
    OpenRouter orqali ERP POS Copilot.
    Tool Registry dan barcha aktiv funksiyalarni olib LLMga uzatadi.
    """

    url = "https://openrouter.ai/api/v1/chat/completions"
    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")

    if not api_key:
        return {"intent": "error", "reply": "OPENROUTER_API_KEY sozlanmagan."}

    system_prompt = (
        "Siz 'E-Code' korxona boshqaruvi tizimining aqlli yordamchisisiz (Copilot). "
        "Foydalanuvchi do'kon rahbari yoki kassir. Siz faqat o'zbek tilida qisqa va aniq javob berasiz.\n\n"
        f"Bugungi holat:\n{daily_context}\n\n"
        "Sizga maxsus Tools (Funksiyalar) berilgan. Agar foydalanuvchining maqsadi biron Tool'ga mos tushsa, "
        "shu Tool'ni chaqiring.\n"
        "DIQQAT: Mijoz ismini olganda HECH QANDAY qo'shimchalarsiz (masalan: 'Asrorni' o'rniga faqat 'Asror' deb) yozing. "
        "Agar krillcha yozilgan bo'lsa, xuddi o'zidek qoldiring."
    )

    tools = AIToolRegistry.get_all_tools_for_llm(user) if user else []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://savdo.e-code.uz",
        "X-Title": "E-Code POS"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        "temperature": 0.1,
    }
    
    if tools:
        payload["tools"] = tools

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        message_obj = data["choices"][0]["message"]
        
        # Agar AI biron-bir tool ishlatsa:
        if message_obj.get("tool_calls"):
            tool_call = message_obj["tool_calls"][0]
            func_name = tool_call["function"]["name"]
            func_args_str = tool_call["function"]["arguments"]
            try:
                func_args = json.loads(func_args_str)
            except:
                func_args = {}

            return {
                "intent": "execute_tool",
                "tool_name": func_name,
                "tool_arguments": func_args
            }

        content = message_obj.get("content") or ""
        return {
            "intent": "query",
            "reply": content.strip()
        }

    except Exception as e:
        return {
            "intent": "error",
            "reply": f"AI ulanishida xatolik: {str(e)}"
        }

def summarize_tool_result_with_llm(original_message: str, tool_name: str, tool_result: dict, api_key: str) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")

    if not api_key:
        return "Natija olindi, lekin AI xulosasi uchun API kalit yo'q."

    system_prompt = (
        "Siz ERP tizimining aqlli tahlilchisisiz. "
        "Foydalanuvchining savoliga asosan bazadan olingan xom (JSON) ma'lumotlarni o'qiysiz va unga qisqa, "
        "tushunarli va chiroyli o'zbek tilida xulosa qilib berasiz. "
        "O'zingizdan raqam to'qimang. Faqat berilgan JSON ma'lumotidagi raqamlardan foydalaning."
    )

    user_prompt = f"Foydalanuvchi so'rovi: {original_message}\nTool nomi: {tool_name}\nBaza natijasi: {json.dumps(tool_result, ensure_ascii=False)}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://savdo.e-code.uz",
        "X-Title": "E-Code POS"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Natija olindi, lekin AI unga xulosa yozolmadi: {str(e)}"
