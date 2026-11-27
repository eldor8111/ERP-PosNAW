"""Restoran hisobotlari (12-bo'lim: 1, 2, 4, 8): ko'rsatkichlar, to'lov turlari, taomlar (haqiqiy tannarx bilan),
ofitsiantlar, bekor qilishlar, chegirmalar, qaytarishning ta'siri, davr va ruxsatlar.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R_reports.py -q -p no:cacheprovider
"""
import os
import re
from datetime import timedelta

import pytest

from app.models.user import UserRole
from app.services import restaurant_orders as svc
from app.services.document_numbers import tashkent_today
from tests.branch_audit.test_R3 import PIN
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"
REP = "/api/restaurant/reports/summary"


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


@pytest.fixture
def day(db, mk):
    """Bir kun: 3 ta to'langan chek, 1 ta tayyorlangan taom bekor qilingan, 1 ta chek qaytarilgan."""
    rp = RP(db, mk)
    from app.services.restaurant_orders import set_pin
    set_pin(rp.admin, PIN)
    return rp


def _pay(cl, oid, total, ptype="cash"):
    r = cl.post(f"{O}/{oid}/pay", json={"payments": [{"type": ptype, "amount": total}]})
    assert r.status_code == 200, r.text
    return r.json()


def _build(rp, client):
    cl = client.login(rp.cashier)
    o1 = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2}, {"product_id": rp.cola.id}, table=0)
    _pay(cl, o1, 121000)
    adm = client.login(rp.admin)
    o2 = adm.post(O, json={"order_type": "takeaway", "branch_id": rp.b.id}).json()["id"]
    adm.post(f"{O}/{o2}/items", json={"items": [{"product_id": rp.cola.id}]})
    adm.post(f"{O}/{o2}/send", json={})
    _pay(adm, o2, 10000, "card")
    o3 = rp.ready_check(adm, {"product_id": rp.osh.id}, table=1)
    adm.post(f"{O}/{o3}/discount", json={"pct": 10, "reason": "doimiy mijoz"})
    _pay(adm, o3, 49500)
    o4 = rp.ready_check(adm, {"product_id": rp.osh.id}, table=2)
    iid = adm.get(f"{O}/{o4}").json()["items"][0]["id"]
    adm.post(f"{O}/{o4}/items/{iid}/status", json={"status": "ready"})
    adm.post(f"{O}/{o4}/items/{iid}/cancel", json={"reason": "spoiled"})
    r = adm.post(f"{O}/{o2}/refund", json={"reason": "quality", "payment_type": "card"})
    assert r.status_code == 200, r.text
    return o1, o2, o3, o4


def test_summary_numbers(day, client):
    rp = day
    _build(rp, client)
    rep = client.login(rp.admin).get(REP).json()
    k = rep["kpi"]
    assert (k["gross"], k["refunded"], k["revenue"], k["checks"]) == (180500, 10000, 170500, 3)
    assert k["guests"] == 4 and k["avg_check"] == 56833.33 and k["avg_per_guest"] == 42625
    assert (k["service"], k["discounts"], k["cancels"], k["cancel_amount"]) == (15500, 5000, 1, 50000)
    assert rep["payments"] == {"card": 10000, "cash": 170500}
    assert rep["by_type"]["takeaway"] == {"checks": 1, "revenue": 0}
    dishes = {d["name"]: d for d in rep["dishes"]}
    # osh: 3 porsiya sotilgan (bekor qilingani hisobda emas), tannarx 3 * 0.15 kg * 20000
    assert dishes["Osh"]["qty"] == 3 and dishes["Osh"]["revenue"] == 150000 and dishes["Osh"]["cost"] == 9000
    assert dishes["Osh"]["food_cost_pct"] == 6.0
    assert dishes["Cola"]["qty"] == 1                   # qaytarilgan cola hisobdan chiqdi
    assert [d["name"] for d in rep["dishes"]][0] == "Osh"
    waiters = {w["name"]: w for w in rep["waiters"]}
    assert waiters[rp.cashier.name]["revenue"] == 121000 and waiters[rp.cashier.name]["checks"] == 1
    assert waiters[rp.admin.name]["checks"] == 2 and waiters[rp.admin.name]["revenue"] == 49500
    assert waiters[rp.admin.name]["cancels"] == 1
    c = rep["cancellations"][0]
    assert c["name"] == "Osh" and c["write_off"] is True and c["reason"].startswith("spoiled")
    assert c["cancelled_by"] == rp.admin.name
    d = rep["discounts"][0]
    assert d["amount"] == 5000 and d["pct"] == 10 and d["reason"] == "doimiy mijoz"


def test_other_day_empty_and_range_validation(day, client):
    rp = day
    _build(rp, client)
    cl = client.login(rp.admin)
    y = (tashkent_today() - timedelta(days=1)).isoformat()
    rep = cl.get(REP, params={"date_from": y, "date_to": y}).json()
    assert rep["kpi"]["checks"] == 0 and rep["dishes"] == [] and rep["cancellations"] == []
    today = tashkent_today()
    assert cl.get(REP, params={"date_from": today.isoformat(), "date_to": y}).status_code == 400
    far = (today - timedelta(days=100)).isoformat()
    assert cl.get(REP, params={"date_from": far, "date_to": today.isoformat()}).status_code == 400


def test_permissions_and_branch_scope(day, client, mk):
    rp = day
    _build(rp, client)
    assert client.login(rp.cashier).get(REP).status_code == 403
    b2 = mk.branch(rp.c)
    mgr2 = mk.user(rp.c, role=UserRole.manager, branch=b2)
    rep = client.login(mgr2).get(REP).json()           # boshqa filial menejeri — o'z filiali (bo'sh)
    assert rep["kpi"]["checks"] == 0
    assert client.login(mgr2).get(REP, params={"branch_id": rp.b.id}).status_code == 403
    _, _, _, retail = mk.tenant()
    assert client.login(retail).get(REP).status_code == 403


def test_frontend_reports_page_wired():
    app_jsx = open(os.path.join(ROOT, 'frontend/src/App.jsx'), encoding='utf-8').read()
    assert "RestaurantReports" in app_jsx and 'path="restaurant/reports"' in app_jsx
    layout = open(os.path.join(ROOT, 'frontend/src/components/AdminLayout.jsx'), encoding='utf-8').read()
    assert "path: '/admin/restaurant/reports'" in layout
    page = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantReports.jsx'), encoding='utf-8').read()
    assert "/restaurant/reports/summary" in page
    keys = set(re.findall(r"'(restRep\.[\w.]+)'", page)) | {'nav.restaurantReports'}
    for lang in ('uz', 'ru', 'en'):
        d = open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8').read()
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
