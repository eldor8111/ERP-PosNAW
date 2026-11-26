"""R2 — Restoran zallari va stollari: zal/stol CRUD, zal sxemasini saqlash, filial doirasi, izolyatsiya.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R2.py -q -p no:cacheprovider
"""
import os
import re

from app.models.audit_log import AuditLog
from app.models.restaurant import Hall, RestaurantTable
from app.models.user import UserRole
from app.services.restaurant import provision_restaurant, settings_for_format

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _rest(db, mk, fmt="full_service"):
    c = mk.company(business_type="restaurant", restaurant_settings=settings_for_format(fmt))
    b = mk.branch(c, is_main=True)
    u = mk.user(c, branch=b)
    provision_restaurant(db, c, b)
    return c, b, u


def _hall_of(db, branch):
    return db.query(Hall).filter(Hall.branch_id == branch.id).first()


# ───────────────────────── zallar ─────────────────────────

def test_list_halls_with_tables(db, mk, client):
    c, b, u = _rest(db, mk)
    halls = client.login(u).get("/api/restaurant/halls").json()
    assert len(halls) == 1 and halls[0]["name"] == "Asosiy zal" and halls[0]["branch_id"] == b.id
    assert len(halls[0]["tables"]) == 10 and halls[0]["service_pct"] is None


