"""
Mahsulot qidiruvi uchun umumiy filter yordamchilari.
products.py va product_search.py ikkalasi ham shu moduldan foydalanadi.
"""
from sqlalchemy import and_, or_
from app.models.product import Product
from app.utils.translit import translit_variants as _translit_variants


def _word_condition(word: str):
    """Bitta so'z uchun translit-aware OR filter (name, sku, barcode, ...)."""
    variants = _translit_variants(word)
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
    """
    words = [w for w in search.strip().split() if w]
    if not words:
        from sqlalchemy import true
        return true()
    return and_(*[_word_condition(w) for w in words])
