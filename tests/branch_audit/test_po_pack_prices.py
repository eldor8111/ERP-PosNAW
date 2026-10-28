"""Dorixona kirimi (PO): dona sotuv narxi o'zgarsa saqlangan quti/blister narxlari ham nisbat bo'yicha yangilanadi.

Avval qabulda faqat `product.sale_price` (dona) yozilardi; `ProductUnit.sale_price` (quti, blister) eski qolib,
kassada quti eski narxda sotilardi. Endi: yangi narx = dona narxi * nisbat; narxi saqlanmagan birlik (NULL)
o'zgarmaydi (sotuvda o'zi hisoblanadi). Oddiy korxona o'zgarmagan.
"""
import os
from decimal import Decimal as D

from app.models.audit_log import AuditLog
from app.models.product_units import ProductUnit
from tests.branch_audit.test_D2_4 import _PO, _Recv, _dt, _product, _supplier, _unit, ph   # noqa: F401
from app.services.purchase_order_service import create_purchase_order, receive_purchase_order

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _med(db, c, price=1000, box=30000, blister=10000):
    """1 quti = 3 blister = 30 dona; quti va blister narxi saqlangan, dona birligi narxsiz (NULL)."""
    p = _product(db, c, price=price)
    return p, _unit(db, p, "quti", 30, price=box), _unit(db, p, "blister", 10, price=blister), _unit(db, p, "dona", 1)


def _receive(db, c, user, wh, p, cost, new_sale_price=None):
    sup = _supplier(db, c)
    item = {"product_id": p.id, "qty_ordered": 30, "unit_cost": cost}
    if new_sale_price is not None:
        item["new_sale_price"] = new_sale_price
    po = create_purchase_order(db, _PO(supplier_id=sup.id, warehouse_id=wh.id, status="sent", items=[item]), user)
    receive_purchase_order(db, po.id, _Recv(items=[{"po_item_id": po.items[0].id, "qty_received": 30,
                                                    "lot_number": "L1", "expiry_date": _dt(400).isoformat()}]), user)
    return po


def _price(db, obj):
    db.refresh(obj)
    return None if obj.sale_price is None else D(str(obj.sale_price))


def test_new_sale_price_updates_box_and_blister_by_ratio(db, ph):
    p, box, blister, piece = _med(db, ph["c"])
    _receive(db, ph["c"], ph["admin"], ph["wh"], p, cost=800, new_sale_price=1200)
    assert _price(db, p) == 1200
    assert _price(db, box) == 36000 and _price(db, blister) == 12000
    assert _price(db, piece) is None                                    # narxsiz birlik o'zi hisoblanadi
    log = db.query(AuditLog).filter(AuditLog.action == "PRICE_CHANGE", AuditLog.entity_id == p.id).one()
    assert log.old_values["units"]["quti"].startswith("30000") and log.new_values["units"]["quti"].startswith("36000")
    assert log.new_values["units"]["blister"].startswith("12000")


def test_auto_markup_price_updates_pack_prices(db, ph):
    ph["c"].pharmacy_settings = {"price_round": 100, "markup_pct": 25}
    db.flush()
    p, box, blister, _ = _med(db, ph["c"], price=900, box=27000, blister=9000)
    _receive(db, ph["c"], ph["admin"], ph["wh"], p, cost=800)                    # 800 * 1.25 = 1000 (dona)
    assert _price(db, p) == 1000
    assert _price(db, box) == 30000 and _price(db, blister) == 10000


def test_unchanged_sale_price_keeps_manual_box_price(db, ph):
    """Dona narxi o'zgarmasa (faqat tannarx) qo'lda qo'yilgan quti narxi (29 000, 30 * 1000 emas) saqlanadi."""
    p, box, blister, _ = _med(db, ph["c"], price=1000, box=29000, blister=9800)
    _receive(db, ph["c"], ph["admin"], ph["wh"], p, cost=700)
    _receive(db, ph["c"], ph["admin"], ph["wh"], p, cost=750, new_sale_price=1000)   # narx avvalgidek — o'zgarish yo'q
    assert _price(db, p) == 1000
    assert _price(db, box) == 29000 and _price(db, blister) == 9800


def test_plain_company_unit_prices_untouched(db, ph):
    p = _product(db, ph["c2"], price=1000)
    box = ProductUnit(product_id=p.id, company_id=p.company_id, name="quti", ratio=D(30), sale_price=D(30000))
    db.add(box)
    db.flush()
    _receive(db, ph["c2"], ph["admin2"], ph["wh2"], p, cost=800, new_sale_price=1200)
    assert _price(db, p) == 1200 and _price(db, box) == 30000


def test_purchase_form_shows_new_pack_prices():
    with open(os.path.join(ROOT, 'frontend/src/pages/admin/Purchases.jsx'), encoding='utf-8') as f:
        src = f.read()
    assert "t('purchase.phPackPrices')" in src
    for lang in ('uz', 'ru', 'en'):
        with open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8') as f:
            assert "'purchase.phPackPrices'" in f.read()
