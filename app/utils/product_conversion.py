"""Tarkibiy (virtual) mahsulot konversiyasi yordamchi funksiyalari."""
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.product import Product, ProductConversion


def get_conversion_for_sell(
    db: Session, product_id: int
) -> Tuple[Optional[ProductConversion], Optional[Product]]:
    """Sotiladigan mahsulot uchun konversiya va asosiy mahsulotni qaytaradi."""
    conversion = (
        db.query(ProductConversion)
        .filter(ProductConversion.sell_product_id == product_id)
        .first()
    )
    if not conversion:
        return None, None
    source = (
        db.query(Product)
        .filter(
            Product.id == conversion.source_product_id,
            Product.is_deleted == False,
        )
        .first()
    )
    if not source:
        return None, None
    return conversion, source


def deduct_target_for_sale(
    db: Session, product_id: int, quantity: Decimal
) -> Tuple[int, Decimal, Optional[ProductConversion], Optional[Product]]:
    """
    Sotuvda qaysi mahsulotdan qancha yechilishini aniqlaydi.
    Returns: (deduct_product_id, deduct_qty, conversion, source_product)
    """
    conversion, source = get_conversion_for_sell(db, product_id)
    if conversion and source:
        ratio = Decimal(str(conversion.ratio))
        return source.id, quantity * ratio, conversion, source
    return product_id, quantity, None, None
