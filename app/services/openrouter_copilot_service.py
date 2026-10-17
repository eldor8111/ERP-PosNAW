import requests
import json
import os
from typing import Dict, Any

import logging

from app.config import settings
from app.models.user import User
from app.services.ai_tools_registry import AIToolRegistry

logger = logging.getLogger(__name__)

TIMEOUT = 45
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

AI_UNAVAILABLE_REPLY = "AI vaqtincha ishlamayapti. Birozdan so'ng qayta urinib ko'ring."


def _model_chain() -> list:
    """OPENROUTER_MODEL, so'ng OPENROUTER_FALLBACK_MODELS (vergul bilan) — takrorlarsiz, tartib saqlanadi."""
    candidates = [settings.OPENROUTER_MODEL] + (settings.OPENROUTER_FALLBACK_MODELS or "").split(",")
    chain = []
    for m in (c.strip() for c in candidates):
        if m and m not in chain:
            chain.append(m)
    return chain


def call_copilot_ai(message: str, daily_context: str, api_key: str, user: User = None, conversation_history: list = None) -> Dict[str, Any]:
    """
    LLMProvider (OpenRouter, Anthropic, OpenAI, Mock) orqali ERP POS Copilot.
    Tool Registry dan barcha aktiv funksiyalarni olib LLMga uzatadi.
    """
    from app.ai import get_llm_router

    api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
    models_to_try = _model_chain()
    model = models_to_try[0] if models_to_try else ""

    primary_prov = (getattr(settings, "LLM_PROVIDER", "") or "openrouter").lower()
    if primary_prov == "openrouter":
        if not api_key:
            return {"intent": "error", "reply": "OPENROUTER_API_KEY sozlanmagan."}
        if not model:
            return {"intent": "error", "reply": "OPENROUTER_MODEL sozlanmagan."}

    system_prompt = (
        "Siz 'E-Code' korxona boshqaruvi tizimining aqlli yordamchisisiz (Copilot). "
        "Foydalanuvchi do'kon rahbari yoki kassir. Siz faqat o'zbek tilida qisqa va aniq javob berasiz.\n\n"
        f"Bugungi holat:\n{daily_context}\n\n"
        "Sizga maxsus Tools (Funksiyalar) berilgan. Agar foydalanuvchining maqsadi biron Tool'ga mos tushsa, "
        "shu Tool'ni chaqiring.\n"
        "DIQQAT: Mijoz ismini olganda HECH QANDAY qo'shimchalarsiz (masalan: 'Asrorni' o'rniga faqat 'Asror' deb) yozing. "
        "Agar krillcha yozilgan bo'lsa, xuddi o'zidek qoldiring.\n"
        "FILIAL: Agar foydalanuvchi aniq filial so'rasa, vositalarning `branch` parametrini shu filial nomi bilan to'ldiring; "
        "aniq filial so'ramasa `branch` ni bo'sh qoldiring. Javobda doirani (masalan 'Yunusobod filiali' yoki 'Butun korxona') "
        "vosita natijasidagi yorliqqa muvofiq aniq ayting; butun korxona raqamlarini filial raqami deb aytmang. "
        "Filial bo'yicha ma'lumot bo'lmasa (masalan, qarz filial bo'yicha ajratilmagan), buni aniq ayting."
    )

    tools = AIToolRegistry.get_all_tools_for_llm(user) if user else []

    messages_list = []
    if conversation_history:
        messages_list.extend(conversation_history[-10:])
    messages_list.append({"role": "user", "content": message})

    router = get_llm_router()
    last_error = ""

    for attempt_model in models_to_try:
        try:
            resp = router.chat(
                system=system_prompt,
                messages=messages_list,
                tools=tools,
                model=attempt_model,
                temperature=0.1,
                allow_local_fallback=False,
            )

            if resp.has_tool_calls:
                tc = resp.tool_calls[0]
                return {
                    "intent": "execute_tool",
                    "tool_name": tc.name,
                    "tool_arguments": tc.arguments,
                }

            return {
                "intent": "query",
                "reply": resp.text.strip(),
            }
        except Exception as e:
            last_error = f"{attempt_model}: {e}"
            logger.warning("[AI Copilot] model ishlamadi: %s", last_error)
            continue

    logger.error("[AI Copilot] barcha modellar ishlamadi: %s", last_error)
    return {
        "intent": "error",
        "reply": AI_UNAVAILABLE_REPLY,
    }


def summarize_tool_result_with_llm(original_message: str, tool_name: str, tool_result: Any, api_key: str) -> str:
    # Agar tool_result dict bo'lsa va allaqachon tayyor 'reply' bo'lsa, to'g'ridan qaytaramiz
    if isinstance(tool_result, dict) and tool_result.get("reply"):
        return str(tool_result["reply"])
    if isinstance(tool_result, str) and not (tool_result.startswith("{") or tool_result.startswith("[")):
        # Agar oddiy matn bo'lsa, AI xulosasi kerak emas
        return tool_result

    api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
    models_to_try = _model_chain()
    model = models_to_try[0] if models_to_try else ""

    if not api_key or not model:
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

    for attempt_model in models_to_try:
        payload["model"] = attempt_model
        try:
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=TIMEOUT)
            if resp.status_code in (403, 402):
                continue
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning("[AI Copilot] xulosa modeli ishlamadi %s: %s", attempt_model, e)
            continue

    if isinstance(tool_result, dict):
        return tool_result.get("reply", "Natija olindi, lekin AI unga xulosa yozolmadi.")
    return "Natija olindi, lekin AI unga xulosa yozolmadi."
