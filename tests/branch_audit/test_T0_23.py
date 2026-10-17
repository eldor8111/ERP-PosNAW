"""T0.23 — BOM/retseptura tenant va qiymat tekshiruvi (STOCK-16)."""
import itertools
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.batch import Batch
from app.models.bom import BOM, BOMItem
from app.models.inventory import StockLevel, StockMovement
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.production_order import ProductionOrder, ProductionOrderStatus
from app.schemas.production import (
    BOMItemIn, CompleteProductionOrderRequest, ProductionOrderCostIn,
)

_n = itertools.count(1)


def _product(db, company, ptype="simple", deleted=False, cost=0, name=None):
    n = next(_n)
    p = Product(company_id=company.id, name=name or f"Mahsulot {n}", sku=f"SKU{n}", barcode=f"B{n:010d}",
                product_type=ptype, is_deleted=deleted, cost_price=cost, sale_price=0)
    db.add(p)
    db.flush()
    return p


def _variant(db, product):
    v = ProductVariant(product_id=product.id, name="XL")
    db.add(v)
    db.flush()
    return v


def _stock(db, product, wh, qty):
    s = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=Decimal(str(qty)))
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def env(db, mk, client):
    """Ikki korxona: A va B (admin, tayyor mahsulot, xom ashyo, 2 ombor)."""
    out = {}
    for key in ("a", "b"):
        c, br, wh, u = mk.tenant()
        c.manufacturing_enabled = True
        wh2 = mk.warehouse(c, br)
        out[key] = dict(company=c, wh=wh, wh2=wh2, user=u,
                        fin=_product(db, c), raw=_product(db, c, cost=1000))
    db.flush()
    return out


def _body(product_id, items, variant_id=None, name="Retsept"):
    return {"product_id": product_id, "variant_id": variant_id, "name": name,
            "items": [{"component_product_id": pid, "quantity_per_unit": q} for pid, q in items]}


def _count_boms(db):
    return db.query(BOM).count(), db.query(BOMItem).count()


# --- Ijobiy yo'l -------------------------------------------------------------

def test_create_bom_own_ok(client, db, env):
    a = env["a"]
    client.login(a["user"])
    r = client.post("/api/production/boms", json=_body(a["fin"].id, [(a["raw"].id, 2)]))
    assert r.status_code == 201, r.text
    assert r.json()["items"][0]["component_product_id"] == a["raw"].id


def test_update_bom_own_ok(client, db, env):
    a = env["a"]
    client.login(a["user"])
    bom_id = client.post("/api/production/boms", json=_body(a["fin"].id, [(a["raw"].id, 2)])).json()["id"]
    raw2 = _product(db, a["company"])
    r = client.put(f"/api/production/boms/{bom_id}", json={
        "items": [{"component_product_id": raw2.id, "quantity_per_unit": 3}]})
    assert r.status_code == 200, r.text
    assert [i["component_product_id"] for i in r.json()["items"]] == [raw2.id]


# --- Tenant izolyatsiyasi ------------------------------------------------------

def test_create_bom_foreign_finished_product_404(client, db, env):
    a, b = env["a"], env["b"]
    client.login(a["user"])
    before = _count_boms(db)
    r = client.post("/api/production/boms", json=_body(b["fin"].id, [(a["raw"].id, 1)]))
    assert r.status_code == 404
    assert _count_boms(db) == before


def test_create_bom_foreign_component_404(client, db, env):
    a, b = env["a"], env["b"]
    client.login(a["user"])
    before = _count_boms(db)
    r = client.post("/api/production/boms", json=_body(a["fin"].id, [(b["raw"].id, 1)]))
    assert r.status_code == 404
    assert _count_boms(db) == before


def test_update_bom_foreign_component_404_items_unchanged(client, db, env):
    a, b = env["a"], env["b"]
    client.login(a["user"])
    bom_id = client.post("/api/production/boms", json=_body(a["fin"].id, [(a["raw"].id, 2)])).json()["id"]
    r = client.put(f"/api/production/boms/{bom_id}", json={
        "items": [{"component_product_id": b["raw"].id, "quantity_per_unit": 1}]})
    assert r.status_code == 404
    items = db.query(BOMItem).filter(BOMItem.bom_id == bom_id).all()
    assert [i.component_product_id for i in items] == [a["raw"].id]


def test_foreign_bom_not_accessible(client, db, env):
    a, b = env["a"], env["b"]
    client.login(b["user"])
    bom_id = client.post("/api/production/boms", json=_body(b["fin"].id, [(b["raw"].id, 2)])).json()["id"]
    client.login(a["user"])
    assert client.get(f"/api/production/boms/{bom_id}").status_code == 404
    assert client.put(f"/api/production/boms/{bom_id}", json={"name": "x"}).status_code == 404


# --- Qiymat va tur tekshiruvlari -----------------------------------------------

