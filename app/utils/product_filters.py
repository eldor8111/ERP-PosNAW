"""
Mahsulot qidiruvi uchun umumiy filter yordamchilari.
products.py va product_search.py ikkalasi ham shu moduldan foydalanadi.
"""
from sqlalchemy import and_, or_
from app.models.product import Product
from app.utils.translit import translit_variants as _translit_variants

# Barcha apostrof/tutuq belgilari → ASCII ' (U+0027) ga normalashtirish
# O'zbek klaviaturasida qo'y, o'n, g'isht kabi so'zlar turli belgilar bilan yoziladi
_APOSTROPHES = (
    "\u2019",  # RIGHT SINGLE QUOTATION MARK '
    "\u2018",  # LEFT SINGLE QUOTATION MARK '
    "\u02bc",  # MODIFIER LETTER APOSTROPHE ʼ
    "\u0060",  # GRAVE ACCENT `
    "\u00b4",  # ACUTE ACCENT ´
    "\u02b9",  # MODIFIER LETTER PRIME ʹ
    "\u0022",  # QUOTATION MARK (double) -- just in case
)


def _normalize(text: str) -> str:
    """Barcha apostrof turlarini ASCII ' ga almashtiradi va kichik harfga o'tkazadi."""
    t = text.lower().strip()
    for apos in _APOSTROPHES:
        t = t.replace(apos, "'")
    return t


def _word_variants(word: str) -> list:
    """
    Bitta so'z uchun barcha qidiruv variantlarini qaytaradi:
    - Normallashtirilgan (apostroflar tekislangan)
    - Transliteratsiya (Kirill ↔ Lotin)
    - Apostrofsiz variant (qoʻy → qoy) — foydalanuvchi yoki baza xato yozgan bo'lishi mumkin
    """
    normalized = _normalize(word)
    base_variants = _translit_variants(normalized)

    # Apostrofsiz versiya ham qo'shamiz (qo'y → qoy, o'n → on)
    stripped_variants = []
    for v in base_variants:
        stripped = v.replace("'", "")
        if stripped and stripped not in base_variants:
            stripped_variants.append(stripped)

    # Original (normallashtirilmagan) versiyani ham kiritamiz — DB da turlicha saqlanishi mumkin
    original = word.lower().strip()
    all_variants = list(dict.fromkeys([original, normalized] + base_variants + stripped_variants))
    return all_variants


def _word_condition(word: str):
    """Bitta so'z uchun translit-aware OR filter (name, sku, barcode, ...)."""
    variants = _word_variants(word)
    return or_(
        *[Product.name.ilike(f"%{v}%") for v in variants],
        *[Product.sku.ilike(f"%{v}%") for v in variants],
        *[Product.barcode.ilike(f"%{v}%") for v in variants],
        *[Product.product_code.ilike(f"%{v}%") for v in variants],
        *[Product.extra_barcodes.ilike(f"%{v}%") for v in variants],
        *[Product.extra_product_codes.ilike(f"%{v}%") for v in variants],
    )


def name_filter(search: str):
    """
    Ko'p so'zli, translit-aware qidiruv filtri.
    Har bir so'z AND bilan: 'un turon' → TURON UN 10KG topiladi.
    Apostrof normalizatsiyasi: qoʻy = qo'y = qo`y = qoy barchasi topiladi.
    """
    words = [w for w in _normalize(search).split() if w]
    if not words:
        from sqlalchemy import true
        return true()
    return and_(*[_word_condition(w) for w in words])
