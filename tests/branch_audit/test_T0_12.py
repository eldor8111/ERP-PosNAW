"""T0.12 — POST /inventory/adjust: ombor majburiy, mahsulot/variant/ombor korxonaga tekshiriladi."""
from decimal import Decimal

from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import UserRole

URL = "/api/inventory/adjust"


def _product(db, company, name="Tovar", ptype="simple"):
    p = Product(sku=f"SKU{company.id}-{name}", barcode=f"BC{company.id}-{name}", name=name,
                company_id=company.id, cost_price=Decimal("700"), sale_price=Decimal("1000"),
                product_type=ptype)
    db.add(p)
    db.flush()
    return p


def _variant(db, product, name="L"):
    v = ProductVariant(product_id=product.id, name=name)
    db.add(v)
    db.flush()
    return v


def _stock(db, product, wh, qty, variant=None):
    s = StockLevel(product_id=product.id, warehouse_id=wh.id,
                   variant_id=variant.id if variant else None, quantity=Decimal(qty))
    db.add(s)
    db.flush()
    return s


def _body(product, wh, qty=5, **kw):
    d = {"product_id": product.id, "warehouse_id": wh.id, "new_quantity": qty, "reason": "Inventar tuzatish"}
    d.update(kw)
    return d


def test_warehouse_id_required_422(db, mk, client):
    c, b, w, u = mk.tenant(UserRole.manager)
    p = _product(db, c)
    r = client.login(u).post(URL, json={"product_id": p.id, "new_quantity": 5, "reason": "Sabab"})
    assert r.status_code == 422


def test_short_reason_422(db, mk, client):
    c, b, w, u = mk.tenant(UserRole.manager)
    p = _product(db, c)
    r = client.login(u).post(URL, json=_body(p, w, reason="x"))
    assert r.status_code == 422


def test_foreign_product_404_and_stock_untouched(db, mk, client):
    ca, ba, wa, ua = mk.tenant(UserRole.manager)
    cb, bb, wb, ub = mk.tenant()
    pb = _product(db, cb, "B")
    sb = _stock(db, pb, wb, 10)
    r = client.login(ua).post(URL, json=_body(pb, wa, 0))
    assert r.status_code == 404
    r = client.login(ua).post(URL, json=_body(pb, wb, 0))
    assert r.status_code == 404
    db.refresh(sb)
    assert sb.quantity == Decimal("10")


def test_foreign_warehouse_404(db, mk, client):
    ca, ba, wa, ua = mk.tenant(UserRole.manager)
    cb, bb, wb, ub = mk.tenant()
    pa = _product(db, ca, "A")
    sb = _stock(db, pa, wa, 3)
    r = client.login(ua).post(URL, json=_body(pa, wb, 0))
    assert r.status_code == 404
    db.refresh(sb)
    assert sb.quantity == Decimal("3")
    assert db.query(StockLevel).filter(StockLevel.warehouse_id == wb.id).count() == 0


def test_manager_other_branch_warehouse_403(db, mk, client):
    c, b, w, u = mk.tenant(UserRole.manager)
    b2 = mk.branch(c)
    w2 = mk.warehouse(c, b2)
    p = _product(db, c)
    r = client.login(u).post(URL, json=_body(p, w2, 1))
    assert r.status_code == 403


def test_only_selected_warehouse_changes(db, mk, client):
    c, b, w, u = mk.tenant(UserRole.manager)
    w2 = mk.warehouse(c, b)
    p = _product(db, c)
    s1 = _stock(db, p, w, 10)
    s2 = _stock(db, p, w2, 20)
    r = client.login(u).post(URL, json=_body(p, w2, 7))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["warehouse_id"] == w2.id
    assert data["qty_before"] == "20.000" or Decimal(data["qty_before"]) == Decimal("20")
    assert Decimal(data["qty_after"]) == Decimal("7")
    db.refresh(s1)
    db.refresh(s2)
    assert s1.quantity == Decimal("10")
    assert s2.quantity == Decimal("7")


def test_variant_row_only(db, mk, client):
    c, b, w, u = mk.tenant(UserRole.manager)
    p = _product(db, c)
    v = _variant(db, p)
    base = _stock(db, p, w, 4)
    sv = _stock(db, p, w, 6, variant=v)
    r = client.login(u).post(URL, json=_body(p, w, 9, variant_id=v.id))
    assert r.status_code == 200, r.text
    db.refresh(base)
    db.refresh(sv)
    assert base.quantity == Decimal("4")
    assert sv.quantity == Decimal("9")


def test_foreign_variant_404(db, mk, client):
    ca, ba, wa, ua = mk.tenant(UserRole.manager)
    cb, bb, wb, ub = mk.tenant()
    pa = _product(db, ca, "A")
    pb = _product(db, cb, "B")
    vb = _variant(db, pb)
    r = client.login(ua).post(URL, json=_body(pa, wa, 1, variant_id=vb.id))
    assert r.status_code == 404


def test_movement_has_warehouse_and_type(db, mk, client):
    c, b, w, u = mk.tenant(UserRole.manager)
    p = _product(db, c)
    _stock(db, p, w, 10)
    r = client.login(u).post(URL, json=_body(p, w, 4))
    assert r.status_code == 200, r.text
    m = db.query(StockMovement).filter(StockMovement.product_id == p.id).one()
    assert m.warehouse_id == w.id
    assert m.type == MovementType.ADJUST
    assert m.qty_before == Decimal("10")
    assert m.qty_after == Decimal("4")
    assert m.quantity == Decimal("6")
    assert m.reference_type == "adjustment"


def test_creates_row_in_selected_warehouse_not_null(db, mk, client):
    c, b, w, u = mk.tenant(UserRole.manager)
    p = _product(db, c)
    r = client.login(u).post(URL, json=_body(p, w, 5))
    assert r.status_code == 200, r.text
    rows = db.query(StockLevel).filter(StockLevel.product_id == p.id).all()
    assert len(rows) == 1
    assert rows[0].warehouse_id == w.id
    assert rows[0].quantity == Decimal("5")
    assert db.query(StockLevel).filter(StockLevel.product_id == p.id,
                                       StockLevel.warehouse_id.is_(None)).count() == 0


def test_virtual_product_400(db, mk, client):
    c, b, w, u = mk.tenant(UserRole.manager)
    p = _product(db, c, "Virt", ptype="sell")
    r = client.login(u).post(URL, json=_body(p, w, 5))
    assert r.status_code == 400


def test_missing_product_404(db, mk, client):
    c, b, w, u = mk.tenant(UserRole.manager)
    r = client.login(u).post(URL, json={"product_id": 999999, "warehouse_id": w.id,
                                        "new_quantity": 1, "reason": "Sabab"})
    assert r.status_code == 404


def test_admin_can_adjust_any_company_warehouse(db, mk, client):
    c, b, w, u = mk.tenant(UserRole.admin)
    b2 = mk.branch(c)
    w2 = mk.warehouse(c, b2)
    p = _product(db, c)
    r = client.login(u).post(URL, json=_body(p, w2, 2))
    assert r.status_code == 200, r.text


def test_service_requires_warehouse():
    """adjust_stock servisi warehouse_id siz chaqirilsa 400."""
    import pytest
    from fastapi import HTTPException
    from app.services.inventory_service import adjust_stock
    with pytest.raises(HTTPException) as e:
        adjust_stock(None, 1, Decimal("1"), 1, "Sabab", warehouse_id=None, company_id=1)
    assert e.value.status_code == 400