@pytest.mark.parametrize("q", [0, -1])
def test_create_bom_non_positive_qty_422(client, db, env, q):
    a = env["a"]
    client.login(a["user"])
    before = _count_boms(db)
    r = client.post("/api/production/boms", json=_body(a["fin"].id, [(a["raw"].id, q)]))
    assert r.status_code == 422
    assert _count_boms(db) == before


@pytest.mark.parametrize("q", [0, -1])
def test_update_bom_non_positive_qty_422(client, db, env, q):
    a = env["a"]
    client.login(a["user"])
    bom_id = client.post("/api/production/boms", json=_body(a["fin"].id, [(a["raw"].id, 2)])).json()["id"]
    r = client.put(f"/api/production/boms/{bom_id}", json={
        "items": [{"component_product_id": a["raw"].id, "quantity_per_unit": q}]})
    assert r.status_code == 422


def test_variant_of_other_product_400(client, db, env):
    a = env["a"]
    other = _product(db, a["company"])
    v = _variant(db, other)
    client.login(a["user"])
    r = client.post("/api/production/boms", json=_body(a["fin"].id, [(a["raw"].id, 1)], variant_id=v.id))
    assert r.status_code == 400


def test_own_variant_ok(client, db, env):
    a = env["a"]
    v = _variant(db, a["fin"])
    client.login(a["user"])
    r = client.post("/api/production/boms", json=_body(a["fin"].id, [(a["raw"].id, 1)], variant_id=v.id))
    assert r.status_code == 201, r.text


def test_component_variant_mismatch_400(client, db, env):
    a = env["a"]
    v = _variant(db, a["fin"])  # xom ashyoniki emas
    client.login(a["user"])
    body = _body(a["fin"].id, [(a["raw"].id, 1)])
    body["items"][0]["component_variant_id"] = v.id
    assert client.post("/api/production/boms", json=body).status_code == 400


@pytest.mark.parametrize("kind", ["deleted", "service", "sell"])
def test_bad_component_rejected(client, db, env, kind):
    a = env["a"]
    comp = _product(db, a["company"], ptype="simple" if kind == "deleted" else kind, deleted=(kind == "deleted"))
    client.login(a["user"])
    r = client.post("/api/production/boms", json=_body(a["fin"].id, [(comp.id, 1)]))
    assert r.status_code == 404


@pytest.mark.parametrize("kind", ["service", "sell"])
def test_bad_finished_product_rejected(client, db, env, kind):
    a = env["a"]
    fin = _product(db, a["company"], ptype=kind)
    client.login(a["user"])
    assert client.post("/api/production/boms", json=_body(fin.id, [(a["raw"].id, 1)])).status_code == 404


def test_self_component_400(client, db, env):
    a = env["a"]
    client.login(a["user"])
    r = client.post("/api/production/boms", json=_body(a["fin"].id, [(a["fin"].id, 1)]))
    assert r.status_code == 400


def test_duplicate_component_400(client, db, env):
    a = env["a"]
    client.login(a["user"])
    r = client.post("/api/production/boms", json=_body(a["fin"].id, [(a["raw"].id, 1), (a["raw"].id, 2)]))
    assert r.status_code == 400
    assert "takrorlangan" in r.json()["detail"]


# --- Sxema testlari --------------------------------------------------------------

def test_schema_validators():
    with pytest.raises(ValidationError):
        BOMItemIn(component_product_id=1, quantity_per_unit=0)
    with pytest.raises(ValidationError):
        BOMItemIn(component_product_id=1, quantity_per_unit=-1)
    with pytest.raises(ValidationError):
        BOMItemIn(component_product_id=1, quantity_per_unit=Decimal("1000001"))
    assert BOMItemIn(component_product_id=1, quantity_per_unit=Decimal("0.333333")).quantity_per_unit > 0
    with pytest.raises(ValidationError):
        ProductionOrderCostIn(cost_type="labor", amount=-1)
    with pytest.raises(ValidationError):
        CompleteProductionOrderRequest(produced_quantity=1, defect_quantity=-1)
    with pytest.raises(ValidationError):
        CompleteProductionOrderRequest(produced_quantity=0)


# --- Buyurtma yaratish va yakunlash ----------------------------------------------

def _make_order(db, company, user, bom, wh, wh2, qty=1, status=ProductionOrderStatus.in_progress):
    o = ProductionOrder(number=f"MO{next(_n):08d}", bom_id=bom.id, product_id=bom.product_id,
                        variant_id=bom.variant_id, planned_quantity=qty, warehouse_id=wh.id,
                        target_warehouse_id=wh2.id, status=status, created_by=user.id,
                        company_id=company.id)
    db.add(o)
    db.flush()
    return o


def _snapshot(db):
    return (
        sorted((s.id, s.quantity) for s in db.query(StockLevel).all()),
        db.query(StockMovement).count(),
        db.query(Batch).count(),
        sorted((p.id, p.cost_price) for p in db.query(Product).all()),
    )


