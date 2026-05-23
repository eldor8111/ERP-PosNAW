"""
Tarkibiy (virtual) mahsulotlarni tuzatish: Dumba -> asosiy mahsulot bog'lanishi.
Ishlatish:
  python fix_virtual_products.py          # faqat ko'rsatadi
  python fix_virtual_products.py --apply  # DB ga yozadi
"""
import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")

from decimal import Decimal

from app.database import SessionLocal
from app.models.inventory import StockLevel
from app.models.product import Product, ProductConversion


def find_pair(db):
    """Dumba (sell) va asosiy go'sht (stock) juftligini topish."""
    sell_candidates = (
        db.query(Product)
        .filter(Product.is_deleted == False, Product.name.ilike("%dumba%"))
        .all()
    )
    stock_candidates = (
        db.query(Product)
        .filter(
            Product.is_deleted == False,
            Product.name.ilike("%qo%y%"),
            Product.product_type != "sell",
        )
        .all()
    )
    if not sell_candidates:
        sell_candidates = (
            db.query(Product)
            .filter(Product.is_deleted == False, Product.product_type == "sell")
            .all()
        )
    return sell_candidates, stock_candidates


def fix_product(db, sell_product: Product, source_product: Product, apply: bool) -> list[str]:
    actions = []
    conv = (
        db.query(ProductConversion)
        .filter(ProductConversion.sell_product_id == sell_product.id)
        .first()
    )

    if sell_product.product_type != "sell":
        actions.append(f"  product_type: {sell_product.product_type!r} -> 'sell'")
        if apply:
            sell_product.product_type = "sell"

    if not conv:
        actions.append(
            f"  yangi conversion: sell={sell_product.name!r} -> source={source_product.name!r} ratio=1"
        )
        if apply:
            db.add(
                ProductConversion(
                    sell_product_id=sell_product.id,
                    source_product_id=source_product.id,
                    ratio=Decimal("1"),
                )
            )
    elif conv.source_product_id != source_product.id:
        actions.append(
            f"  conversion source: {conv.source_product_id} -> {source_product.id}"
        )
        if apply:
            conv.source_product_id = source_product.id
            conv.ratio = Decimal("1")

    stocks = db.query(StockLevel).filter(StockLevel.product_id == sell_product.id).all()
    if stocks:
        actions.append(f"  o'chirish: {len(stocks)} ta StockLevel (virtual mahsulotda qoldiq bo'lmasin)")
        if apply:
            db.query(StockLevel).filter(StockLevel.product_id == sell_product.id).delete(
                synchronize_session=False
            )

    if source_product.product_type == "sell":
        actions.append(f"  source product_type: 'sell' -> 'stock'")
        if apply:
            source_product.product_type = "stock"

    return actions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="O'zgarishlarni saqlash")
    parser.add_argument("--sell-id", type=int, help="Tarkibiy mahsulot ID (Dumba)")
    parser.add_argument("--source-id", type=int, help="Asosiy mahsulot ID (Qo'y go'shti)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.sell_id and args.source_id:
            sell_p = db.query(Product).filter(Product.id == args.sell_id).first()
            source_p = db.query(Product).filter(Product.id == args.source_id).first()
            if not sell_p or not source_p:
                print("Mahsulot topilmadi")
                return 1
            pairs = [(sell_p, source_p)]
        else:
            sell_list, stock_list = find_pair(db)
            if not sell_list:
                print("Tarkibiy (Dumba) mahsulot topilmadi")
                return 1
            if not stock_list:
                print("Asosiy (Qo'y go'shti) mahsulot topilmadi")
                return 1
            pairs = [(sell_list[0], stock_list[0])]

        print("=== Tarkibiy mahsulot tuzatish ===\n")
        any_action = False
        for sell_p, source_p in pairs:
            if sell_p.company_id != source_p.company_id:
                print(f"SKIP: {sell_p.name} va {source_p.name} boshqa kompaniyada")
                continue
            print(f"Juft: [{sell_p.id}] {sell_p.name}  ->  [{source_p.id}] {source_p.name}")
            actions = fix_product(db, sell_p, source_p, args.apply)
            if actions:
                any_action = True
                for a in actions:
                    print(a)
            else:
                print("  (o'zgartirish kerak emas)")
            print()

        if not any_action:
            print("Barcha yozuvlar to'g'ri.")
            return 0

        if args.apply:
            db.commit()
            print("Saqlandi.")
        else:
            print("Dry-run. Saqlash uchun: python fix_virtual_products.py --apply")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
