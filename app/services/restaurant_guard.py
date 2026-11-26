"""R5: restoran chekidan yaratilgan sotuvni umumiy qaytarish / bekor qilish yo'llaridan himoya.

Taom qoldig'i yuritilmaydi (ingredientlar yechilgan), shuning uchun oddiy qaytarish taomni "omborga qaytarib"
noto'g'ri qoldiq hosil qiladi. Restoran cheki restoran bo'limidan qaytariladi (R5.4).
"""
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

RESTAURANT_SALE_DETAIL = {
    "code": "RESTAURANT_SALE",
    "message": "Bu restoran cheki. Uni restoran bo'limidan qaytaring yoki bekor qiling.",
}


def assert_not_restaurant_sale(db: Session, sale_id: Optional[int]) -> None:
    if not sale_id:
        return
    from app.models.restaurant_order import RestaurantOrder
    if db.query(RestaurantOrder.id).filter(RestaurantOrder.sale_id == sale_id).first():
        raise HTTPException(status_code=409, detail=RESTAURANT_SALE_DETAIL)


def assert_no_restaurant_items(db: Session, product_ids: Iterable[int]) -> None:
    """Asl sotuvsiz qaytarishda ham taom / xizmat haqi qaytarilmasin (o'z qoldig'i yo'q)."""
    ids = [int(i) for i in set(product_ids or []) if i]
    if not ids:
        return
    from app.models.product import NO_STOCK_ITEM_KINDS, Product
    bad = db.query(Product.name).filter(Product.id.in_(ids), Product.item_kind.in_(NO_STOCK_ITEM_KINDS)).first()
    if bad:
        raise HTTPException(status_code=409, detail={
            "code": "RESTAURANT_ITEM",
            "message": f"'{bad[0]}' restoran taomi: u restoran bo'limidan qaytariladi.",
        })