def _dirty_bom(db, company, product, items):
    bom = BOM(product_id=product.id, name="Iflos", company_id=company.id, is_active=True)
    db.add(bom)
    db.flush()
    for comp, q in items:
        db.add(BOMItem(bom_id=bom.id, component_product_id=comp.id, quantity_per_unit=Decimal(str(q))))
    db.flush()
    db.refresh(bom)
    return bom


def test_complete_valid_bom_works(client, db, env):
    a = env["a"]
    _stock(db, a["raw"], a["wh"], 100)
    client.login(a["user"])
    bom_id = client.post("/api/production/boms", json=_body(a["fin"].id, [(a["raw"].id, 2)])).json()["id"]
    r = client.post("/api/production/orders", json={
        "bom_id": bom_id, "planned_quantity": 5, "warehouse_id": a["wh"].id,
        "target_warehouse_id": a["wh2"].id})
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    assert client.post(f"/api/production/orders/{oid}/start").status_code == 200
    r = client.post(f"/api/production/orders/{oid}/complete", json={"produced_quantity": 5})
    assert r.status_code == 200, r.text
    raw = db.query(StockLevel).filter_by(product_id=a["raw"].id, warehouse_id=a["wh"].id).one()
    fin = db.query(StockLevel).filter_by(product_id=a["fin"].id, warehouse_id=a["wh2"].id).one()
    assert raw.quantity == Decimal("90")
    assert fin.quantity == Decimal("5")
    assert db.query(Batch).filter_by(product_id=a["fin"].id).count() == 1
    db.refresh(a["fin"])
    assert a["fin"].cost_price == Decimal("2000")  # 2 * 1000 UZS


def test_complete_negative_qty_dirty_bom_rejected(client, db, env):
    a = env["a"]
    _stock(db, a["raw"], a["wh"], 100)
    bom = _dirty_bom(db, a["company"], a["fin"], [(a["raw"], -1)])
    o = _make_order(db, a["company"], a["user"], bom, a["wh"], a["wh2"])
    snap = _snapshot(db)
    client.login(a["user"])
    r = client.post(f"/api/production/orders/{o.id}/complete", json={"produced_quantity": 3})
    assert r.status_code == 400
    assert _snapshot(db) == snap


def test_complete_foreign_component_dirty_bom_rejected(client, db, env):
    a, b = env["a"], env["b"]
    _stock(db, b["raw"], a["wh"], 100)
    bom = _dirty_bom(db, a["company"], a["fin"], [(b["raw"], 1)])
    o = _make_order(db, a["company"], a["user"], bom, a["wh"], a["wh2"])
    snap = _snapshot(db)
    client.login(a["user"])
    r = client.post(f"/api/production/orders/{o.id}/complete", json={"produced_quantity": 3})
    assert r.status_code == 400
    assert _snapshot(db) == snap


def test_complete_foreign_finished_product_does_not_touch_b(client, db, env):
    a, b = env["a"], env["b"]
    _stock(db, a["raw"], a["wh"], 100)
    bom = _dirty_bom(db, a["company"], b["fin"], [(a["raw"], 1)])  # B mahsuloti, A korxonasi BOM i
    o = _make_order(db, a["company"], a["user"], bom, a["wh"], a["wh2"])
    snap = _snapshot(db)
    client.login(a["user"])
    r = client.post(f"/api/production/orders/{o.id}/complete", json={"produced_quantity": 3})
    assert r.status_code == 404
    assert _snapshot(db) == snap
    db.refresh(b["fin"])
    assert b["fin"].cost_price == 0


def test_complete_bom_of_other_company_404(client, db, env):
    a, b = env["a"], env["b"]
    _stock(db, a["raw"], a["wh"], 100)
    bom = _dirty_bom(db, b["company"], b["fin"], [(b["raw"], 1)])  # BOM B korxonasiniki
    o = _make_order(db, a["company"], a["user"], bom, a["wh"], a["wh2"])
    snap = _snapshot(db)
    client.login(a["user"])
    r = client.post(f"/api/production/orders/{o.id}/complete", json={"produced_quantity": 3})
    assert r.status_code == 404
    assert _snapshot(db) == snap


def test_complete_schema_422(client, db, env):
    a = env["a"]
    client.login(a["user"])
    r = client.post("/api/production/orders/1/complete", json={"produced_quantity": 1, "defect_quantity": -1})
    assert r.status_code == 422
    r = client.post("/api/production/orders/1/complete", json={
        "produced_quantity": 1, "costs": [{"cost_type": "labor", "amount": -5}]})
    assert r.status_code == 422


def test_create_order_foreign_product_bom_400(client, db, env):
    a, b = env["a"], env["b"]
    bom = _dirty_bom(db, a["company"], b["fin"], [(a["raw"], 1)])
    client.login(a["user"])
    r = client.post("/api/production/orders", json={
        "bom_id": bom.id, "planned_quantity": 1, "warehouse_id": a["wh"].id,
        "target_warehouse_id": a["wh2"].id})
    assert r.status_code == 400
    assert db.query(ProductionOrder).count() == 0
