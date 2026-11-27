"""R5.2 — Hisobni bo'lish: qatorlar (qisman miqdor bilan) va teng bo'lish, har bir qism alohida chek, alohida
to'lov va sotuv, yechilgan ingredientlar ikki marta yechilmaydi, chegirma taqsimoti, tekshiruvlar.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R5_2.py -q -p no:cacheprovider
"""
import os
import re
from decimal import Decimal as D

import pytest

from app.models.product import Product
from app.models.restaurant_order import RestaurantOrder
from app.models.sale import Sale, SaleItem
from app.models.user import UserRole
from app.services import restaurant_orders as svc
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


@pytest.fixture
def rp(db, mk):
    return RP(db, mk)


def _items(order):
    return {i["name"]: i for i in order["items"] if i["status"] != "cancelled"}


def _pay(cl, o):
    r = cl.post(f"{O}/{o['id']}/pay", json={"payments": [{"type": "cash", "amount": o["total"]}]})
    assert r.status_code == 200, r.text
    return r.json()


def test_split_by_lines_and_pay_each(rp, client, db):
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2}, {"product_id": rp.salad.id},
                         {"product_id": rp.cola.id})
    o = cl.get(f"{O}/{oid}").json()
    it = _items(o)
    r = cl.post(f"{O}/{oid}/split", params={"version": o["version"]},
                json={"parts": [[{"item_id": it["Osh"]["id"], "quantity": 1}, {"item_id": it["Cola"]["id"]}]]})
    assert r.status_code == 200, r.text
    orig, child = r.json()["order"], r.json()["created"][0]
    assert orig["subtotal"] == 70000 and orig["total"] == 77000                  # osh 1 + salat
    assert child["subtotal"] == 60000 and child["total"] == 66000                # osh 1 + cola
    assert child["split_from_id"] == oid and child["table_id"] == orig["table_id"] and child["status"] == "open"
    assert child["daily_no"] != orig["daily_no"] and child["comment"].startswith(f"#{orig['daily_no']}")
    assert {n: i["quantity"] for n, i in _items(child).items()} == {"Osh": 1, "Cola": 1}
    assert _items(child)["Osh"]["status"] == "sent"                               # oshxona holati saqlanadi
    st = cl.get("/api/restaurant/tables/status", params={"branch_id": rp.b.id}).json()
    assert len(st[0]["orders"]) == 2
    # har bir qism alohida to'lanadi: alohida sotuv
    p1 = _pay(cl, child)
    assert cl.get("/api/restaurant/tables/status", params={"branch_id": rp.b.id}).json()[0]["orders"][0]["id"] == oid
    p2 = _pay(cl, cl.get(f"{O}/{oid}").json())
    assert p1["sale_id"] != p2["sale_id"]
    assert float(db.get(Sale, p1["sale_id"]).total_amount) == 66000 and float(db.get(Sale, p2["sale_id"]).total_amount) == 77000
    assert rp.qty(rp.rice, rp.kitchen) == D("9.700") and rp.qty(rp.cola, rp.main_wh) == D("49")
    assert cl.get("/api/restaurant/tables/status", params={"branch_id": rp.b.id}).json() == []
    cart = cl.get(f"{O}/{child['id']}/fiscal").json()["cart"]
    assert {c["name"]: c["quantity"] for c in cart} == {"Osh": 1, "Cola": 1, "Xizmat haqi": 1}


def test_split_equal(rp, client, db):
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id}, {"product_id": rp.cola.id, "quantity": 2})
    o = cl.get(f"{O}/{oid}").json()
    r = cl.post(f"{O}/{oid}/split", params={"version": o["version"]}, json={"equal": 3})
    assert r.status_code == 200, r.text
    orig, created = r.json()["order"], r.json()["created"]
    assert len(created) == 2
    for c in created:
        assert {n: i["quantity"] for n, i in _items(c).items()} == {"Osh": 0.333, "Cola": 0.666}
        assert c["subtotal"] == 23310
    assert {n: i["quantity"] for n, i in _items(orig).items()} == {"Osh": 0.334, "Cola": 0.668}
    assert orig["subtotal"] == 23380
    assert sum(x["subtotal"] for x in [orig, *created]) == 70000
    sales = [_pay(cl, c)["sale_id"] for c in created] + [_pay(cl, cl.get(f"{O}/{oid}").json())["sale_id"]]
    assert abs(sum(float(db.get(Sale, s).total_amount) for s in sales) - 77000) < 0.05
    assert rp.qty(rp.rice, rp.kitchen) == D("9.850")                              # 3 x 0.05 = 0.15 kg
    assert rp.qty(rp.cola, rp.main_wh) == D("48")


