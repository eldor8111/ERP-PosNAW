"""R4.1 — Oshxona tiketlarini chop etish navbati: sex filtri, atomar egallash (ikki qurilma bir tiketni ikki
marta chiqarmaydi), qayta chop etish, bekor qilish tiketi, eski tiketlar navbatda yo'q, ruxsat va filial doirasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R4_1.py -q -p no:cacheprovider
"""
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.models.restaurant_order import KitchenTicket
from app.models.user import UserRole
from app.services import restaurant_orders as svc
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"
P = "/api/restaurant/print"


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


@pytest.fixture
def rp(db, mk):
    r = RP(db, mk)
    r.cook = mk.user(r.c, role=UserRole.warehouse, branch=r.b, permissions={"restaurant": {"kitchen": True}})
    db.flush()
    return r


def _queue(cl, rp, **params):
    r = cl.get(f"{P}/queue", params={"branch_id": rp.b.id, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_queue_by_station_and_content(rp, client):
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2, "comment": "achchiq"},
                         {"product_id": rp.salad.id}, {"product_id": rp.cola.id}, table=0)
    kc = client.login(rp.cook)
    allq = _queue(kc, rp)
    assert len(allq) == 3 and all(t["order_id"] == oid for t in allq)
    hot = _queue(kc, rp, station=str(rp.hot.id))
    assert len(hot) == 1 and hot[0]["station_name"] == "Issiq sex" and hot[0]["table_name"] == "1"
    assert hot[0]["lines"][0]["name"] == "Osh" and hot[0]["lines"][0]["quantity"] == 2
    assert hot[0]["lines"][0]["comment"] == "achchiq" and hot[0]["waiter_name"] == rp.cashier.name
    two = _queue(kc, rp, station=f"{rp.hot.id},{rp.cold.id}")
    assert {t["station_name"] for t in two} == {"Issiq sex", "Sovuq sex"}
    none = _queue(kc, rp, station="none")
    assert [t["lines"][0]["name"] for t in none] == ["Cola"]
    assert kc.get(f"{P}/queue", params={"branch_id": rp.b.id, "station": "abc"}).status_code == 400


def test_claim_is_atomic_and_reprint(rp, client, db):
    cl = client.login(rp.cashier)
    rp.ready_check(cl, {"product_id": rp.osh.id})
    kc = client.login(rp.cook)
    ids = [t["id"] for t in _queue(kc, rp)]
    first = kc.post(f"{P}/claim", json={"ticket_ids": ids}).json()
    assert [t["id"] for t in first] == ids and first[0]["printed_at"] and first[0]["print_attempts"] == 1
    assert kc.post(f"{P}/claim", json={"ticket_ids": ids}).json() == []       # ikkinchi qurilma — bo'sh
    assert _queue(kc, rp) == []
    assert [t["id"] for t in kc.get(f"{P}/recent", params={"branch_id": rp.b.id}).json()] == ids
    assert kc.post(f"{P}/{ids[0]}/reprint").status_code == 200
    again = kc.post(f"{P}/claim", json={"ticket_ids": ids}).json()
    assert again[0]["print_attempts"] == 2
    assert kc.post(f"{P}/999999/reprint").status_code == 404


def test_cancel_ticket_and_old_tickets_hidden(rp, client, db):
    adm = client.login(rp.admin)
    oid = rp.ready_check(adm, {"product_id": rp.osh.id})
    iid = adm.get(f"{O}/{oid}").json()["items"][0]["id"]
    adm.post(f"{O}/{oid}/items/{iid}/cancel", json={"reason": "mistake"})
    kinds = [t["kind"] for t in _queue(client.login(rp.cook), rp)]
    assert kinds == ["order", "cancel"]
    for t in db.query(KitchenTicket).filter(KitchenTicket.order_id == oid):
        t.created_at = datetime.now(timezone.utc) - timedelta(hours=13)
    db.flush()
    assert _queue(client.login(rp.cook), rp) == []


def test_permissions_and_scope(rp, client, mk):
    from app.services.restaurant import provision_restaurant
    cl = client.login(rp.cashier)
    rp.ready_check(cl, {"product_id": rp.osh.id})
    ids = [t["id"] for t in _queue(cl, rp)]                                   # kassir (orders) ko'ra oladi
    acc = mk.user(rp.c, role=UserRole.accountant, branch=rp.b)
    assert client.login(acc).get(f"{P}/queue", params={"branch_id": rp.b.id}).status_code == 403
    b2 = mk.branch(rp.c)
    provision_restaurant(rp.db, rp.c, b2)
    cook2 = mk.user(rp.c, role=UserRole.warehouse, branch=b2, permissions={"restaurant": {"kitchen": True}})
    c2 = client.login(cook2)
    assert c2.get(f"{P}/queue", params={"branch_id": rp.b.id}).status_code == 403
    assert c2.post(f"{P}/claim", json={"ticket_ids": ids}).json() == []       # boshqa filial tiketi egallanmaydi
    assert c2.post(f"{P}/{ids[0]}/reprint").status_code == 404
    _, _, _, retail = mk.tenant()
    assert client.login(retail).get(f"{P}/queue").status_code == 403


def test_frontend_print_station_wired():
    app_jsx = open(os.path.join(ROOT, 'frontend/src/App.jsx'), encoding='utf-8').read()
    assert "RestaurantPrintStation" in app_jsx and 'path="restaurant/print"' in app_jsx
    assert "path: '/admin/restaurant/print'" in open(os.path.join(ROOT, 'frontend/src/components/AdminLayout.jsx'), encoding='utf-8').read()
    page = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantPrintStation.jsx'), encoding='utf-8').read()
    for token in ("/restaurant/print/queue", "/restaurant/print/claim", "/reprint", "kiosk-printing", "contentWindow"):
        assert token in page, token
    keys = set(re.findall(r"'(restPrint\.[\w.]+)'", page)) | {'nav.restaurantPrint'}
    for lang in ('uz', 'ru', 'en'):
        d = open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8').read()
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
