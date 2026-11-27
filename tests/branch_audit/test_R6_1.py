"""R6.1 — Ofitsiant plansheti: menejer ulaydi (token bir marta, bazada xesh), xodimlar ro'yxati (PIN, ruxsat, filial),
PIN bilan kirish (xato urinishlar bloki), sessiya tokeni planshetga bog'langan (bekor qilinsa yaroqsiz), ruxsatlar.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R6_1.py -q -p no:cacheprovider
"""
import hashlib
import os
import re

import pytest

from app.core.dependencies import get_current_user, get_current_user_allow_expired
from app.main import app
from app.models.restaurant import RestaurantTerminal
from app.models.user import UserRole
from app.services import restaurant_orders as svc
from tests.branch_audit.test_R3 import PIN, R

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
T = "/api/restaurant/terminals"
P = "/api/restaurant/terminal"
CASHIER_PIN = "2580"


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield
    svc._PIN_FAILS.clear()


@pytest.fixture
def r(db, mk):
    x = R(db, mk)
    svc.set_pin(x.cashier, CASHIER_PIN)
    db.flush()
    return x


def _create(client, r, name="Zal plansheti"):
    res = client.login(r.mgr).post(T, json={"branch_id": r.b.id, "name": name})
    assert res.status_code == 201, res.text
    return res.json()


def _real_auth(client):
    """Haqiqiy token tekshiruvi uchun test o'rnini bosuvchini olib tashlaydi."""
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_allow_expired, None)
    return client


def test_create_list_revoke(r, client, db):
    t = _create(client, r)
    assert t["token"] and len(t["token"]) >= 40 and t["branch_name"] == r.b.name
    row = db.get(RestaurantTerminal, t["id"])
    assert row.token_hash == hashlib.sha256(t["token"].encode()).hexdigest() and t["token"] not in row.token_hash
    lst = client.login(r.mgr).get(T).json()
    assert [x["id"] for x in lst] == [t["id"]] and "token" not in lst[0]
    assert client.login(r.cashier).post(T, json={"branch_id": r.b.id, "name": "x"}).status_code == 403
    assert client.login(r.mgr).post(T, json={"branch_id": r.b.id, "name": " "}).status_code == 400
    assert client.login(r.mgr).delete(f"{T}/{t['id']}").status_code == 200
    assert client.login(r.mgr).get(T).json() == []
    assert client.get(f"{P}/staff", headers={"X-Terminal-Token": t["token"]}).status_code == 401


def test_staff_list_filters(r, client, mk, db):
    t = _create(client, r)
    acc = mk.user(r.c, role=UserRole.accountant, branch=r.b)
    svc.set_pin(acc, "7391")
    cook = mk.user(r.c, role=UserRole.warehouse, branch=r.b, permissions={"restaurant": {"kitchen": True}})
    svc.set_pin(cook, "7392")
    b2 = mk.branch(r.c)
    other_branch = mk.user(r.c, role=UserRole.cashier, branch=b2)
    svc.set_pin(other_branch, "7393")
    db.flush()
    res = client.get(f"{P}/staff", headers={"X-Terminal-Token": t["token"]})
    assert res.status_code == 200, res.text
    body = res.json()
    names = {s["name"] for s in body["staff"]}
    # kassir va menejer (PIN bor), oshpaz (kitchen) — bor; admin (PINsiz), buxgalter, boshqa filial — yo'q
    assert names == {r.cashier.name, r.mgr.name, cook.name}
    assert body["branch_id"] == r.b.id and body["terminal"] == "Zal plansheti"
    assert client.get(f"{P}/staff").status_code == 401
    assert client.get(f"{P}/staff", headers={"X-Terminal-Token": "noto'g'ri"}).status_code == 401
    assert client.post(f"{P}/login", headers={"X-Terminal-Token": t["token"]},
                       json={"user_id": other_branch.id, "pin": "7393"}).status_code == 403


