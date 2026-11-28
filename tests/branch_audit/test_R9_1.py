"""R9.1 — Restoran tariflari va Super Admin "Restoranlar" bo'limi: tarif turi va restoran maydonlari, ro'yxat
turlar bo'yicha ajratilgan, boshqa turdagi tarifni sotib olib (yoki biriktirib) bo'lmaydi, restoran imkoniyatlari
(KDS, bron) tarif bo'yicha yopiladi, ofitsiant planshetlari limiti, sinov tarifi turi bo'yicha, restoranlar ro'yxati.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R9_1.py -q -p no:cacheprovider
"""
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.models.billing import Tariff
from app.models.user import UserRole
from app.services import restaurant_orders as svc
from tests.branch_audit.test_R3 import R

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
T = "/api/billing/tariffs"


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


def _tariff(db, **kw):
    t = Tariff(name=kw.pop("name", "T"), price_per_month=kw.pop("price_per_month", 100000), duration_days=30,
               is_active=True, **kw)
    db.add(t)
    db.flush()
    return t


def _subscribe(db, company, tariff):
    company.tariff_id = tariff.id
    company.subscription_ends_at = datetime.now(timezone.utc) + timedelta(days=20)
    db.flush()
    db.expire(company)


@pytest.fixture
def r(db, mk):
    return R(db, mk)


def test_super_admin_crud_and_lists(client, db, mk):
    sa = client.login(mk.user(None, role=UserRole.super_admin))
    res = sa.post(T, json={"name": "Kafe", "price_per_month": 176000, "business_type": "restaurant",
                           "max_waiter_devices": 2, "max_kds_screens": 1,
                           "restaurant_features": ["reservations", "kds"]})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["business_type"] == "restaurant" and out["restaurant_features"] == ["kds", "reservations"]
    assert out["max_waiter_devices"] == 2 and out["max_kds_screens"] == 1
    assert sa.post(T, json={"name": "X", "business_type": "cafe"}).status_code == 400
    assert sa.post(T, json={"name": "X", "business_type": "restaurant", "restaurant_features": ["wifi"]}).status_code == 400
    # tahrir: null bilan cheklov olib tashlanadi
    out = sa.put(f"{T}/{out['id']}", json={"max_waiter_devices": None, "restaurant_features": None}).json()
    assert out["max_waiter_devices"] is None and out["restaurant_features"] is None and out["max_kds_screens"] == 1
    _tariff(db, name="Do'kon Pro")
    pub = client.get(T).json()                                         # sukut: faqat do'kon tariflari
    assert "Do'kon Pro" in [x["name"] for x in pub] and "Kafe" not in [x["name"] for x in pub]
    rest = client.get(T, params={"business_type": "restaurant"}).json()
    assert [x["name"] for x in rest] == ["Kafe"]
    names = [x["name"] for x in sa.get(T, params={"all": True}).json()]
    assert "Kafe" in names and "Do'kon Pro" in names


def test_type_mismatch_rejected(r, client, db, mk):
    retail_t = _tariff(db, name="Pro")
    rest_t = _tariff(db, name="Restoran", business_type="restaurant")
    r.c.balance = 10_000_000
    db.flush()
    cl = client.login(r.admin)
    res = cl.post("/api/billing/my-company/subscribe", json={"tariff_id": retail_t.id, "months": 1})
    assert res.status_code == 400 and res.json()["detail"]["code"] == "TARIFF_TYPE_MISMATCH"
    assert cl.get(f"{T}/{retail_t.id}/quote").status_code == 400
    assert cl.get(f"{T}/{rest_t.id}/quote").status_code == 200
    sa = client.login(mk.user(None, role=UserRole.super_admin))
    res = sa.post(f"/api/billing/companies/{r.c.id}/subscribe", json={"tariff_id": retail_t.id, "months": 1})
    assert res.status_code == 400
    # do'kon korxonasi restoran tarifini ololmaydi
    shop, _, _, u = mk.tenant()
    shop.balance = 10_000_000
    db.flush()
    res = client.login(u).post("/api/billing/my-company/subscribe", json={"tariff_id": rest_t.id, "months": 1})
    assert res.status_code == 400
    res = client.login(r.admin).post("/api/billing/my-company/subscribe", json={"tariff_id": rest_t.id, "months": 1})
    assert res.status_code == 200, res.text


