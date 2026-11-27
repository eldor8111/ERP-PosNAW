"""R1.5 — Stop-list: qo'lda to'xtatish (sabab, qachongacha), porsiya hisoblagichi (qo'shishda kamayadi, qoralama
va pishmagan taom bekor qilinsa qaytadi), ingredient yetishmasligi va avtomatik stop sozlamasi, ruxsat va filial.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R1_5.py -q -p no:cacheprovider
"""
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.models.restaurant import MenuStop
from app.models.user import UserRole
from app.services import restaurant_orders as svc
from tests.branch_audit.test_R3 import PIN
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"
S = "/api/restaurant/stop-list"


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


def _add(cl, oid, pid, qty=1):
    return cl.post(f"{O}/{oid}/items", json={"items": [{"product_id": pid, "quantity": qty}]})


def _status(cl, rp):
    r = cl.get(S, params={"branch_id": rp.b.id})
    assert r.status_code == 200, r.text
    return r.json()


def test_manual_stop_until_and_unstop(rp, client, db):
    kc = client.login(rp.cook)
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert kc.put(f"{S}/{rp.osh.id}", json={"branch_id": rp.b.id, "until": past}).status_code == 400
    soon = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    r = kc.put(f"{S}/{rp.osh.id}", json={"branch_id": rp.b.id, "reason": "Go'sht tugadi", "until": soon})
    assert r.status_code == 200, r.text
    st = _status(kc, rp)
    assert st["unavailable"] == [rp.osh.id] and st["can_edit"] is True
    row = st["stops"][0]
    assert row["name"] == "Osh" and row["reason"] == "Go'sht tugadi" and row["effective"] and row["until"]
    assert row["updated_by"] == rp.cook.name
    cl = client.login(rp.cashier)
    oid = rp.open(cl)["id"]
    res = _add(cl, oid, rp.osh.id)
    assert res.status_code == 409 and "stop-list" in res.json()["detail"] and "Go'sht tugadi" in res.json()["detail"]
    assert _add(cl, oid, rp.cola.id).status_code == 200                      # boshqa taom sotiladi
    # muddat o'tdi — o'zi qaytadi
    db.query(MenuStop).update({MenuStop.until: datetime.utcnow() - timedelta(minutes=1)})
    db.flush()
    st = _status(cl, rp)
    assert st["unavailable"] == [] and st["stops"][0]["expired"] is True
    assert _add(cl, oid, rp.osh.id).status_code == 200
    # qayta to'xtatish (muddatsiz) va sotuvga qaytarish
    kc = client.login(rp.cook)
    kc.put(f"{S}/{rp.osh.id}", json={"branch_id": rp.b.id})
    assert _status(kc, rp)["unavailable"] == [rp.osh.id]
    assert kc.delete(f"{S}/{rp.osh.id}", params={"branch_id": rp.b.id}).status_code == 200
    assert _status(kc, rp)["stops"] == [] and db.query(MenuStop).count() == 0


def test_portion_counter(rp, client, db):
    kc = client.login(rp.cook)
    assert kc.put(f"{S}/{rp.osh.id}", json={"branch_id": rp.b.id, "stopped": False, "remaining": 3}).status_code == 200
    left = lambda: D(str(db.query(MenuStop).one().remaining))
    cl = client.login(rp.cashier)
    oid = rp.open(cl)["id"]
    it = _add(cl, oid, rp.osh.id, 2).json()["items"][0]
    assert left() == D("1")
    res = _add(cl, oid, rp.osh.id, 2)
    assert res.status_code == 409 and "faqat 1 porsiya" in res.json()["detail"]
    # bir so'rovda ikki qator jami bo'yicha tekshiriladi
    two = cl.post(f"{O}/{oid}/items", json={"items": [{"product_id": rp.osh.id}, {"product_id": rp.osh.id}]})
    assert two.status_code == 409 and left() == D("1")
    assert cl.patch(f"{O}/{oid}/items/{it['id']}", json={"quantity": 1}).status_code == 200
    assert left() == D("2")
    assert cl.patch(f"{O}/{oid}/items/{it['id']}", json={"quantity": 4}).status_code == 409
    assert cl.post(f"{O}/{oid}/items/{it['id']}/cancel", json={}).status_code == 200    # qoralama o'chdi
    assert left() == D("3")
    it = _add(cl, oid, rp.osh.id, 3).json()["items"][0]
    assert left() == 0
    st = _status(cl, rp)
    assert st["unavailable"] == [rp.osh.id] and st["remaining"] == {str(rp.osh.id): 0}
    res = _add(cl, oid, rp.osh.id)
    assert res.status_code == 409 and "tugadi" in res.json()["detail"]
    assert cl.post(f"{O}/{oid}/send", json={}).status_code == 200
    # pishmagan taom bekor qilinsa porsiya qaytadi
    approval = {"user_id": rp.mgr.id, "pin": PIN}
    r = cl.post(f"{O}/{oid}/items/{it['id']}/cancel", json={"reason": "guest_refused", "approval": approval})
    assert r.status_code == 200, r.text
    assert left() == D("3")
    # tayyorlangan taom bekor qilinsa qaytmaydi
    it2 = _add(cl, oid, rp.osh.id, 1).json()["items"][-1]
    cl.post(f"{O}/{oid}/send", json={})
    kc = client.login(rp.cook)
    kc.post(f"{O}/{oid}/items/{it2['id']}/status", json={"status": "cooking"})
    cl = client.login(rp.cashier)
    cl.post(f"{O}/{oid}/items/{it2['id']}/cancel", json={"reason": "guest_refused", "approval": approval})
    assert left() == D("2")
    # butun chek bekor qilinsa qoralama porsiyasi qaytadi
    _add(cl, oid, rp.osh.id, 2)
    assert left() == 0
    assert cl.post(f"{O}/{oid}/cancel", json={"reason": "guest_refused", "approval": approval}).status_code == 200
    assert left() == D("2")