def test_sent_mode_stock_not_deducted_twice(rp, client, db):
    s = dict(rp.c.restaurant_settings)
    s["deduct_stock_on"] = "sent"
    rp.c.restaurant_settings = s
    db.flush()
    cl = client.login(rp.admin)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2})
    assert rp.qty(rp.rice, rp.kitchen) == D("9.700")
    o = cl.get(f"{O}/{oid}").json()
    item = o["items"][0]
    r = cl.post(f"{O}/{oid}/split", json={"parts": [[{"item_id": item["id"], "quantity": 1}]]})
    assert r.status_code == 200, r.text
    child = r.json()["created"][0]
    lines = {o2.id: o2.items[0].stock_lines for o2 in db.query(RestaurantOrder).filter(RestaurantOrder.id.in_([oid, child["id"]]))}
    assert [D(x["quantity"]) for x in lines[oid]] == [D("0.150")] and [D(x["quantity"]) for x in lines[child["id"]]] == [D("0.150")]
    s1 = _pay(cl, child)["sale_id"]
    s2 = _pay(cl, cl.get(f"{O}/{oid}").json())["sale_id"]
    assert rp.qty(rp.rice, rp.kitchen) == D("9.700")                              # qayta yechilmadi
    for sid in (s1, s2):
        osh = next(si for si in db.query(SaleItem).filter(SaleItem.sale_id == sid) if db.get(Product, si.product_id).name == "Osh")
        assert osh.cost_price == D("3000.0000")


def test_discount_carried_to_parts(rp, client):
    cl = client.login(rp.admin)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id}, {"product_id": rp.salad.id})
    assert cl.post(f"{O}/{oid}/discount", json={"pct": 10, "reason": "VIP"}).status_code == 200
    it = _items(cl.get(f"{O}/{oid}").json())
    r = cl.post(f"{O}/{oid}/split", json={"parts": [[{"item_id": it["Achchiq-chuchuk"]["id"]}]]}).json()
    assert r["created"][0]["discount_pct"] == 10 and r["created"][0]["discount_amount"] == 2000
    assert r["order"]["discount_amount"] == 5000
    # summali chegirma: 7000 so'm, qismlar subtotaliga mutanosib
    oid2 = rp.ready_check(cl, {"product_id": rp.osh.id}, {"product_id": rp.salad.id}, table=1)
    assert cl.post(f"{O}/{oid2}/discount", json={"amount": 7000, "reason": "x"}).status_code == 200
    it = _items(cl.get(f"{O}/{oid2}").json())
    r = cl.post(f"{O}/{oid2}/split", json={"parts": [[{"item_id": it["Achchiq-chuchuk"]["id"]}]]}).json()
    assert r["created"][0]["discount_amount"] == 2000 and r["order"]["discount_amount"] == 5000


def test_split_validation(rp, client, mk):
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2}, {"product_id": rp.cola.id})
    it = _items(cl.get(f"{O}/{oid}").json())
    osh, cola = it["Osh"]["id"], it["Cola"]["id"]
    bad = [
        {},
        {"parts": [[]]},
        {"parts": [[{"item_id": 999999}]]},
        {"parts": [[{"item_id": osh, "quantity": 3}]]},
        {"parts": [[{"item_id": osh, "quantity": 1}], [{"item_id": osh, "quantity": 1.5}]]},
        {"parts": [[{"item_id": osh}, {"item_id": cola}]]},                      # hammasi ko'chadi
        {"parts": [[{"item_id": osh, "quantity": -1}]]},
        {"equal": 1}, {"equal": 21},
        {"equal": 2, "parts": [[{"item_id": cola}]]},
    ]
    for body in bad:
        assert cl.post(f"{O}/{oid}/split", json=body).status_code == 400, body
    # pre-chek qulflangan chekni bo'lib bo'lmaydi
    assert cl.post(f"{O}/{oid}/precheck").status_code == 200
    r = cl.post(f"{O}/{oid}/split", json={"equal": 2})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PRECHECK_LOCKED"
    acc = mk.user(rp.c, role=UserRole.accountant, branch=rp.b)
    assert client.login(acc).post(f"{O}/{oid}/split", json={"equal": 2}).status_code == 403
    # to'langan chek bo'linmaydi
    cl = client.login(rp.cashier)
    oid2 = rp.ready_check(cl, {"product_id": rp.cola.id, "quantity": 2}, table=1)
    _pay(cl, cl.get(f"{O}/{oid2}").json())
    assert cl.post(f"{O}/{oid2}/split", json={"equal": 2}).status_code == 409


def test_frontend_split_wired():
    orders = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantOrders.jsx'), encoding='utf-8').read()
    assert "/split" in orders and "equal" in orders and "parts" in orders
    keys = set(re.findall(r"'(restSplit\.[\w.]+)'", orders))
    assert keys
    for lang in ('uz', 'ru', 'en'):
        d = open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8').read()
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
