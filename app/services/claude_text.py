"""Qisqa matn yaratish uchun Claude (rasmiy anthropic SDK): kunlik xulosa, mahsulot ta'rifi.

Vositasiz, bitta so'rov. Xato bo'lsa None qaytaradi — chaqiruvchi o'z zaxira matnini ishlatadi
(zaxira matn hech qachon "AI javobi" sifatida keshlanmaydi).
"""
import logging
from typing import Optional

import anthropic

from app.config import settings

log = logging.getLogger("claude_text")


def company_has_ai(db, company_id) -> bool:
    """Korxonada faol AI yordamchi paketi bormi (pullik AI imkoniyatlari shu paketga bog'langan)."""
    if not company_id:
        return False
    from app.services.ai_packages import access_for
    return access_for(db, company_id).active


def complete(system: str, prompt: str, max_tokens: int = 1200, effort: str = "low") -> Optional[str]:
    if not settings.ANTHROPIC_API_KEY:
        return None
    from app.services.ai_assistant import get_client
    try:
        msg = get_client().messages.create(
            model=settings.AI_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort},
        )
    except anthropic.AnthropicError as e:
        log.warning("claude_text: so'rov bajarilmadi: %s", type(e).__name__)
        return None
    if msg.stop_reason == "refusal":
        return None
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    return text or None
