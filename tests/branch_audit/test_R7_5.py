"""R7.5 — Kirimda ingredient narxi o'zgarsa tex kartalar tannarxi qayta hisoblanadi: o'zgarish jurnali (eski / yangi
tannarx, food cost %, chegaradan oshgan taomlar), ichma-ich yarim tayyor orqali ham; qo'lda kirim, xarid buyurtmasi
qabuli, menyuda tannarx tahriri; do'konda yozilmaydi; food cost ko'rinishi va tavsiya narx; ruxsat.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R7_5.py -q -p no:cacheprovider
"""
import itertools
import os
import re
from decimal import Decimal as D

import pytest

from app.models.restaurant import RestaurantCostChange
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services import restaurant_costs
from app.services.restaurant_menu import create_item, save_card
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FC = "/api/restaurant/food-cost"
_n = itertools.count(1)


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture
def rp(db, mk):
    r = RP(db, mk)
    cid = r.c.id
    # Osh: 0.15 kg guruch (20 000/kg) + 0.1 kg go'sht (100 000/kg) = 13 000; narx 50 000 -> 26%
    r.meat = create_item(db, cid, {"name": "Go'sht", "kind": "ingredient", "cost_price": 100000})
    save_card(db, cid, r.osh, {"items": [{"component_product_id": r.rice.id, "gross_qty": 0.15},
                                         {"component_product_id": r.meat.id, "gross_qty": 0.1}]}, None)
    # Qiyma (yarim tayyor): 1 kg = 1.1 kg go'sht; Manti: 0.2 kg qiyma, narx 40 000 -> 22 000 / 40 000 = 55%
    r.mince = create_item(db, cid, {"name": "Qiyma", "kind": "semi"})
    save_card(db, cid, r.mince, {"items": [{"component_product_id": r.meat.id, "gross_qty": 1.1}]}, None)
    r.manti = create_item(db, cid, {"name": "Manti", "kind": "dish", "sale_price": 40000})
    save_card(db, cid, r.manti, {"items": [{"component_product_id": r.mince.id, "gross_qty": 0.2}]}, None)
    r.sup = Supplier(name=f"Bozor {next(_n)}", company_id=cid, is_active=True, debt_balance=D(0), debt_balances={})
    db.add(r.sup)
    db.flush()
    return r


def _receive(cl, rp, pid, qty, price):
    return cl.post("/api/inventory/receive", json={"warehouse_id": rp.kitchen.id,
                                                   "items": [{"product_id": pid, "quantity": qty, "cost_price": price}]})


def test_manual_receive_records_change_with_nested_semis(rp, client, db):
    cl = client.login(rp.admin)
    res = _receive(cl, rp, rp.meat.id, 5, 120000)
    assert res.status_code == 200, res.text
    fc = res.json()["food_cost"]
    assert fc["dishes"] == 3 and fc["over_count"] == 1                      # Osh, Qiyma, Manti; Manti oshgan
    ev = db.query(RestaurantCostChange).one()
    assert ev.source == "receive" and ev.user_id == rp.admin.id and ev.threshold == D("35")
    assert ev.ingredients == [{"product_id": rp.meat.id, "name": "Go'sht", "unit": rp.meat.unit,
                               "old": 100000.0, "new": 120000.0}]
    d = {x["name"]: x for x in ev.dishes}
    assert d["Osh"]["old_cost"] == 13000 and d["Osh"]["new_cost"] == 15000
    assert d["Osh"]["old_pct"] == 26.0 and d["Osh"]["new_pct"] == 30.0 and d["Osh"]["over"] is False
    assert d["Qiyma"]["kind"] == "semi" and d["Qiyma"]["new_cost"] == 132000 and d["Qiyma"]["new_pct"] is None
    assert d["Manti"]["old_cost"] == 22000 and d["Manti"]["new_cost"] == 26400 and d["Manti"]["new_pct"] == 66.0
    assert d["Manti"]["over"] is True
    assert [x["name"] for x in ev.dishes] == ["Manti", "Osh", "Qiyma"]       # taomlar food cost bo'yicha, keyin yarim tayyor
    # jurnal API
    items = cl.get(f"{FC}/changes").json()["items"]
    assert len(items) == 1 and items[0]["user_name"] == rp.admin.name and items[0]["over_count"] == 1


def test_same_price_or_unused_ingredient_not_recorded(rp, client, db):
    cl = client.login(rp.admin)
    assert _receive(cl, rp, rp.meat.id, 1, 100000).status_code == 200        # narx o'zgarmadi
    oil = create_item(db, rp.c.id, {"name": "Yog'", "kind": "ingredient", "cost_price": 20000})
    res = _receive(cl, rp, oil.id, 1, 25000)                                 # hech qaysi kartada yo'q
    assert res.status_code == 200 and "food_cost" not in res.json()
    assert db.query(RestaurantCostChange).count() == 0


