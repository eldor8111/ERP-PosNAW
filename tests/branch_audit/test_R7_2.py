"""R7.2 — Yarim tayyor mahsulot ishlab chiqarish: tex karta bo'yicha xom ashyo oshxona omboridan yechiladi,
yarim tayyor shu omborga kiradi (bitta production_orders yozuvi), yetishmovchilik 409 (force bilan minusga),
ichma-ich yarim tayyor yoyiladi, bekor qilish qoldiqni qaytaradi, ruxsat va filial.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R7_2.py -q -p no:cacheprovider
"""
import os
from decimal import Decimal as D

import pytest

from app.models.inventory import StockMovement
from app.models.product import Product
from app.models.production_order import ProductionOrder
from app.models.user import UserRole
from app.services import restaurant_orders as svc
from app.services.restaurant_menu import create_item, save_card
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
P = "/api/restaurant/production"


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


@pytest.fixture
def rp(db, mk):
    r = RP(db, mk)
    cid = r.c.id
    r.cook = mk.user(r.c, role=UserRole.cashier, branch=r.b, permissions={"restaurant": {"kitchen": True}})
    r.meat = create_item(db, cid, {"name": "Go'sht", "kind": "ingredient", "cost_price": 80000})
    r.onion = create_item(db, cid, {"name": "Piyoz", "kind": "ingredient", "cost_price": 5000})
    r.mince = create_item(db, cid, {"name": "Qiyma", "kind": "semi"})
    # 5 kg qiyma: 4 kg go'sht + 1.2 kg piyoz -> 326 000, 1 kg = 65 200
    save_card(db, cid, r.mince, {"output_qty": 5, "items": [
        {"component_product_id": r.meat.id, "gross_qty": 4},
        {"component_product_id": r.onion.id, "gross_qty": 1.2}]}, None)
    r.stock(r.meat, r.kitchen, 10)
    r.stock(r.onion, r.kitchen, 5)
    r.stock(r.meat, r.main_wh, 100)
    db.flush()
    return r


def _produce(cl, rp, pid, qty, **kw):
    return cl.post(P, json={"branch_id": rp.b.id, "product_id": pid, "quantity": qty, **kw})


def test_produce_moves_stock_in_kitchen_and_records_order(rp, client, db):
    kc = client.login(rp.cook)
    semis = kc.get(f"{P}/semis", params={"branch_id": rp.b.id}).json()
    row = next(s for s in semis["items"] if s["id"] == rp.mince.id)
    assert row["has_card"] and row["output_qty"] == 5 and row["stock"] == 0 and row["unit_cost"] == 65200
    assert semis["can_produce"] is True and semis["can_cancel"] is False

    plan = kc.get(f"{P}/plan", params={"branch_id": rp.b.id, "product_id": rp.mince.id, "quantity": 10}).json()
    lines = {ln["name"]: ln for ln in plan["lines"]}
    assert lines["Go'sht"]["quantity"] == 8 and lines["Go'sht"]["available"] == 10 and lines["Go'sht"]["shortage"] == 0
    assert lines["Piyoz"]["quantity"] == 2.4 and plan["short"] == []
    assert plan["total_cost"] == 652000 and plan["unit_cost"] == 65200
    assert rp.qty(rp.meat, rp.kitchen) == D("10")                      # reja hech narsa yozmaydi

    res = _produce(kc, rp, rp.mince.id, 10, note="Ertalabki")
    assert res.status_code == 201, res.text
    out = res.json()
    assert out["status"] == "completed" and out["quantity"] == 10 and out["total_cost"] == 652000
    assert out["user_name"] == rp.cook.name and out["note"] == "Ertalabki"
    assert {ln["name"]: ln["quantity"] for ln in out["lines"]} == {"Go'sht": 8, "Piyoz": 2.4}
    assert rp.qty(rp.meat, rp.kitchen) == D("2") and rp.qty(rp.onion, rp.kitchen) == D("2.6")
    assert rp.qty(rp.mince, rp.kitchen) == D("10")
    assert rp.qty(rp.meat, rp.main_wh) == D("100")                     # asosiy ombor tegilmadi
    o = db.get(ProductionOrder, out["id"])
    assert o.warehouse_id == o.target_warehouse_id == rp.kitchen.id and o.bom_id is not None
    assert db.get(Product, rp.mince.id).cost_price == D("65200.0000")
    refs = db.query(StockMovement).filter(StockMovement.reference_type == "production_order",
                                          StockMovement.reference_id == o.id).count()
    assert refs == 3
    hist = kc.get(P, params={"branch_id": rp.b.id}).json()["items"]
    assert [h["id"] for h in hist] == [o.id] and hist[0]["name"] == "Qiyma"


def test_shortage_409_then_force_goes_negative(rp, client, db):
    kc = client.login(rp.cook)
    res = _produce(kc, rp, rp.mince.id, 15)                            # 12 kg go'sht kerak, 10 bor
    assert res.status_code == 409, res.text
    det = res.json()["detail"]
    assert det["code"] == "INSUFFICIENT_STOCK" and [ln["name"] for ln in det["lines"]] == ["Go'sht"]
    assert det["lines"][0]["shortage"] == 2
    assert db.query(ProductionOrder).count() == 0 and rp.qty(rp.meat, rp.kitchen) == D("10")
    res = _produce(kc, rp, rp.mince.id, 15, force=True)
    assert res.status_code == 201, res.text
    assert rp.qty(rp.meat, rp.kitchen) == D("-2") and rp.qty(rp.mince, rp.kitchen) == D("15")


