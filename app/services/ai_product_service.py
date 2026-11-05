import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_product_description(
    name: str,
    category: str,
    api_key: Optional[str] = None
) -> Optional[str]:
    """Mahsulot uchun qisqa marketing ta'rifi (Claude). Xato bo'lsa None.
    `api_key` eski chaqiruvlar uchun qoldirilgan, ishlatilmaydi (kalit faqat .env da)."""
    from app.services import claude_text

    prompt = (
        "Ushbu mahsulot uchun qisqa (2-3 gap), jozibador va sotuvchi marketing ta'rifi yozing. "
        "Faqat ta'rif matnini qaytaring, sarlavha va emojisiz.\n\n"
        f"Mahsulot nomi: {name}\n"
        f"Kategoriyasi: {category}\n"
        "Til: o'zbek tili, lotin yozuvi."
    )
    return claude_text.complete("Siz professional marketing kopirayterisiz.", prompt, max_tokens=500)
