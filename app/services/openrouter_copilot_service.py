import requests
import json
import os
from typing import Dict, Any

TIMEOUT = 30

def call_copilot_ai(message: str, daily_context: str, api_key: str) -> Dict[str, Any]:
    """
    OpenRouter orqali ERP POS Copilot.
    Tool Calling yordamida qarz/nasiya operatsiyalarini aniqlaydi.
    """

    url = "https://openrouter.ai/api/v1/chat/completions"

    # api_key argumenti bo'lmasa .env dan olamiz
    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")

    if not api_key:
        return {
            "intent": "error",
            "reply": "OPENROUTER_API_KEY sozlanmagan."
        }

    system_prompt = (
        "Siz 'E-Code' korxona boshqaruvi tizimining aqlli yordamchisisiz (Copilot). "
        "Foydalanuvchi do'kon rahbari yoki kassir. "
        "Siz foydalanuvchining maqsadini tushunib, kerak bo'lsa maxsus funksiyani chaqirasiz.\n\n"
        f"Bugungi holat (faqat ma'lumot uchun):\n{daily_context}\n\n"
        "Agar foydalanuvchi qarz/nasiya TO'LAGANINI aytsa, record_debt_payment funksiyasini chaqiring.\n"
        "Agar foydalanuvchi yangi nasiya/qarz YOZISHNI so'rasa, record_new_debt funksiyasini chaqiring.\n"
        "Agar foydalanuvchi mijozning QARZINI SO'RASA (masalan: 'Ali qancha qarzi bor?'), check_customer_debt funksiyasini chaqiring.\n"
        "Boshqa savollarga o'zbek tilida qisqa va aniq javob bering."
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "record_debt_payment",
                "description": "Mijoz qarzini/nasiyasini qaytarib to'laganda ishlatiladi.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_name": {
                            "type": "string",
                            "description": "Qarzini to'lagan mijozning ismi."
                        },
                        "amount": {
                            "type": "number",
                            "description": "To'langan summa."
                        }
                    },
                    "required": ["customer_name", "amount"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "record_new_debt",
                "description": "Mijoz do'kondan nasiyaga mol olib ketganda ishlatiladi.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_name": {
                            "type": "string",
                            "description": "Qarzga mol olgan mijozning ismi."
                        },
                        "amount": {
                            "type": "number",
                            "description": "Nasiya summasi."
                        }
                    },
                    "required": ["customer_name", "amount"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_customer_debt",
                "description": "Mijozning hozirgi qarzini bilish uchun ishlatiladi.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_name": {
                            "type": "string",
                            "description": "Qarzi tekshirilayotgan mijozning ismi."
                        }
                    },
                    "required": ["customer_name"]
                }
            }
        }
    ]

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
            {"role": "user", "content": message}
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 300,
        "temperature": 0.2
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=TIMEOUT
        )

        if response.status_code != 200:
            print(f"[Copilot AI] HTTP {response.status_code}: {response.text[:2000]}")
            return {
                "intent": "error",
                "reply": "Kechirasiz, sun'iy intellekt xizmatida nosozlik yuz berdi."
            }

        data = response.json()

        choices = data.get("choices", [])
        if not choices:
            return {
                "intent": "error",
                "reply": "AI javob qaytarmadi."
            }

        message_obj = choices[0].get("message", {})

        tool_calls = message_obj.get("tool_calls") or []

        if tool_calls:
            tool_call = tool_calls[0]
            function = tool_call.get("function", {})
            func_name = function.get("name")
            raw_args = function.get("arguments", "{}")

            try:
                func_args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                func_args = {}

            if func_name == "record_debt_payment":
                return {
                    "intent": "debt_payment",
                    "customer_name": func_args.get("customer_name"),
                    "amount": func_args.get("amount")
                }

            if func_name == "record_new_debt":
                return {
                    "intent": "add_debt",
                    "customer_name": func_args.get("customer_name"),
                    "amount": func_args.get("amount")
                }

            if func_name == "check_customer_debt":
                return {
                    "intent": "check_debt",
                    "customer_name": func_args.get("customer_name")
                }

        content = message_obj.get("content") or ""

        return {
            "intent": "query",
            "reply": content.strip()
        }

    except requests.Timeout:
        print("[Copilot AI] Request timeout")
        return {
            "intent": "error",
            "reply": "AI server javob berishi uchun vaqt tugadi."
        }

    except Exception as e:
        print(f"[Copilot AI] Request failed: {e}")
        return {
            "intent": "error",
            "reply": "Internet aloqasida yoki AI serverida muammo yuz berdi."
        }