def test_pin_login_session_and_revoke(r, client, db):
    t = _create(client, r)
    h = {"X-Terminal-Token": t["token"]}
    assert client.post(f"{P}/login", headers=h, json={"user_id": r.cashier.id, "pin": "0000"}).status_code == 401
    res = client.post(f"{P}/login", headers=h, json={"user_id": r.cashier.id, "pin": CASHIER_PIN})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user"]["id"] == r.cashier.id and body["branch_id"] == r.b.id and "refresh_token" not in body
    assert db.get(RestaurantTerminal, t["id"]).last_used_at is not None
    token = body["access_token"]
    cl = _real_auth(client)
    perms = cl.get("/api/restaurant/me/perms", headers={"Authorization": f"Bearer {token}"})
    assert perms.status_code == 200 and perms.json()["orders"] is True
    # planshet bekor qilinsa sessiya darhol yaroqsiz
    db.get(RestaurantTerminal, t["id"]).revoked_at = db.get(RestaurantTerminal, t["id"]).created_at
    db.flush()
    assert cl.get("/api/restaurant/me/perms", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_pin_lockout(r, client):
    t = _create(client, r)
    h = {"X-Terminal-Token": t["token"]}
    for _ in range(svc.PIN_MAX_FAILS):
        assert client.post(f"{P}/login", headers=h, json={"user_id": r.mgr.id, "pin": "9999"}).status_code == 401
    res = client.post(f"{P}/login", headers=h, json={"user_id": r.mgr.id, "pin": PIN})
    assert res.status_code == 429


def test_pin_lockout_shared_across_workers(r, client, db):
    """Xotiradagi hisob bo'sh (boshqa worker) bo'lsa ham audit jurnalidagi xato urinishlar bloklaydi."""
    from app.models.audit_log import AuditLog
    t = _create(client, r)
    for _ in range(svc.PIN_MAX_FAILS):
        db.add(AuditLog(action="REST_PIN_FAIL", entity_type="user", entity_id=r.mgr.id, user_id=r.mgr.id))
    db.flush()
    res = client.post(f"{P}/login", headers={"X-Terminal-Token": t["token"]}, json={"user_id": r.mgr.id, "pin": PIN})
    assert res.status_code == 429


def test_retail_and_other_company(r, client, mk):
    _, _, _, retail = mk.tenant()
    assert client.login(retail).post(T, json={"name": "x"}).status_code == 403
    other = R(r.db, mk)
    t = _create(client, r)
    assert client.login(other.mgr).delete(f"{T}/{t['id']}").status_code == 404
    # boshqa korxona xodimi bu planshetda kira olmaydi
    assert client.post(f"{P}/login", headers={"X-Terminal-Token": t["token"]},
                       json={"user_id": other.mgr.id, "pin": PIN}).status_code == 403


def test_frontend_waiter_wired():
    app_jsx = open(os.path.join(ROOT, 'frontend/src/App.jsx'), encoding='utf-8').read()
    assert 'path="/waiter"' in app_jsx and "WaiterApp" in app_jsx and 'path="restaurant/terminals"' in app_jsx
    assert "path: '/admin/restaurant/terminals'" in open(os.path.join(ROOT, 'frontend/src/components/AdminLayout.jsx'), encoding='utf-8').read()
    waiter = open(os.path.join(ROOT, 'frontend/src/pages/waiter/WaiterApp.jsx'), encoding='utf-8').read()
    terms = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantTerminals.jsx'), encoding='utf-8').read()
    for token in ("/restaurant/terminal/staff", "/restaurant/terminal/login", "X-Terminal-Token", "applyAuthResponse"):
        assert token in waiter, token
    assert "/restaurant/terminals" in terms and "/waiter?t=" in terms
    keys = set()
    for src in (waiter, terms):
        keys |= set(re.findall(r"'(restTerm\.[\w.]+)'", src))
    keys.add('nav.restaurantTerminals')
    for lang in ('uz', 'ru', 'en'):
        d = open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8').read()
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
