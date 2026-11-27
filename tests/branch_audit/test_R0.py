"""R0 — Restoran rejimi asosi: biznes turi, ro'yxatdan o'tish, avtomatik tayyorlash, menyu ajratish, Super Admin.

Qamrov:
 1. Ro'yxatdan o'tish: sukut 'retail' (eski mijoz) va hech narsa qo'shilmaydi; 'restaurant' + format bo'yicha
    oshxona ombori, sexlar, zal va stollar, kategoriyalar, sozlamalar; fast-food'da zal yo'q; noto'g'ri tur 400.
 2. Sinov tarifi biznes turiga mos tanlanadi.
 3. Restoran korxonasida yangi filial ham tayyorlanadi; do'konda yo'q.
 4. /companies/me/features biznes turini qaytaradi.
 5. /restaurant/* do'konga 403, restoranga ochiq; sozlamalar tekshiruvi; korxonalar izolyatsiyasi.
 6. Super Admin turini almashtiradi (takroriy xavfsiz, audit), do'konga qaytishda ma'lumot o'chmaydi.
 7. Frontend: ro'yxatdan o'tish formasi, sidebar ajratish, i18n kalitlari uch tilda.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R0.py -q -p no:cacheprovider
"""
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.core.limiter import limiter
from app.core.security import create_access_token
from app.models.audit_log import AuditLog
from app.models.billing import Tariff
from app.models.branch import Branch
from app.models.category import Category
from app.models.company import Company
from app.models.restaurant import Hall, KitchenStation, RestaurantTable
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.services.restaurant import (
    get_kitchen_warehouse, provision_restaurant, restaurant_settings_of, settings_for_format,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


@pytest.fixture(autouse=True)
def _no_rate_limit():
    old = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = old


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _register(client, phone, **extra):
    token = create_access_token({"type": "otp_verified", "phone": phone})
    body = {"company_name": f"Korxona {phone}", "name": "Ali", "phone": phone, "region": "Toshkent",
            "district": "Chilonzor", "password": "Parol12345", "otp_verified_token": token}
    body.update(extra)
    return client.post("/api/auth/register", json=body)


def _company_of(db, phone):
    return db.get(Company, db.query(User).filter(User.phone == phone).one().company_id)


def _paid_tariff(db, company):
    t = Tariff(name="Test tarif", max_branches=5, price_per_month=100000)
    db.add(t)
    db.flush()
    company.tariff_id = t.id
    company.subscription_ends_at = datetime.now(timezone.utc) + timedelta(days=30)
    db.flush()


def _restaurant(db, mk, fmt="full_service"):
    c = mk.company(business_type="restaurant", restaurant_settings=settings_for_format(fmt))
    b = mk.branch(c, is_main=True)
    u = mk.user(c, branch=b)
    provision_restaurant(db, c, b)
    return c, b, u


# ───────────────────────── 1. Ro'yxatdan o'tish ─────────────────────────

def test_register_default_is_retail_and_adds_nothing(db, client):
    r = _register(client, "998901110001")
    assert r.status_code == 201, r.text
    assert r.json()["business_type"] == "retail"
    c = _company_of(db, "998901110001")
    assert c.business_type == "retail" and c.restaurant_settings is None
    assert db.query(Warehouse).filter(Warehouse.company_id == c.id).count() == 1
    assert db.query(KitchenStation).filter(KitchenStation.company_id == c.id).count() == 0
    assert db.query(Hall).filter(Hall.company_id == c.id).count() == 0
    assert db.query(Category).filter(Category.company_id == c.id).count() == 0


def test_register_restaurant_full_service_provisions_everything(db, client):
    r = _register(client, "998901110002", business_type="restaurant", restaurant_format="full_service")
    assert r.status_code == 201, r.text
    assert r.json()["business_type"] == "restaurant"
    c = _company_of(db, "998901110002")
    b = db.query(Branch).filter(Branch.company_id == c.id).one()
    assert c.business_type == "restaurant"
    s = restaurant_settings_of(c)
    assert s["format"] == "full_service" and s["service_pct"] == 10 and s["deduct_stock_on"] == "paid"
    whs = {w.name: w for w in db.query(Warehouse).filter(Warehouse.company_id == c.id)}
    assert set(whs) == {"Asosiy ombor", "Oshxona"}
    assert whs["Asosiy ombor"].is_default is True and whs["Oshxona"].is_default is False
    assert get_kitchen_warehouse(db, c.id, b.id).id == whs["Oshxona"].id
    st = [s.name for s in db.query(KitchenStation).filter(KitchenStation.company_id == c.id).order_by(KitchenStation.sort_order)]
    assert st == ["Issiq sex", "Sovuq sex", "Bar"]
    hall = db.query(Hall).filter(Hall.company_id == c.id).one()
    assert hall.branch_id == b.id and hall.name == "Asosiy zal"
    assert db.query(RestaurantTable).filter(RestaurantTable.hall_id == hall.id).count() == 10
    cats = {x.name for x in db.query(Category).filter(Category.company_id == c.id)}
    assert {"Salatlar", "Ichimliklar", "Desertlar"} <= cats


def test_register_fast_food_has_no_hall_and_zero_service(db, client):
    r = _register(client, "998901110003", business_type="restaurant", restaurant_format="fast_food")
    assert r.status_code == 201, r.text
    c = _company_of(db, "998901110003")
    s = restaurant_settings_of(c)
    assert s["service_pct"] == 0 and s["table_service"] is False and s["order_number_screen"] is True
    assert db.query(Hall).filter(Hall.company_id == c.id).count() == 0
    assert db.query(KitchenStation).filter(KitchenStation.company_id == c.id).count() == 3


@pytest.mark.parametrize("extra", [{"business_type": "pharmacy"},
                                   {"business_type": "restaurant", "restaurant_format": "bar"}])
def test_register_rejects_bad_type_or_format(db, client, extra):
    phone = "998901110004"
    r = _register(client, phone, **extra)
    assert r.status_code == 400, r.text
    assert db.query(User).filter(User.phone == phone).count() == 0


# ───────────────────────── 2. Sinov tarifi ─────────────────────────

def test_trial_tariff_matches_business_type(db, client):
    retail = Tariff(name="Sinov", price_per_month=0, is_active=True, business_type="retail")
    rest = Tariff(name="Restoran sinov", price_per_month=0, is_active=True, business_type="restaurant")
    db.add_all([retail, rest])
    db.flush()
    assert _register(client, "998901110005").status_code == 201
    assert _register(client, "998901110006", business_type="restaurant").status_code == 201
    assert _company_of(db, "998901110005").tariff_id == retail.id
    assert _company_of(db, "998901110006").tariff_id == rest.id


def test_restaurant_falls_back_to_retail_trial(db, client):
    retail = Tariff(name="Sinov", price_per_month=0, is_active=True, business_type="retail")
    db.add(retail)
    db.flush()
    assert _register(client, "998901110007", business_type="restaurant").status_code == 201
    assert _company_of(db, "998901110007").tariff_id == retail.id


# ───────────────────────── 3. Yangi filial ─────────────────────────

def test_new_branch_of_restaurant_is_provisioned(db, mk, client):
    c, b, u = _restaurant(db, mk)
    _paid_tariff(db, c)
    r = client.login(u).post("/api/branches", json={"name": "Ikkinchi filial"})
    assert r.status_code in (200, 201), r.text
    b2 = db.query(Branch).filter(Branch.company_id == c.id, Branch.name == "Ikkinchi filial").one()
    # sexlar korxona darajasida: ikkinchi filialda qayta yaratilmaydi
    assert db.query(KitchenStation).filter(KitchenStation.company_id == c.id).count() == 3
    assert db.query(Hall).filter(Hall.branch_id == b2.id).count() == 1
    assert get_kitchen_warehouse(db, c.id, b2.id).name == "Oshxona"
    # kategoriyalar korxona darajasida: takrorlanmaydi
    assert db.query(Category).filter(Category.company_id == c.id, Category.name == "Salatlar").count() == 1


def test_new_branch_of_retail_gets_nothing_extra(db, mk, client):
    c = mk.company()
    b = mk.branch(c, is_main=True)
    u = mk.user(c, branch=b)
    _paid_tariff(db, c)
    r = client.login(u).post("/api/branches", json={"name": "R0 savdo filiali"})
    assert r.status_code in (200, 201), r.text
    assert db.query(KitchenStation).filter(KitchenStation.company_id == c.id).count() == 0
    assert db.query(Hall).filter(Hall.company_id == c.id).count() == 0


def test_provision_is_idempotent(db, mk):
    c, b, _ = _restaurant(db, mk)
    again = provision_restaurant(db, c, b)
    assert again == {"warehouse": False, "stations": 0, "halls": 0, "tables": 0, "categories": 0}
    assert db.query(RestaurantTable).filter(RestaurantTable.company_id == c.id).count() == 10


# ───────────────────────── 4. Features ─────────────────────────

def test_features_report_business_type(db, mk, client):
    c, b, u = _restaurant(db, mk, "cafe")
    f = client.login(u).get("/api/companies/me/features").json()
    assert f["business_type"] == "restaurant" and f["restaurant"] is True
    assert f["restaurant_settings"]["format"] == "cafe" and f["restaurant_settings"]["service_pct"] == 0
    _, _, _, u2 = mk.tenant()
    f2 = client.login(u2).get("/api/companies/me/features").json()
    assert f2["business_type"] == "retail" and f2["restaurant"] is False and f2["restaurant_settings"] == {}


# ───────────────────────── 5. /restaurant API ─────────────────────────

def test_restaurant_api_closed_for_retail(db, mk, client):
    _, _, _, u = mk.tenant()
    cl = client.login(u)
    for path in ("/api/restaurant/settings", "/api/restaurant/layout"):
        assert cl.get(path).status_code == 403
    assert cl.put("/api/restaurant/settings", json={"service_pct": 5}).status_code == 403


def test_restaurant_layout_and_isolation(db, mk, client):
    c1, b1, u1 = _restaurant(db, mk)
    c2, b2, u2 = _restaurant(db, mk)
    data = client.login(u1).get("/api/restaurant/layout").json()
    assert [s["name"] for s in data["stations"]] == ["Issiq sex", "Sovuq sex", "Bar"]
    own = {s.id for s in db.query(KitchenStation).filter(KitchenStation.company_id == c1.id)}
    assert {s["id"] for s in data["stations"]} == own
    assert len(data["halls"]) == 1 and len(data["halls"][0]["tables"]) == 10
    assert all(h["branch_id"] == b1.id for h in data["halls"])


def test_restaurant_settings_update_and_validation(db, mk, client):
    c, b, u = _restaurant(db, mk)
    cl = client.login(u)
    r = cl.put("/api/restaurant/settings", json={"service_pct": 15, "deduct_stock_on": "sent", "unknown": 1})
    assert r.status_code == 200, r.text
    assert r.json()["service_pct"] == 15 and r.json()["deduct_stock_on"] == "sent" and "unknown" not in r.json()
    db.refresh(c)
    assert restaurant_settings_of(c)["service_pct"] == 15
    assert cl.put("/api/restaurant/settings", json={"service_pct": 80}).status_code == 400
    assert cl.put("/api/restaurant/settings", json={"deduct_stock_on": "never"}).status_code == 400
    assert cl.put("/api/restaurant/settings", json={"format": "bar"}).status_code == 400


def test_restaurant_settings_update_requires_admin(db, mk, client):
    c, b, _ = _restaurant(db, mk)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    assert client.login(cashier).put("/api/restaurant/settings", json={"service_pct": 5}).status_code == 403
    assert client.login(cashier).get("/api/restaurant/settings").status_code == 200


# ───────────────────────── 6. Super Admin ─────────────────────────

def test_super_admin_switches_type_and_back(db, mk, client):
    c = mk.company()
    b1 = mk.branch(c, is_main=True)
    b2 = mk.branch(c)
    sa = mk.user(None, role=UserRole.super_admin)
    cl = client.login(sa)
    r = cl.put(f"/api/super-admin/companies/{c.id}", json={"business_type": "restaurant", "restaurant_format": "cafe"})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.business_type == "restaurant" and restaurant_settings_of(c)["format"] == "cafe"
    assert db.query(KitchenStation).filter(KitchenStation.company_id == c.id).count() == 3   # korxona darajasida
    assert db.query(Hall).filter(Hall.company_id == c.id).count() == 2
    assert db.query(AuditLog).filter(AuditLog.action == "BUSINESS_TYPE_CHANGE", AuditLog.entity_id == c.id).count() == 1
    listing = {x["id"]: x for x in cl.get("/api/super-admin/companies").json()}
    assert listing[c.id]["business_type"] == "restaurant"

    # takroriy chaqiruv hech narsani ikkilamchi yaratmaydi
    assert cl.put(f"/api/super-admin/companies/{c.id}", json={"business_type": "restaurant"}).status_code == 200
    assert db.query(KitchenStation).filter(KitchenStation.company_id == c.id).count() == 3

    # do'konga qaytish: restoran ma'lumotlari o'chmaydi, faqat yashiriladi
    assert cl.put(f"/api/super-admin/companies/{c.id}", json={"business_type": "retail"}).status_code == 200
    db.refresh(c)
    assert c.business_type == "retail"
    assert db.query(Hall).filter(Hall.company_id == c.id).count() == 2


def test_super_admin_rejects_bad_type(db, mk, client):
    c = mk.company()
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).put(f"/api/super-admin/companies/{c.id}", json={"business_type": "bar"})
    assert r.status_code == 400
    db.refresh(c)
    assert c.business_type == "retail"