def test_low_ingredients_and_auto_stop(rp, client, db):
    adm = client.login(rp.admin)
    st = _status(adm, rp)
    assert st["low"] == [] and st["portions"][str(rp.osh.id)] == 66               # 10 kg / 0.15
    rp.stock(rp.rice, rp.kitchen, D("0.1"))
    st = _status(adm, rp)
    assert [x["name"] for x in st["low"]] == ["Osh"] and st["unavailable"] == [] and st["auto_stop"] is False
    miss = st["low"][0]["missing"][0]
    assert miss["name"] == "Guruch" and miss["need"] == 0.15 and miss["have"] == 0.1
    oid = rp.open(adm)["id"]
    assert _add(adm, oid, rp.osh.id).status_code == 200                           # faqat ogohlantirish
    assert adm.put("/api/restaurant/settings", json={"auto_stop_on_no_stock": True}).status_code == 200
    st = _status(adm, rp)
    assert st["auto_stop"] is True and st["unavailable"] == [rp.osh.id]
    res = _add(adm, oid, rp.osh.id)
    assert res.status_code == 409 and "ingredient" in res.json()["detail"]
    rp.stock(rp.rice, rp.kitchen, 5)
    assert _add(adm, oid, rp.osh.id).status_code == 200


def test_permissions_validation_and_scope(rp, client, mk):
    cl = client.login(rp.cashier)
    st = _status(cl, rp)
    assert st["can_edit"] is False
    assert cl.put(f"{S}/{rp.osh.id}", json={"branch_id": rp.b.id}).status_code == 403
    assert cl.delete(f"{S}/{rp.osh.id}", params={"branch_id": rp.b.id}).status_code == 403
    acc = mk.user(rp.c, role=UserRole.accountant, branch=rp.b)
    assert client.login(acc).get(S, params={"branch_id": rp.b.id}).status_code == 403
    kc = client.login(rp.cook)
    assert kc.put(f"{S}/{rp.rice.id}", json={"branch_id": rp.b.id}).status_code == 400   # ingredient emas
    assert kc.put(f"{S}/{rp.osh.id}", json={"branch_id": rp.b.id, "remaining": -1}).status_code == 400
    assert kc.put(f"{S}/999999", json={"branch_id": rp.b.id}).status_code == 404
    assert kc.put(f"{S}/{rp.cola.id}", json={"branch_id": rp.b.id}).status_code == 200  # tovar ham bo'ladi
    # boshqa filial stop-listi alohida, ruxsatsiz filial yopiq
    from app.services.restaurant import provision_restaurant
    b2 = mk.branch(rp.c)
    provision_restaurant(rp.db, rp.c, b2)
    adm = client.login(rp.admin)
    assert adm.get(S, params={"branch_id": b2.id}).json()["stops"] == []
    cook2 = mk.user(rp.c, role=UserRole.warehouse, branch=b2, permissions={"restaurant": {"kitchen": True}})
    assert client.login(cook2).get(S, params={"branch_id": rp.b.id}).status_code == 403
    other = RP(rp.db, mk)
    assert client.login(other.admin).put(f"{S}/{rp.osh.id}", json={"branch_id": other.b.id}).status_code == 404
    _, _, _, retail = mk.tenant()
    assert client.login(retail).get(S).status_code == 403


def test_frontend_stop_list_wired():
    app_jsx = open(os.path.join(ROOT, 'frontend/src/App.jsx'), encoding='utf-8').read()
    assert "RestaurantStopList" in app_jsx and 'path="restaurant/stop-list"' in app_jsx
    assert "path: '/admin/restaurant/stop-list'" in open(os.path.join(ROOT, 'frontend/src/components/AdminLayout.jsx'), encoding='utf-8').read()
    page = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantStopList.jsx'), encoding='utf-8').read()
    orders = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantOrders.jsx'), encoding='utf-8').read()
    for token in ("/restaurant/stop-list", "auto_stop_on_no_stock", "remaining", "until"):
        assert token in page, token
    assert "/restaurant/stop-list" in orders and "unavailable" in orders
    keys = set()
    for src in (page, orders):
        keys |= set(re.findall(r"'(restStop\.[\w.]+)'", src))
    keys.add('nav.restaurantStopList')
    for lang in ('uz', 'ru', 'en'):
        d = open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8').read()
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