def test_purchase_order_receive_records_change(rp, client, db):
    cl = client.login(rp.admin)
    po = cl.post("/api/purchase-orders", json={
        "supplier_id": rp.sup.id, "warehouse_id": rp.kitchen.id, "status": "sent",
        "items": [{"product_id": rp.rice.id, "qty_ordered": 10, "unit_cost": 30000}]})
    assert po.status_code in (200, 201), po.text
    po = po.json()
    assert db.query(RestaurantCostChange).count() == 0                       # hali qabul qilinmagan
    r = cl.post(f"/api/purchase-orders/{po['id']}/receive",
                json={"items": [{"po_item_id": po["items"][0]["id"], "qty_received": 10}]})
    assert r.status_code == 200, r.text
    ev = db.query(RestaurantCostChange).one()
    assert ev.source == "purchase" and ev.reference_id == po["id"]
    osh = next(x for x in ev.dishes if x["name"] == "Osh")
    assert osh["old_cost"] == 13000 and osh["new_cost"] == 14500
    # darhol qabul qilingan xarid ham
    r = cl.post("/api/purchase-orders", json={
        "supplier_id": rp.sup.id, "warehouse_id": rp.kitchen.id, "status": "received",
        "items": [{"product_id": rp.rice.id, "qty_ordered": 5, "unit_cost": 32000}]})
    assert r.status_code in (200, 201), r.text
    assert db.query(RestaurantCostChange).count() == 2


def test_menu_cost_edit_records_manual_change(rp, client, db):
    cl = client.login(rp.admin)
    r = cl.put(f"/api/restaurant/menu/items/{rp.rice.id}", json={"cost_price": 10000})
    assert r.status_code == 200, r.text
    ev = db.query(RestaurantCostChange).one()
    assert ev.source == "manual" and {x["name"] for x in ev.dishes} == {"Osh"}
    assert cl.put(f"/api/restaurant/menu/items/{rp.rice.id}", json={"name": "Guruch (lazer)"}).status_code == 200
    assert db.query(RestaurantCostChange).count() == 1                       # tannarx tegilmadi


def test_overview_over_threshold_and_suggested_price(rp, client, db):
    cl = client.login(rp.mgr)
    out = cl.get(FC).json()
    assert out["threshold"] == 35 and out["over_count"] == 1
    names = [d["name"] for d in out["dishes"]]
    assert names[0] == "Manti" and "Qiyma" not in names                      # faqat taomlar, oshganlari birinchi
    manti = out["dishes"][0]
    assert manti["cost"] == 22000 and manti["pct"] == 55.0 and manti["over"] is True
    assert manti["suggested_price"] == 62900                                 # 22 000 / 0.35 = 62 857 -> 62 900
    osh = next(d for d in out["dishes"] if d["name"] == "Osh")
    assert osh["over"] is False and osh["suggested_price"] is None
    # chegara sozlamasi
    assert client.login(rp.admin).put("/api/restaurant/settings", json={"food_cost_alert_pct": 20}).status_code == 200
    cl = client.login(rp.mgr)
    out = cl.get(FC).json()
    assert out["threshold"] == 20 and out["over_count"] == 2


def test_retail_company_not_recorded_and_permissions(rp, client, db, mk):
    # do'kon: kirimda jurnal yozilmaydi
    c = mk.company()
    b = mk.branch(c, is_main=True)
    wh = mk.warehouse(c, b)
    u = mk.user(c, branch=b)
    from app.models.product import Product
    p = Product(name="Shakar", company_id=c.id, sku=f"S{c.id}", barcode=f"47800{c.id}", cost_price=D(1000), sale_price=D(1500),
                unit="kg")
    db.add(p)
    db.flush()
    assert restaurant_costs.snapshot(db, c.id, [p.id]) is None
    r = client.login(u).post("/api/inventory/receive", json={"warehouse_id": wh.id,
                                                             "items": [{"product_id": p.id, "quantity": 1, "cost_price": 1200}]})
    assert r.status_code == 200, r.text
    assert db.query(RestaurantCostChange).count() == 0
    assert client.login(u).get(FC).status_code == 403                        # restoran emas
    # kassir food cost ko'rmaydi, omborchi ko'radi
    assert client.login(rp.cashier).get(FC).status_code == 403
    wc = client.login(mk.user(rp.c, role=UserRole.warehouse, branch=rp.b))
    assert wc.get(FC).status_code == 200 and wc.get(f"{FC}/changes").status_code == 200


def test_frontend_wired_and_i18n():
    app_jsx = _read('frontend/src/App.jsx')
    assert "RestaurantFoodCost" in app_jsx and 'path="restaurant/food-cost"' in app_jsx
    layout = _read('frontend/src/components/AdminLayout.jsx')
    assert "path: '/admin/restaurant/food-cost'" in layout
    page = _read('frontend/src/pages/admin/restaurant/RestaurantFoodCost.jsx')
    for token in ("/restaurant/food-cost", "/restaurant/food-cost/changes", "suggested_price", "new_pct", "old_cost"):
        assert token in page, token
    keys = set(re.findall(r"'(restFc\.[\w.]+)'", page)) | {'nav.restaurantFoodCost'}
    assert len(keys) > 12
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