def test_feature_gating(r, client, db):
    cl = client.login(r.admin)
    # restoran tarifi yo'q (yoki ro'yxat belgilanmagan): hammasi ochiq
    assert cl.get("/api/companies/me/features").json()["restaurant_features"] == ["kds", "reservations", "delivery",
                                                                                   "aggregators", "qr_menu"]
    assert cl.get("/api/restaurant/kds", params={"branch_id": r.b.id}).status_code == 200
    t = _tariff(db, name="Kafe", business_type="restaurant", restaurant_features=["kds"])
    _subscribe(db, r.c, t)
    assert cl.get("/api/companies/me/features").json()["restaurant_features"] == ["kds"]
    assert cl.get("/api/restaurant/kds", params={"branch_id": r.b.id}).status_code == 200
    res = cl.get("/api/restaurant/reservations", params={"branch_id": r.b.id})
    assert res.status_code == 403 and res.json()["detail"]["code"] == "TARIFF_FEATURE"
    t.restaurant_features = []
    db.flush()
    assert cl.get("/api/restaurant/kds", params={"branch_id": r.b.id}).status_code == 403
    t.restaurant_features = None
    db.flush()
    assert cl.get("/api/restaurant/reservations", params={"branch_id": r.b.id}).status_code == 200


def test_waiter_device_limit(r, client, db):
    t = _tariff(db, name="Kafe", business_type="restaurant", max_waiter_devices=1)
    _subscribe(db, r.c, t)
    cl = client.login(r.admin)
    first = cl.post("/api/restaurant/terminals", json={"branch_id": r.b.id, "name": "Zal 1"})
    assert first.status_code == 201, first.text
    res = cl.post("/api/restaurant/terminals", json={"branch_id": r.b.id, "name": "Zal 2"})
    assert res.status_code == 403 and res.json()["detail"]["code"] == "TARIFF_LIMIT"
    assert cl.delete(f"/api/restaurant/terminals/{first.json()['id']}").status_code == 200
    assert cl.post("/api/restaurant/terminals", json={"branch_id": r.b.id, "name": "Zal 2"}).status_code == 201


def test_trial_picks_restaurant_trial_tariff(r, client, db):
    _tariff(db, name="Sinov", price_per_month=0)
    rt = _tariff(db, name="Restoran sinov", price_per_month=0, business_type="restaurant")
    r.c.subscription_ends_at = None
    r.c.is_trial = False
    db.flush()
    res = client.login(r.admin).post("/api/billing/activate-my-trial")
    assert res.status_code == 200, res.text
    db.refresh(r.c)
    assert r.c.tariff_id == rt.id


def test_super_admin_restaurants_list(r, client, db, mk):
    cl = client.login(r.cashier)
    oid = cl.post("/api/restaurant/orders", json={"table_id": r.tables[0].id, "guests": 2}).json()["id"]
    assert oid
    mk.tenant()                                                        # do'kon ro'yxatga tushmaydi
    sa = client.login(mk.user(None, role=UserRole.super_admin))
    rows = sa.get("/api/super-admin/restaurants").json()
    me = next(x for x in rows if x["id"] == r.c.id)
    assert all(x["id"] != 0 for x in rows) and len([x for x in rows if x["id"] == r.c.id]) == 1
    assert me["format"] == "full_service" and me["branches"] == 1 and me["open_checks"] == 1
    assert me["last_activity"] is not None and me["today_checks"] == 0
    assert me["features"] == ["kds", "reservations", "delivery", "aggregators", "qr_menu"]
    assert client.login(r.admin).get("/api/super-admin/restaurants").status_code == 403


def test_migration_seed_is_conservative():
    src = _read('alembic/versions/r9_1_restaurant_tariffs.py')
    assert "ALTER TYPE" not in src                                    # prod DB foydalanuvchisi enum egasi emas
    assert "restaurant_features" in src and "WHERE business_type = 'restaurant'" in src


def test_frontend_wired_and_i18n():
    sa = _read('frontend/src/pages/admin/SuperAdmin.jsx')
    for token in ("/super-admin/restaurants", "business_type", "restaurant_features", "max_waiter_devices"):
        assert token in sa, token
    layout = _read('frontend/src/components/AdminLayout.jsx')
    assert "restFeature: 'kds'" in layout and "restFeature: 'reservations'" in layout
    tar = _read('frontend/src/pages/admin/Tariflar.jsx')
    assert "business_type" in tar
    keys = set(re.findall(r"'(restTar\.[\w.]+)'", sa + tar + layout))
    assert len(keys) > 15
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
