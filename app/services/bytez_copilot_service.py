import requests
import json
import os
from typing import Dict, Any

TIMEOUT = 12

def call_copilot_ai(message: str, daily_context: str, api_key: str) -> Dict[str, Any]:
    """
    Bytez API (OpenAI format) orqali Copilot bilan chat.
    Tool Calling (Function Calling) ishlatiladi.
    """
    url = "https://api.bytez.com/v1/chat/completions"
    
    # 1. System Prompt
    system_prompt = (
        "Siz 'E-Code' korxona boshqaruvi tizimining aqlli yordamchisisiz (Copilot). "
        "Foydalanuvchi do'kon rahbari yoki kassir. "
        "Sizning vazifangiz ularning muloqotidagi maqsadni tushunish. "
        f"Bugungi holat (Faqat ma'lumot uchun, o'zgartira olmaysiz):\n{daily_context}\n\n"
        "Foydalanuvchi qarz/nasiya to'lash yoki yozishni so'rasa, MAXSUS FUNKSIYALARDAN (tools) birini chaqiring. "
        "Agar foydalanuvchi bugungi savdo yoki boshqa narsa haqida ma'lumot so'rasa, funksiya chaqirmasdan o'zbek tilida qisqa va aniq javob qaytaring."
    )
    
    # 2. Xavfsiz funksiyalar ro'yxati (Tools)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "record_debt_payment",
                "description": "Mijoz o'zining qarzini (nasiyasini) qaytarib to'laganda ishlatiladi.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_name": {"type": "string", "description": "Qarzini to'lagan mijozning ismi. Masalan: Ali, Valijon."},
                        "amount": {"type": "number", "description": "To'langan summa miqdori (faqat raqam)."}
                    },
                    "required": ["customer_name", "amount"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "record_new_debt",
                "description": "Mijoz do'kondan nasiyaga (qarzga) mol olib ketganda (yangi qarz) ishlatiladi.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_name": {"type": "string", "description": "Qarzga mol olgan mijozning ismi."},
                        "amount": {"type": "number", "description": "Nasiya olingan tovarning summasi (faqat raqam)."}
                    },
                    "required": ["customer_name", "amount"]
                }
            }
        }
    ]
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "openai/gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 150,
        "temperature": 0.2
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                message_obj = data["choices"][0]["message"]
                
                # Agar AI Tool (Funksiya) chaqirmoqchi bo'lsa
                if "tool_calls" in message_obj and message_obj["tool_calls"]:
                    tool_call = message_obj["tool_calls"][0]
                    func_name = tool_call["function"]["name"]
                    func_args = json.loads(tool_call["function"]["arguments"])
                    
                    if func_name == "record_debt_payment":
                        return {"intent": "debt_payment", "customer_name": func_args.get("customer_name"), "amount": func_args.get("amount")}
                    elif func_name == "record_new_debt":
                        return {"intent": "add_debt", "customer_name": func_args.get("customer_name"), "amount": func_args.get("amount")}
                
                # Aks holda shunchaki matn (maslahat yoki statistika)
                return {"intent": "query", "reply": message_obj.get("content", "").strip()}
                
        return {"intent": "error", "reply": "Kechirasiz, sun'iy intellekt xizmatida nosozlik yuz berdi."}
    except Exception as e:
        print(f"[Copilot AI] Request failed: {e}")
        return {"intent": "error", "reply": "Internet aloqasida yoki serverda muammo yuz berdi."}