def test_nested_semi_uses_stock_then_expands(rp, client, db):
    cid = rp.c.id
    cutlet = create_item(db, cid, {"name": "Kotlet massasi", "kind": "semi"})
    bread = create_item(db, cid, {"name": "Non", "kind": "ingredient", "cost_price": 4000})
    save_card(db, cid, cutlet, {"output_qty": 1, "items": [
        {"component_product_id": rp.mince.id, "gross_qty": 0.8},
        {"component_product_id": bread.id, "gross_qty": 0.2}]}, None)
    rp.stock(bread, rp.kitchen, 3)
    rp.stock(rp.mince, rp.kitchen, 1)                                  # 1 kg tayyor qiyma, 1.6 kg kerak
    kc = client.login(rp.cook)
    res = _produce(kc, rp, cutlet.id, 2)
    assert res.status_code == 201, res.text
    lines = {ln["name"]: ln["quantity"] for ln in res.json()["lines"]}
    # 1 kg qiyma o'zidan, qolgan 0.6 kg qiyma kartasi bo'yicha: 0.48 go'sht, 0.144 piyoz
    assert lines == {"Qiyma": 1, "Go'sht": 0.48, "Piyoz": 0.144, "Non": 0.4}
    assert rp.qty(rp.mince, rp.kitchen) == D("0") and rp.qty(cutlet, rp.kitchen) == D("2")
    assert rp.qty(rp.meat, rp.kitchen) == D("9.52")


def test_cancel_restores_stock_only_for_managers(rp, client, db):
    kc = client.login(rp.cook)
    oid = _produce(kc, rp, rp.mince.id, 5).json()["id"]
    assert kc.post(f"{P}/{oid}/cancel", params={"branch_id": rp.b.id}).status_code == 403
    mc = client.login(rp.mgr)
    res = mc.post(f"{P}/{oid}/cancel", params={"branch_id": rp.b.id})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"
    assert rp.qty(rp.meat, rp.kitchen) == D("10") and rp.qty(rp.onion, rp.kitchen) == D("5")
    assert rp.qty(rp.mince, rp.kitchen) == D("0")
    assert mc.post(f"{P}/{oid}/cancel", params={"branch_id": rp.b.id}).status_code == 400
    assert mc.get(f"{P}/{oid}", params={"branch_id": rp.b.id}).json()["status"] == "cancelled"


def test_permissions_and_validation(rp, client, db, mk):
    cc = client.login(rp.cashier)                                      # oshxona ruxsati yo'q
    assert cc.get(f"{P}/semis", params={"branch_id": rp.b.id}).status_code == 403
    assert _produce(cc, rp, rp.mince.id, 1).status_code == 403
    wc = client.login(mk.user(rp.c, role=UserRole.warehouse, branch=rp.b))
    assert _produce(wc, rp, rp.mince.id, 1).status_code == 201         # omborchi tayyorlay oladi
    kc = client.login(rp.cook)
    assert _produce(kc, rp, rp.osh.id, 1).status_code == 400           # taom emas, yarim tayyor
    sauce = create_item(db, rp.c.id, {"name": "Sous", "kind": "semi"})
    res = _produce(kc, rp, sauce.id, 1)
    assert res.status_code == 409 and res.json()["detail"]["code"] == "NO_CARD"
    assert _produce(kc, rp, rp.mince.id, 0).status_code == 400
    assert _produce(kc, rp, rp.mince.id, -1).status_code == 400
    # boshqa filial: xodim doirasidan tashqari
    b2 = mk.branch(rp.c)
    db.flush()
    assert _produce(kc, rp, rp.mince.id, 1).status_code == 201
    res = kc.post(P, json={"branch_id": b2.id, "product_id": rp.mince.id, "quantity": 1})
    assert res.status_code == 403
    # boshqa korxona mahsuloti
    other = RP(db, mk)
    foreign = create_item(db, other.c.id, {"name": "Begona qiyma", "kind": "semi"})
    assert _produce(kc, rp, foreign.id, 1).status_code == 404


def test_retail_company_blocked(db, mk, client):
    c = mk.company()
    b = mk.branch(c, is_main=True)
    u = mk.user(c, branch=b)
    assert client.login(u).get(f"{P}/semis", params={"branch_id": b.id}).status_code == 403


def test_frontend_wired_and_i18n():
    import re
    app_jsx = _read('frontend/src/App.jsx')
    assert "RestaurantProduction" in app_jsx and 'path="restaurant/production"' in app_jsx
    layout = _read('frontend/src/components/AdminLayout.jsx')
    assert "path: '/admin/restaurant/production'" in layout
    page = _read('frontend/src/pages/admin/restaurant/RestaurantProduction.jsx')
    for token in ("/restaurant/production/semis", "/restaurant/production/plan", "INSUFFICIENT_STOCK", "force",
                  "/cancel"):
        assert token in page, token
    keys = set(re.findall(r"'(restProd\.[\w.]+)'", page)) | {'nav.restaurantProduction'}
    assert len(keys) > 15
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
