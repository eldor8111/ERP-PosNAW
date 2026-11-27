"""R4.2 — Oshxona ekrani (KDS): kartochkalar, sex filtri, norma, yig'indi, bir yo'la holat o'zgartirish,
bekor qilingan taom ko'rinishi, to'langan chek yo'qolishi, ruxsatlar va filial doirasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R4_2.py -q -p no:cacheprovider
"""
import os
import re

import pytest

from app.models.user import UserRole
from app.services import restaurant_orders as svc
from app.services.restaurant_menu import save_card
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"
K = "/api/restaurant/kds"


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


@pytest.fixture
def rp(db, mk):
    r = RP(db, mk)
    save_card(db, r.c.id, r.osh, {"cooking_time_min": 20, "items": [{"component_product_id": r.rice.id, "gross_qty": 0.15}]}, None)
    r.cook = mk.user(r.c, role=UserRole.warehouse, branch=r.b, permissions={"restaurant": {"kitchen": True}})
    db.flush()
    return r


def _board(cl, rp, **params):
    r = cl.get(K, params={"branch_id": rp.b.id, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_board_cards_filters_norm_and_totals(rp, client):
    cl = client.login(rp.cashier)
    o1 = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2, "comment": "piyozsiz"},
                        {"product_id": rp.salad.id}, {"product_id": rp.cola.id}, table=0)
    o2 = rp.ready_check(cl, {"product_id": rp.osh.id}, table=1)
    o3 = rp.open(cl, 2)["id"]
    rp.add(cl, o3, {"product_id": rp.osh.id})                          # draft — ekranda yo'q
    kc = client.login(rp.cook)
    b = _board(kc, rp)
    assert [c["order_id"] for c in b["cards"]] == [o1, o2]               # yuborilish tartibida
    c1 = b["cards"][0]
    assert c1["table_name"] == "1" and c1["waiter_name"] == rp.cashier.name
    osh = next(i for i in c1["items"] if i["name"] == "Osh")
    assert osh["quantity"] == 2 and osh["comment"] == "piyozsiz" and osh["norm_min"] == 20 and osh["status"] == "sent"
    assert {t["name"]: t["quantity"] for t in b["totals"]}["Osh"] == 3
    hot = _board(kc, rp, station=str(rp.hot.id))
    assert {i["name"] for c in hot["cards"] for i in c["items"]} == {"Osh"}
    cold = _board(kc, rp, station=str(rp.cold.id))
    assert {i["name"] for c in cold["cards"] for i in c["items"]} == {"Achchiq-chuchuk"}
    none = _board(kc, rp, station="none")
    assert {i["name"] for c in none["cards"] for i in c["items"]} == {"Cola"}


def test_bulk_status_idempotent_and_ready_reaches_floor(rp, client):
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id}, {"product_id": rp.salad.id})
    ids = [i["id"] for i in cl.get(f"{O}/{oid}").json()["items"]]
    kc = client.login(rp.cook)
    assert kc.post(f"{K}/status", json={"item_ids": ids, "status": "cooking"}).json()["changed"] == 2
    assert kc.post(f"{K}/status", json={"item_ids": ids, "status": "ready"}).json()["changed"] == 2
    assert kc.post(f"{K}/status", json={"item_ids": ids, "status": "ready"}).json()["changed"] == 0   # takroriy
    assert kc.post(f"{K}/status", json={"item_ids": ids, "status": "cooking"}).json()["changed"] == 0  # orqaga yo'q
    st = {x["table_id"]: x["status"] for x in client.login(rp.cashier).get(
        "/api/restaurant/tables/status", params={"branch_id": rp.b.id}).json()}
    assert st[rp.tables[0].id] == "ready"
    # ofitsiant "berildi" qiladi — kartochka yo'qoladi
    assert client.login(rp.cashier).post(f"{K}/status", json={"item_ids": ids, "status": "served"}).json()["changed"] == 2
    assert _board(client.login(rp.cook), rp)["cards"] == []


def test_permissions(rp, client, mk):
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id})
    iid = cl.get(f"{O}/{oid}").json()["items"][0]["id"]
    assert cl.post(f"{K}/status", json={"item_ids": [iid], "status": "cooking"}).status_code == 403   # kassir oshpaz emas
    acc = mk.user(rp.c, role=UserRole.accountant, branch=rp.b)
    assert client.login(acc).get(K, params={"branch_id": rp.b.id}).status_code == 403
    assert client.login(rp.cook).post(f"{K}/status", json={"item_ids": [iid], "status": "bad"}).status_code == 400
    assert client.login(rp.cook).post(f"{K}/status", json={"item_ids": [999999], "status": "ready"}).status_code == 404
    _, _, _, retail = mk.tenant()
    assert client.login(retail).get(K).status_code == 403


def test_cancelled_shown_and_paid_removed(rp, client):
    adm = client.login(rp.admin)
    oid = rp.ready_check(adm, {"product_id": rp.osh.id}, {"product_id": rp.salad.id})
    items = adm.get(f"{O}/{oid}").json()["items"]
    osh = next(i for i in items if i["name"] == "Osh")
    adm.post(f"{O}/{oid}/items/{osh['id']}/cancel", json={"reason": "mistake"})
    b = _board(client.login(rp.cook), rp)
    st = {i["name"]: i["status"] for c in b["cards"] for i in c["items"]}
    assert st["Osh"] == "cancelled" and st["Achchiq-chuchuk"] == "sent"
    assert "Osh" not in {t["name"] for t in b["totals"]}
    r = client.login(rp.admin).post(f"{O}/{oid}/pay", json={"payments": [{"type": "cash", "amount": 22000}]})
    assert r.status_code == 200, r.text
    assert _board(client.login(rp.cook), rp)["cards"] == []


def test_branch_scope(rp, client, mk):
    from app.services.restaurant import provision_restaurant
    b2 = mk.branch(rp.c)
    provision_restaurant(rp.db, rp.c, b2)
    cook2 = mk.user(rp.c, role=UserRole.warehouse, branch=b2, permissions={"restaurant": {"kitchen": True}})
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id})
    iid = cl.get(f"{O}/{oid}").json()["items"][0]["id"]
    c2 = client.login(cook2)
    assert c2.get(K, params={"branch_id": rp.b.id}).status_code == 403
    assert c2.get(K).json()["cards"] == []                              # o'z filiali bo'sh
    assert c2.post(f"{K}/status", json={"item_ids": [iid], "status": "cooking"}).status_code == 403


def test_frontend_kds_wired():
    app_jsx = open(os.path.join(ROOT, 'frontend/src/App.jsx'), encoding='utf-8').read()
    assert "RestaurantKds" in app_jsx and 'path="restaurant/kds"' in app_jsx
    assert "path: '/admin/restaurant/kds'" in open(os.path.join(ROOT, 'frontend/src/components/AdminLayout.jsx'), encoding='utf-8').read()
    page = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantKds.jsx'), encoding='utf-8').read()
    for token in ("/restaurant/kds", "/restaurant/kds/status", "norm_min", "totals", "setInterval"):
        assert token in page, token
    orders = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantOrders.jsx'), encoding='utf-8').read()
    assert "restOrd.readyNotice" in orders
    keys = set(re.findall(r"'(restKds\.[\w.]+)'", page)) | {'nav.restaurantKds', 'restOrd.readyNotice'}
    for lang in ('uz', 'ru', 'en'):
        d = open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8').read()
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
