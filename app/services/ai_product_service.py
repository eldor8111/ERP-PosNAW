import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def generate_product_description(
    name: str,
    category: str,
    api_key: Optional[str] = None
) -> Optional[str]:
    """
    LLMProvider (OpenRouter / Anthropic / OpenAI / Mock) yordamida mahsulot uchun marketing description yaratadi.
    Fast model orqali tejamkor va tezkor javob qaytaradi.
    """
    from app.ai import get_llm_router

    prompt = (
        "Ushbu mahsulot uchun qisqa, jozibador va sotuvchi marketing "
        "ta'rifi yozing. Faqat ta'rif matnini qaytaring, ortiqcha gaplarsiz.\n\n"
        f"Mahsulot nomi: {name}\n"
        f"Kategoriyasi: {category}\n"
        "Til: O'zbek tili."
    )

    try:
        router = get_llm_router()
        resp = router.chat(
            system="Siz professional marketing copywritersiz.",
            messages=[{"role": "user", "content": prompt}],
            task_type="fast",
            max_tokens=200,
            temperature=0.7,
        )
        if resp and resp.text:
            return resp.text.strip()
        return None
    except Exception as e:
        logger.warning(f"[AI Product] Tavsif generatsiyasi xatosi: {e}")
        return None

