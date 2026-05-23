"""
Tarkibiy mahsulot sotilganda asosiy mahsulot qoldig'i kamayishini tekshiradi.
Ishlatish: python -m pytest tests/test_virtual_product_sale.py -v
"""
import sys

import pytest

sys.stdout.reconfigure(encoding="utf-8")

from decimal import Decimal

from app.database import SessionLocal
from app.models.inventory import StockLevel
from app.models.product import Product, ProductConversion
from app.models.user import User
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services.sale_service import create_sale


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_sell_product_deducts_source_stock(db):
    user = db.query(User).filter(User.phone == "998933344602").first()
    if not user:
        pytest.skip("Test user yo'q")

    dumbba = db.query(Product).filter(Product.name.ilike("%dumba%")).first()
    assert dumbba is not None
    assert dumbba.product_type == "sell"

    conv = (
        db.query(ProductConversion)
        .filter(ProductConversion.sell_product_id == dumbba.id)
        .first()
    )
    assert conv is not None

    source_id = conv.source_product_id
    stocks_before = (
        db.query(StockLevel).filter(StockLevel.product_id == source_id).all()
    )
    total_before = sum((s.quantity for s in stocks_before), Decimal("0"))

    wh_id = stocks_before[0].warehouse_id if stocks_before else None
    if not wh_id:
        pytest.skip("Asosiy mahsulotda qoldiq yo'q")

    data = SaleCreate(
        items=[
            SaleItemCreate(
                product_id=dumba.id,
                quantity=Decimal("0.1"),
                unit_price=Decimal("1000"),
            )
        ],
        warehouse_id=wh_id,
        payment_type="cash",
        paid_amount=Decimal("100"),
    )
    create_sale(db=db, data=data, current_user=user, ip="127.0.0.1")
    db.flush()

    stocks_after = (
        db.query(StockLevel).filter(StockLevel.product_id == source_id).all()
    )
    total_after = sum((s.quantity for s in stocks_after), Decimal("0"))

    assert total_after < total_before
    assert total_before - total_after == Decimal("0.1") * conv.ratio