def test_create_update_hall_and_validation(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    r = cl.post("/api/restaurant/halls", json={"branch_id": b.id, "name": "VIP", "service_pct": 15})
    assert r.status_code == 201, r.text
    vip = r.json()
    assert vip["service_pct"] == 15 and vip["sort_order"] == 1 and vip["tables"] == []
    assert cl.post("/api/restaurant/halls", json={"branch_id": b.id, "name": "vip"}).status_code == 409
    assert cl.post("/api/restaurant/halls", json={"branch_id": b.id, "name": "Terrasa", "service_pct": 80}).status_code == 400
    assert cl.post("/api/restaurant/halls", json={"name": "Terrasa"}).status_code == 400
    r = cl.put(f"/api/restaurant/halls/{vip['id']}", json={"clear_service_pct": True, "name": "VIP zal"})
    assert r.json()["service_pct"] is None and r.json()["name"] == "VIP zal"
    assert cl.put(f"/api/restaurant/halls/{vip['id']}", json={"is_active": False}).status_code == 200
    assert [h["name"] for h in cl.get("/api/restaurant/halls").json()] == ["Asosiy zal"]
    assert len(cl.get("/api/restaurant/halls", params={"include_inactive": True}).json()) == 2


def test_cashier_cannot_edit(db, mk, client):
    c, b, _ = _rest(db, mk)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    cl = client.login(cashier)
    assert cl.get("/api/restaurant/halls").status_code == 200
    assert cl.post("/api/restaurant/halls", json={"branch_id": b.id, "name": "X"}).status_code == 403
    hall = _hall_of(db, b)
    assert cl.post(f"/api/restaurant/halls/{hall.id}/tables", json={}).status_code == 403


# ───────────────────────── stollar ─────────────────────────

def test_create_table_defaults_and_free_spot(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    hall = _hall_of(db, b)
    r = cl.post(f"/api/restaurant/halls/{hall.id}/tables", json={})
    assert r.status_code == 201, r.text
    t = r.json()
    # 10 ta stol bor: nomi "11", 4 o'rin, mavjud stollar ostidan (y = 3 + 2 + 1 = 6), x = 0
    assert t["name"] == "11" and t["seats"] == 4 and t["shape"] == "rect" and (t["x"], t["y"]) == (0, 6)
    assert cl.post(f"/api/restaurant/halls/{hall.id}/tables", json={"name": "11"}).status_code == 409
    r = cl.post(f"/api/restaurant/halls/{hall.id}/tables",
                json={"name": "Divan", "seats": 8, "shape": "round", "x": 20, "y": 1, "w": 4, "h": 3})
    assert r.status_code == 201 and r.json()["shape"] == "round" and r.json()["w"] == 4


def test_table_validation(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    hall = _hall_of(db, b)
    for bad in ({"seats": 0}, {"seats": 51}, {"shape": "star"}, {"x": -1}, {"y": 201}, {"w": 0}, {"h": 21},
                {"name": " "}):
        assert cl.post(f"/api/restaurant/halls/{hall.id}/tables", json=bad).status_code == 400, bad


def test_update_and_deactivate_table(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    hall = _hall_of(db, b)
    t1, t2 = db.query(RestaurantTable).filter(RestaurantTable.hall_id == hall.id).order_by(RestaurantTable.id).limit(2).all()
    r = cl.put(f"/api/restaurant/tables/{t1.id}", json={"name": "A1", "seats": 6})
    assert r.status_code == 200 and r.json()["name"] == "A1" and r.json()["seats"] == 6
    assert cl.put(f"/api/restaurant/tables/{t2.id}", json={"name": "a1"}).status_code == 409
    assert cl.delete(f"/api/restaurant/tables/{t1.id}").status_code == 200
    db.refresh(t1)
    assert t1.is_active is False
    # nofaol stol nomini endi boshqasi olishi mumkin; nofaolni qayta yoqish to'qnashuvda rad
    assert cl.put(f"/api/restaurant/tables/{t2.id}", json={"name": "A1"}).status_code == 200
    assert cl.put(f"/api/restaurant/tables/{t1.id}", json={"is_active": True}).status_code == 409
    tables = cl.get("/api/restaurant/halls").json()[0]["tables"]
    assert t1.id not in {t["id"] for t in tables} and len(tables) == 9


def test_save_layout_bulk(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    hall = _hall_of(db, b)
    t1, t2 = db.query(RestaurantTable).filter(RestaurantTable.hall_id == hall.id).order_by(RestaurantTable.id).limit(2).all()
    r = cl.put(f"/api/restaurant/halls/{hall.id}/layout", json={"tables": [
        {"id": t1.id, "x": 10, "y": 12, "w": 3, "h": 2, "shape": "round"},
        {"id": t2.id, "x": 0, "y": 0},
    ]})
    assert r.status_code == 200, r.text
    db.refresh(t1)
    assert (t1.x, t1.y, t1.w, t1.h, t1.shape) == (10, 12, 3, 2, "round")
    assert db.query(AuditLog).filter(AuditLog.action == "HALL_LAYOUT_SAVE", AuditLog.entity_id == hall.id).count() == 1
    # noto'g'ri qiymat: hech narsa o'zgarmaydi
    assert cl.put(f"/api/restaurant/halls/{hall.id}/layout",
                  json={"tables": [{"id": t1.id, "x": 500, "y": 0}]}).status_code == 400
    assert cl.put(f"/api/restaurant/halls/{hall.id}/layout",
                  json={"tables": [{"id": t1.id, "x": 1, "y": 1}, {"id": t1.id, "x": 2, "y": 2}]}).status_code == 400


def test_layout_rejects_table_from_other_hall(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    hall = _hall_of(db, b)
    vip = cl.post("/api/restaurant/halls", json={"branch_id": b.id, "name": "VIP"}).json()
    t = cl.post(f"/api/restaurant/halls/{vip['id']}/tables", json={"name": "V1"}).json()
    r = cl.put(f"/api/restaurant/halls/{hall.id}/layout", json={"tables": [{"id": t["id"], "x": 1, "y": 1}]})
    assert r.status_code == 400


# ───────────────────────── filial doirasi va izolyatsiya ─────────────────────────

def test_branch_scope_for_manager(db, mk, client):
    c, b1, admin = _rest(db, mk)
    b2 = mk.branch(c)
    provision_restaurant(db, c, b2)
    mgr = mk.user(c, role=UserRole.manager, branch=b1)
    cl = client.login(mgr)
    halls = cl.get("/api/restaurant/halls").json()
    assert {h["branch_id"] for h in halls} == {b1.id}
    hall2 = _hall_of(db, b2)
    assert cl.post(f"/api/restaurant/halls/{hall2.id}/tables", json={}).status_code == 403
    assert cl.post("/api/restaurant/halls", json={"branch_id": b2.id, "name": "X"}).status_code == 403
    assert cl.get("/api/restaurant/halls", params={"branch_id": b2.id}).status_code == 403
    # admin ikkala filialni ko'radi
    assert {h["branch_id"] for h in client.login(admin).get("/api/restaurant/halls").json()} == {b1.id, b2.id}


def test_company_isolation_and_retail_403(db, mk, client):
    c1, b1, u1 = _rest(db, mk)
    c2, b2, u2 = _rest(db, mk)
    hall1 = _hall_of(db, b1)
    t1 = db.query(RestaurantTable).filter(RestaurantTable.hall_id == hall1.id).first()
    cl2 = client.login(u2)
    assert cl2.put(f"/api/restaurant/halls/{hall1.id}", json={"name": "X"}).status_code == 404
    assert cl2.put(f"/api/restaurant/tables/{t1.id}", json={"name": "X"}).status_code == 404
    assert cl2.post("/api/restaurant/halls", json={"branch_id": b1.id, "name": "X"}).status_code == 404
    _, _, _, retail = mk.tenant()
    assert client.login(retail).get("/api/restaurant/halls").status_code == 403


# ───────────────────────── frontend ─────────────────────────

def test_frontend_floor_page_wired():
    app_jsx = _read('frontend/src/App.jsx')
    assert "RestaurantFloor" in app_jsx and 'path="restaurant/floor"' in app_jsx
    layout = _read('frontend/src/components/AdminLayout.jsx')
    assert "path: '/admin/restaurant/floor'" in layout
    page = _read('frontend/src/pages/admin/restaurant/RestaurantFloor.jsx')
    for token in ("/restaurant/halls", "/layout", "/restaurant/tables/", "onPointerDown", "onPointerMove"):
        assert token in page, token


def test_floor_i18n_keys_in_all_languages():
    page = _read('frontend/src/pages/admin/restaurant/RestaurantFloor.jsx')
    keys = set(re.findall(r"'(restFloor\.[\w.]+)'", page)) | {'nav.restaurantFloor'}
    assert len(keys) > 20
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