def test_non_super_admin_cannot_switch(db, mk, client):
    _, _, _, u = mk.tenant()
    r = client.login(u).put(f"/api/super-admin/companies/{u.company_id}", json={"business_type": "restaurant"})
    assert r.status_code == 403


# ───────────────────────── 7. Frontend ─────────────────────────

def test_register_form_sends_business_type():
    s = _read('frontend/src/pages/RegisterCompany.jsx')
    assert "payload.business_type = form.business_type" in s
    assert "payload.restaurant_format = form.restaurant_format" in s
    assert "searchParams.get('type')" in s
    for fmt in ("full_service", "cafe", "fast_food", "canteen"):
        assert f"'{fmt}'" in s


def test_sidebar_hides_retail_only_items_for_restaurant():
    s = _read('frontend/src/components/AdminLayout.jsx')
    assert "link.hideForRestaurant && features?.restaurant" in s
    assert "group.hideForRestaurant && features?.restaurant" in s
    # ulgurji sotuv va SFA guruhi restoranda yashiriladi
    sotuv = s[s.index("key: 'sotuv'"):s.index("key: 'customers'")]
    assert sotuv.count('hideForRestaurant: true') >= 1
    sfa = s[s.index("key: 'sfa_group'"):s.index("key: 'finance_group'")]
    assert 'hideForRestaurant: true' in sfa


def test_admin_index_redirects_restaurant_to_orders():
    s = _read('frontend/src/App.jsx')
    block = s[s.index('function AdminIndex()'):s.index('function AdminIndex()') + 900]
    assert 'useCompanyFeatures' in block and "features.restaurant" in block and '"restaurant/orders"' in block


def test_super_admin_page_can_change_business_type():
    s = _read('frontend/src/pages/admin/SuperAdmin.jsx')
    assert 'business_type' in s and 'restaurant_format' in s


def test_i18n_keys_in_all_languages():
    reg = _read('frontend/src/pages/RegisterCompany.jsx') + _read('frontend/src/pages/admin/SuperAdmin.jsx')
    keys = set(re.findall(r"t\('((?:auth\.biz|auth\.restFormat|superAdmin\.biz)[\w.]*)'\)", reg))
    assert len(keys) >= 8, keys
    keys |= {f'auth.restFormat.{f}' for f in ('full_service', 'cafe', 'fast_food', 'canteen')}   # t(`auth.restFormat.${f}`)
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
