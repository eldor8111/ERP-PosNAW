"""Restoran bosh sahifasi: bugungi tushum, ochiq cheklar va stollar, oshxona navbati va me'yordan kechikkan taomlar,
bugungi bronlar, stop-list; ruxsat va filial doirasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R_dashboard.py -q -p no:cacheprovider
"""
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.models.restaurant_order import RestaurantOrderItem
from app.services import restaurant_orders as svc
from app.services.restaurant_menu import save_card
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"
D = "/api/restaurant/reports/dashboard"


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


@pytest.fixture
def rp(db, mk):
    return RP(db, mk)


def test_dashboard_numbers(rp, client, db):
    save_card(db, rp.c.id, rp.osh, {"cooking_time_min": 10, "items": [{"component_product_id": rp.rice.id,
                                                                        "gross_qty": 0.15}]}, None)
    cl = client.login(rp.cashier)
    paid = rp.ready_check(cl, {"product_id": rp.cola.id}, table=1)
    assert cl.post(f"{O}/{paid}/pay", json={"payments": [{"type": "cash", "amount": 11000}]}).status_code == 200
    o1 = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2}, table=0)       # oshxonada, kechikkan
    o2 = rp.open(cl, table=2)["id"]
    rp.add(cl, o2, {"product_id": rp.osh.id})                                         # qoralama: navbatda emas
    for it in db.query(RestaurantOrderItem).filter(RestaurantOrderItem.order_id == o1):
        it.sent_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=25)
    db.flush()
    # bron (bugun, 1 soatdan keyin) va stop-list
    start = (datetime.now(timezone.utc) + timedelta(minutes=60)).replace(second=0, microsecond=0).isoformat()
    r = cl.post("/api/restaurant/reservations", json={"branch_id": rp.b.id, "table_ids": [rp.tables[3].id],
                                                      "starts_at": start, "guests": 5, "name": "Kamola"})
    assert r.status_code == 201, r.text
    adm = client.login(rp.admin)
    assert adm.put(f"/api/restaurant/stop-list/{rp.salad.id}", json={"branch_id": rp.b.id, "reason": "tugadi"}).status_code == 200

    out = adm.get(D).json()
    assert out["today"]["revenue"] == 11000 and out["today"]["checks"] == 1
    assert out["open"]["checks"] == 2 and out["open"]["busy_tables"] == 2 and out["open"]["tables"] == len(rp.tables)
    assert out["open"]["sum"] == 110000 + 55000
    k = out["kitchen"]
    assert k["queue"] == 1 and k["late"] == 1
    li = k["late_items"][0]
    assert li["name"] == "Osh" and li["norm"] == 10 and li["over"] >= 14 and li["table"] == rp.tables[0].name
    assert k["stations"][0]["name"] == rp.hot.name and k["stations"][0]["late"] == 1
    res = out["reservations"]
    # bron Toshkent vaqti bo'yicha bugun yoki ertaga tushishi mumkin (soatga qarab)
    if res["items"]:
        assert res["items"][0]["name"] == "Kamola" and res["guests"] == 5
    assert out["stop_list"]["stopped"] == [rp.salad.name]


def test_permissions(rp, client):
    assert client.login(rp.cashier).get(D).status_code == 403
    assert client.login(rp.mgr).get(D).status_code == 200


def test_frontend_wired_and_i18n():
    app_jsx = _read('frontend/src/App.jsx')
    assert "RestaurantDashboard" in app_jsx and 'path="restaurant/dashboard"' in app_jsx
    layout = _read('frontend/src/components/AdminLayout.jsx')
    assert "path: '/admin/restaurant/dashboard'" in layout
    page = _read('frontend/src/pages/admin/restaurant/RestaurantDashboard.jsx')
    for token in ("/restaurant/reports/dashboard", "late_items", "reservations", "stop_list"):
        assert token in page, token
    keys = set(re.findall(r"'(restDash\.[\w.]+)'", page)) | {'nav.restaurantDashboard'}
    assert len(keys) > 15
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
