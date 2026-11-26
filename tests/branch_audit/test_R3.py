"""R3 — Restoran cheki: ochish, qator, oshxonaga yuborish (sex tiketlari), pre-chek va qulf, bekor qilish (sabab,
menejer PIN tasdig'i, chiqim belgisi), chegirma limiti, xizmat haqi, versiya, stol holatlari, ko'chirish, birlashtirish,
ofitsiant ruxsatlari, izolyatsiya.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R3.py -q -p no:cacheprovider
"""
import os
import re

import pytest

from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.company import Company
from app.models.restaurant import Hall, KitchenStation, RestaurantTable
from app.models.restaurant_order import KitchenTicket, RestaurantOrder
from app.models.user import UserRole
from app.services import restaurant_orders as svc
from app.services.restaurant import provision_restaurant, settings_for_format
from app.services.restaurant_menu import create_item, save_card

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"
PIN = "5831"


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(autouse=True)
def _reset_pin_fails():
    svc._PIN_FAILS.clear()
    yield
    svc._PIN_FAILS.clear()


class R:
    """Restoran: admin, kassir, menejer (PIN bilan), taomlar (Osh issiq sexda, Salat sovuq sexda), Cola (tovar)."""

    def __init__(self, db, mk, fmt="full_service"):
        self.db = db
        self.c = mk.company(business_type="restaurant", restaurant_settings=settings_for_format(fmt))
        self.b = mk.branch(self.c, is_main=True)
        provision_restaurant(db, self.c, self.b)
        self.admin = mk.user(self.c, branch=self.b)
        self.cashier = mk.user(self.c, role=UserRole.cashier, branch=self.b)
        self.mgr = mk.user(self.c, role=UserRole.manager, branch=self.b)
        svc.set_pin(self.mgr, PIN)
        st = {s.name: s for s in db.query(KitchenStation).filter(KitchenStation.company_id == self.c.id)}
        self.hot, self.cold = st["Issiq sex"], st["Sovuq sex"]
        cats = {x.name: x for x in db.query(Category).filter(Category.company_id == self.c.id)}
        cats["Salatlar"].station_id = self.cold.id
        cid = self.c.id
        self.rice = create_item(db, cid, {"name": "Guruch", "kind": "ingredient", "cost_price": 20000})
        self.osh = create_item(db, cid, {"name": "Osh", "kind": "dish", "sale_price": 50000, "station_id": self.hot.id})
        self.salad = create_item(db, cid, {"name": "Achchiq-chuchuk", "kind": "dish", "sale_price": 20000,
                                           "category_id": cats["Salatlar"].id})
        self.cola = create_item(db, cid, {"name": "Cola", "kind": "goods", "sale_price": 10000})
        save_card(db, cid, self.osh, {"items": [{"component_product_id": self.rice.id, "gross_qty": 0.15}]}, None)
        self.hall = db.query(Hall).filter(Hall.branch_id == self.b.id).one()
        self.tables = db.query(RestaurantTable).filter(RestaurantTable.hall_id == self.hall.id).order_by(RestaurantTable.id).all()
        db.flush()

    def open(self, cl, table=0, guests=2, **kw):
        body = {"table_id": self.tables[table].id, "guests": guests, **kw}
        r = cl.post(O, json=body)
        assert r.status_code == 201, r.text
        return r.json()

    def add(self, cl, oid, *rows):
        r = cl.post(f"{O}/{oid}/items", json={"items": list(rows)})
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture
def r(db, mk):
    return R(db, mk)


def _appr(r, pin=PIN):
    return {"user_id": r.mgr.id, "pin": pin}


# ───────────────────────── ochish va qatorlar ─────────────────────────

def test_open_numbers_and_snapshot(r, client):
    cl = client.login(r.cashier)
    o1 = r.open(cl, 0)
    o2 = r.open(cl, 1)
    assert (o1["daily_no"], o2["daily_no"]) == (1, 2) and o1["number"].startswith("RC")
    assert o1["waiter_id"] == r.cashier.id and o1["status"] == "open" and o1["table_name"] == "1"
    o = r.add(cl, o1["id"], {"product_id": r.osh.id, "quantity": 2, "comment": "piyozsiz"},
              {"product_id": r.cola.id, "quantity": 1})
    osh = next(i for i in o["items"] if i["name"] == "Osh")
    assert osh["status"] == "draft" and osh["unit_price"] == 50000 and osh["station_id"] == r.hot.id
    assert next(i for i in o["items"] if i["name"] == "Cola")["station_id"] is None
    # tex karta versiyasi qatorda saqlanadi
    row = r.db.query(RestaurantOrder).get(o1["id"]).items[0]
    assert row.bom_id is not None
    # 2*50000 + 10000 = 110000; xizmat 10% = 11000
    assert o["subtotal"] == 110000 and o["service_pct"] == 10 and o["service_amount"] == 11000 and o["total"] == 121000


def test_item_validation(r, client):
    cl = client.login(r.cashier)
    oid = r.open(cl)["id"]
    for bad in ({"product_id": r.rice.id}, {"product_id": 999999}, {"product_id": r.osh.id, "quantity": 0},
                {"product_id": r.osh.id, "course": 9}):
        assert cl.post(f"{O}/{oid}/items", json={"items": [bad]}).status_code == 400, bad
    r.osh.status = "inactive"
    r.db.flush()
    assert cl.post(f"{O}/{oid}/items", json={"items": [{"product_id": r.osh.id}]}).status_code == 400


def test_hall_service_override_and_takeaway(r, client):
    cl = client.login(r.admin)
    r.hall.service_pct = 15
    r.db.flush()
    o = r.add(cl, r.open(cl)["id"], {"product_id": r.cola.id, "quantity": 2})
    assert o["service_pct"] == 15 and o["service_amount"] == 3000
    t = cl.post(O, json={"order_type": "takeaway", "branch_id": r.b.id})
    assert t.status_code == 201, t.text
    t = r.add(cl, t.json()["id"], {"product_id": r.cola.id})
    assert t["service_amount"] == 0 and t["total"] == 10000 and t["table_id"] is None


def test_dine_in_requires_table(r, client):
    assert client.login(r.admin).post(O, json={"branch_id": r.b.id}).status_code == 400


def test_draft_edit_and_remove(r, client):
    cl = client.login(r.cashier)
    oid = r.open(cl)["id"]
    o = r.add(cl, oid, {"product_id": r.osh.id})
    iid = o["items"][0]["id"]
    o = cl.patch(f"{O}/{oid}/items/{iid}", json={"quantity": 3, "course": 2}).json()
    assert o["items"][0]["quantity"] == 3 and o["items"][0]["course"] == 2 and o["subtotal"] == 150000
    o = cl.post(f"{O}/{oid}/items/{iid}/cancel", json={}).json()
    assert o["items"] == [] and o["total"] == 0


# ───────────────────────── oshxonaga yuborish ─────────────────────────

def test_send_groups_tickets_by_station_and_course(r, client, db):
    cl = client.login(r.cashier)
    oid = r.open(cl)["id"]
    r.add(cl, oid, {"product_id": r.salad.id, "course": 1}, {"product_id": r.cola.id, "course": 1},
          {"product_id": r.osh.id, "course": 2})
    res = cl.post(f"{O}/{oid}/send", json={"course": 1})
    assert res.status_code == 200, res.text
    out = res.json()
    assert {t["station_name"] for t in out["tickets"]} == {"Sovuq sex", None}
    st = {i["name"]: i["status"] for i in out["items"]}
    assert st == {"Achchiq-chuchuk": "sent", "Cola": "sent", "Osh": "draft"}
    out = cl.post(f"{O}/{oid}/send", json={}).json()
    assert [t["station_name"] for t in out["tickets"]] == ["Issiq sex"]
    assert out["tickets"][0]["lines"][0]["name"] == "Osh"
    assert cl.post(f"{O}/{oid}/send", json={}).status_code == 400
    sent = next(i for i in out["items"] if i["name"] == "Osh")
    assert cl.patch(f"{O}/{oid}/items/{sent['id']}", json={"quantity": 2}).status_code == 409
    assert db.query(KitchenTicket).filter(KitchenTicket.order_id == oid).count() == 3


# ───────────────────────── bekor qilish va PIN ─────────────────────────

def _sent_osh(r, cl):
    oid = r.open(cl)["id"]
    r.add(cl, oid, {"product_id": r.osh.id})
    o = cl.post(f"{O}/{oid}/send", json={}).json()
    return oid, o["items"][0]["id"]


def test_cancel_sent_needs_reason_and_approval(r, client, db):
    cl = client.login(r.cashier)
    oid, iid = _sent_osh(r, cl)
    url = f"{O}/{oid}/items/{iid}/cancel"
    assert cl.post(url, json={"reason": "bad"}).status_code == 400
    res = cl.post(url, json={"reason": "guest_refused"})
    assert res.status_code == 403 and res.json()["detail"]["code"] == "APPROVAL_REQUIRED"
    res = cl.post(url, json={"reason": "guest_refused", "approval": _appr(r, "0000")})
    assert res.status_code == 403 and res.json()["detail"]["code"] == "APPROVAL_INVALID"
    res = cl.post(url, json={"reason": "guest_refused", "note": "kutib qoldi", "approval": _appr(r)})
    assert res.status_code == 200, res.text
    it = res.json()["items"][0]
    assert it["status"] == "cancelled" and it["write_off"] is False and it["amount"] == 0
    assert res.json()["total"] == 0
    kinds = [t.kind for t in db.query(KitchenTicket).filter(KitchenTicket.order_id == oid).order_by(KitchenTicket.id)]
    assert kinds == ["order", "cancel"]
    log = db.query(AuditLog).filter(AuditLog.action == "REST_ITEM_CANCEL", AuditLog.entity_id == oid).one()
    assert log.new_values["approved_by"] == r.mgr.id
    assert db.query(AuditLog).filter(AuditLog.action == "REST_PIN_FAIL", AuditLog.entity_id == r.mgr.id).count() == 1


def test_cancel_cooked_marks_write_off_and_served_has_no_ticket(r, client, db):
    cl = client.login(r.admin)
    oid = r.open(cl)["id"]
    r.add(cl, oid, {"product_id": r.osh.id}, {"product_id": r.salad.id})
    items = cl.post(f"{O}/{oid}/send", json={}).json()["items"]
    osh = next(i for i in items if i["name"] == "Osh")
    salad = next(i for i in items if i["name"] != "Osh")
    assert cl.post(f"{O}/{oid}/items/{osh['id']}/status", json={"status": "ready"}).status_code == 200
    assert cl.post(f"{O}/{oid}/items/{salad['id']}/status", json={"status": "served"}).status_code == 200
    before = db.query(KitchenTicket).filter(KitchenTicket.order_id == oid, KitchenTicket.kind == "cancel").count()
    out = cl.post(f"{O}/{oid}/items/{osh['id']}/cancel", json={"reason": "spoiled"}).json()   # admin: tasdiqsiz
    assert next(i for i in out["items"] if i["id"] == osh["id"])["write_off"] is True
    out = cl.post(f"{O}/{oid}/items/{salad['id']}/cancel", json={"reason": "mistake"}).json()
    assert next(i for i in out["items"] if i["id"] == salad["id"])["write_off"] is True
    after = db.query(KitchenTicket).filter(KitchenTicket.order_id == oid, KitchenTicket.kind == "cancel").count()
    assert after - before == 1     # berilgan (served) taom uchun oshxonaga tiket ketmaydi


def test_pin_lockout_after_five_fails(r, client):
    cl = client.login(r.cashier)
    oid, iid = _sent_osh(r, cl)
    url = f"{O}/{oid}/items/{iid}/cancel"
    for _ in range(5):
        assert cl.post(url, json={"reason": "mistake", "approval": _appr(r, "1111")}).status_code == 403
    assert cl.post(url, json={"reason": "mistake", "approval": _appr(r)}).status_code == 429


def test_approver_without_capability_rejected(r, client, mk):
    other = mk.user(r.c, role=UserRole.cashier, branch=r.b)
    svc.set_pin(other, "7392")
    cl = client.login(r.cashier)
    oid, iid = _sent_osh(r, cl)
    res = cl.post(f"{O}/{oid}/items/{iid}/cancel",
                  json={"reason": "mistake", "approval": {"user_id": other.id, "pin": "7392"}})
    assert res.status_code == 403 and res.json()["detail"]["code"] == "APPROVAL_INVALID"


# ───────────────────────── item holati (oshxona) ─────────────────────────

def test_item_status_flow_and_permissions(r, client):
    cl = client.login(r.cashier)
    oid, iid = _sent_osh(r, cl)
    url = f"{O}/{oid}/items/{iid}/status"
    assert cl.post(url, json={"status": "cooking"}).status_code == 403
    adm = client.login(r.admin)
    assert adm.post(url, json={"status": "cooking"}).status_code == 200
    assert adm.post(url, json={"status": "cooking"}).status_code == 409
    assert adm.post(url, json={"status": "ready"}).status_code == 200
    st = {x["table_id"]: x for x in adm.get("/api/restaurant/tables/status", params={"branch_id": r.b.id}).json()}
    assert st[r.tables[0].id]["status"] == "ready"
    assert client.login(r.cashier).post(url, json={"status": "served"}).status_code == 200


# ───────────────────────── chegirma ─────────────────────────

def test_discount_limits_and_service_after_discount(r, client, db):
    cl = client.login(r.cashier)
    oid = r.open(cl)["id"]
    r.add(cl, oid, {"product_id": r.osh.id, "quantity": 2})          # 100000
    url = f"{O}/{oid}/discount"
    assert cl.post(url, json={"pct": 10}).status_code == 400           # sabab yo'q
    res = cl.post(url, json={"pct": 10, "reason": "doimiy mijoz"})
    assert res.status_code == 403 and res.json()["detail"]["code"] == "APPROVAL_REQUIRED"
    res = cl.post(url, json={"pct": 10, "reason": "doimiy mijoz", "approval": _appr(r)})
    assert res.status_code == 200, res.text
    o = res.json()
    # 100000 - 10000 = 90000; xizmat 10% chegirmadan keyin = 9000; jami 99000
    assert o["discount_amount"] == 10000 and o["service_amount"] == 9000 and o["total"] == 99000
    assert cl.post(url, json={"amount": 200000, "reason": "x", "approval": _appr(r)}).status_code == 400
    assert cl.post(url, json={"pct": 5, "amount": 5000, "reason": "x"}).status_code == 400
    o = cl.post(url, json={"pct": 0}).json()                           # chegirmani olib tashlash: tasdiqsiz
    assert o["discount_amount"] == 0 and o["total"] == 110000
    assert db.query(AuditLog).filter(AuditLog.action == "REST_DISCOUNT", AuditLog.entity_id == oid).count() == 2


def test_discount_limit_from_custom_permissions(r, client, mk):
    senior = mk.user(r.c, role=UserRole.cashier, branch=r.b, permissions={"restaurant": {"discount_max": 15}})
    cl = client.login(senior)
    oid = r.open(cl)["id"]
    r.add(cl, oid, {"product_id": r.cola.id})
    assert cl.post(f"{O}/{oid}/discount", json={"pct": 15, "reason": "aksiya"}).status_code == 200
    assert cl.post(f"{O}/{oid}/discount", json={"pct": 20, "reason": "aksiya"}).status_code == 403


# ───────────────────────── pre-chek va qulf ─────────────────────────

def test_precheck_lock_and_unlock(r, client):
    cl = client.login(r.cashier)
    oid = r.open(cl)["id"]
    r.add(cl, oid, {"product_id": r.osh.id})
    res = cl.post(f"{O}/{oid}/precheck")
    assert res.status_code == 409 and res.json()["detail"]["code"] == "HAS_DRAFT"
    cl.post(f"{O}/{oid}/send", json={})
    o = cl.post(f"{O}/{oid}/precheck").json()
    assert o["status"] == "prechecked" and o["locked"] is True
    res = cl.post(f"{O}/{oid}/items", json={"items": [{"product_id": r.cola.id}]})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "PRECHECK_LOCKED"
    st = {x["table_id"]: x["status"] for x in cl.get("/api/restaurant/tables/status", params={"branch_id": r.b.id}).json()}
    assert st[r.tables[0].id] == "precheck"
    assert cl.post(f"{O}/{oid}/unlock", json={}).status_code == 403
    o = cl.post(f"{O}/{oid}/unlock", json={"approval": _appr(r)}).json()
    assert o["status"] == "open"
    assert cl.post(f"{O}/{oid}/items", json={"items": [{"product_id": r.cola.id}]}).status_code == 200


def test_precheck_without_lock_reopens_on_edit(r, client, db):
    s = dict(r.c.restaurant_settings)
    s["precheck_lock"] = False
    r.c.restaurant_settings = s
    db.flush()
    cl = client.login(r.cashier)
    oid = r.open(cl)["id"]
    r.add(cl, oid, {"product_id": r.cola.id})
    cl.post(f"{O}/{oid}/send", json={})
    assert cl.post(f"{O}/{oid}/precheck").json()["locked"] is False
    o = r.add(cl, oid, {"product_id": r.cola.id})
    assert o["status"] == "open"


def test_empty_check_precheck_rejected(r, client):
    cl = client.login(r.cashier)
    oid = r.open(cl)["id"]
    assert cl.post(f"{O}/{oid}/precheck").status_code == 400


# ───────────────────────── versiya ─────────────────────────

def test_version_conflict(r, client):
    cl = client.login(r.cashier)
    o = r.open(cl)
    v = o["version"]
    assert cl.post(f"{O}/{o['id']}/items?version={v}", json={"items": [{"product_id": r.cola.id}]}).status_code == 200
    res = cl.post(f"{O}/{o['id']}/items?version={v}", json={"items": [{"product_id": r.cola.id}]})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "ORDER_CHANGED"


# ───────────────────────── chekni bekor qilish ─────────────────────────

def test_cancel_order(r, client):
    cl = client.login(r.cashier)
    empty = r.open(cl, 2)
    assert cl.post(f"{O}/{empty['id']}/cancel", json={}).json()["status"] == "cancelled"
    oid, _ = _sent_osh(r, cl)
    assert cl.post(f"{O}/{oid}/cancel", json={"reason": "guest_refused"}).status_code == 403
    o = cl.post(f"{O}/{oid}/cancel", json={"reason": "guest_refused", "approval": _appr(r)}).json()
    assert o["status"] == "cancelled" and all(i["status"] == "cancelled" for i in o["items"])
    assert cl.post(f"{O}/{oid}/items", json={"items": [{"product_id": r.cola.id}]}).status_code == 409


# ───────────────────────── ko'chirish, birlashtirish, xodim ─────────────────────────

def test_move_and_table_status(r, client, mk):
    cl = client.login(r.cashier)
    o = r.open(cl, 0)
    st = {x["table_id"]: x for x in cl.get("/api/restaurant/tables/status", params={"branch_id": r.b.id}).json()}
    assert st[r.tables[0].id]["status"] == "busy" and st[r.tables[0].id]["orders"][0]["mine"] is True
    o = cl.post(f"{O}/{o['id']}/move", json={"table_id": r.tables[5].id}).json()
    assert o["table_id"] == r.tables[5].id
    st = {x["table_id"] for x in cl.get("/api/restaurant/tables/status", params={"branch_id": r.b.id}).json()}
    assert st == {r.tables[5].id}
    b2 = mk.branch(r.c)
    provision_restaurant(r.db, r.c, b2)
    hall2 = r.db.query(Hall).filter(Hall.branch_id == b2.id).one()
    t2 = r.db.query(RestaurantTable).filter(RestaurantTable.hall_id == hall2.id).first()
    assert cl.post(f"{O}/{o['id']}/move", json={"table_id": t2.id}).status_code == 400


def test_merge_orders(r, client):
    cl = client.login(r.cashier)
    a = r.open(cl, 0, guests=2)
    b = r.open(cl, 1, guests=3)
    r.add(cl, a["id"], {"product_id": r.cola.id})
    r.add(cl, b["id"], {"product_id": r.osh.id})
    o = cl.post(f"{O}/{a['id']}/merge", json={"source_order_id": b["id"]}).json()
    assert o["guests"] == 5 and {i["name"] for i in o["items"]} == {"Cola", "Osh"} and o["subtotal"] == 60000
    src = cl.get(f"{O}/{b['id']}").json()
    assert src["status"] == "cancelled" and src["merged_into_id"] == a["id"] and src["items"] == []
    c = r.open(cl, 2)
    r.add(cl, c["id"], {"product_id": r.cola.id})
    cl.post(f"{O}/{c['id']}/send", json={})
    cl.post(f"{O}/{c['id']}/precheck")
    assert cl.post(f"{O}/{a['id']}/merge", json={"source_order_id": c["id"]}).status_code == 409
    assert cl.post(f"{O}/{a['id']}/merge", json={"source_order_id": a["id"]}).status_code == 400


def test_waiter_scope_and_transfer(r, client, mk, db):
    waiter = mk.user(r.c, role=UserRole.cashier, branch=r.b,
                     permissions={"restaurant": {"waiter": True, "all_tables": False, "move_table": False}})
    other = r.open(client.login(r.cashier), 0)
    wcl = client.login(waiter)
    mine = r.open(wcl, 1)
    assert wcl.get(f"{O}/{other['id']}").status_code == 403
    assert [o["id"] for o in wcl.get(O, params={"branch_id": r.b.id}).json()] == [mine["id"]]
    assert wcl.post(f"{O}/{mine['id']}/move", json={"table_id": r.tables[3].id}).status_code == 403
    # sozlama: ofitsiant hamma stollarni ko'radi
    s = dict(r.c.restaurant_settings)
    s["waiter_sees_all_tables"] = True
    r.c.restaurant_settings = s
    db.flush()
    assert wcl.get(f"{O}/{other['id']}").status_code == 200
    # admin chekni ofitsiantga o'tkazadi
    o = client.login(r.admin).post(f"{O}/{other['id']}/waiter", json={"waiter_id": waiter.id}).json()
    assert o["waiter_id"] == waiter.id


# ───────────────────────── PIN, tasdiqlovchilar, izolyatsiya ─────────────────────────

def test_set_pin_and_approvers(r, client, mk):
    r.cashier.hashed_password = hash_password("Parol123")
    r.db.flush()
    cl = client.login(r.cashier)
    assert cl.put("/api/restaurant/me/pin", json={"pin": "4826", "password": "xato"}).status_code == 403
    assert cl.put("/api/restaurant/me/pin", json={"pin": "1111", "password": "Parol123"}).status_code == 400
    assert cl.put("/api/restaurant/me/pin", json={"pin": "12a4", "password": "Parol123"}).status_code == 400
    assert cl.put("/api/restaurant/me/pin", json={"pin": "4826", "password": "Parol123"}).status_code == 200
    assert cl.get("/api/restaurant/me/perms").json()["has_pin"] is True
    assert cl.put(f"/api/restaurant/staff/{r.mgr.id}/pin", json={"pin": "9157"}).status_code == 403
    assert client.login(r.admin).put(f"/api/restaurant/staff/{r.mgr.id}/pin", json={"pin": "9157"}).status_code == 200
    names = {a["id"] for a in cl.get("/api/restaurant/approvers", params={"capability": "cancel_sent"}).json()}
    assert names == {r.mgr.id}                      # kassirda PIN bor, lekin ruxsat yo'q
    foreign = R(r.db, mk)
    assert client.login(r.admin).put(f"/api/restaurant/staff/{foreign.mgr.id}/pin", json={"pin": "9157"}).status_code == 404


def test_isolation_and_retail(r, client, mk):
    cl = client.login(r.cashier)
    oid = r.open(cl)["id"]
    other = R(r.db, mk)
    ocl = client.login(other.admin)
    assert ocl.get(f"{O}/{oid}").status_code == 404
    assert ocl.post(O, json={"table_id": r.tables[0].id}).status_code == 404
    cl = client.login(r.cashier)
    res = cl.post(f"{O}/{oid}/items", json={"items": [{"product_id": other.osh.id}]})
    assert res.status_code == 400
    _, _, _, retail = mk.tenant()
    assert client.login(retail).get(O).status_code == 403


def test_warehouse_role_has_no_orders(r, client, mk):
    wh = mk.user(r.c, role=UserRole.warehouse, branch=r.b)
    assert client.login(wh).post(O, json={"table_id": r.tables[0].id}).status_code == 403


# ───────────────────────── frontend ─────────────────────────

def test_frontend_orders_page_wired():
    app_jsx = _read('frontend/src/App.jsx')
    assert "RestaurantOrders" in app_jsx and 'path="restaurant/orders"' in app_jsx
    assert "path: '/admin/restaurant/orders'" in _read('frontend/src/components/AdminLayout.jsx')
    page = _read('frontend/src/pages/admin/restaurant/RestaurantOrders.jsx')
    for token in ("/restaurant/tables/status", "/send", "/precheck", "/unlock", "/discount", "/cancel", "/move",
                  "/merge", "APPROVAL_REQUIRED", "ORDER_CHANGED", "/restaurant/approvers", "version"):
        assert token in page, token


def test_orders_i18n_keys_in_all_languages():
    page = _read('frontend/src/pages/admin/restaurant/RestaurantOrders.jsx')
    keys = set(re.findall(r"'(restOrd\.[\w.]+)'", page)) | {'nav.restaurantOrders'}
    keys |= {f'restOrd.reason.{k}' for k in svc.CANCEL_REASONS}
    keys |= {f'restOrd.item.{k}' for k in ('draft', 'sent', 'cooking', 'ready', 'served', 'cancelled')}
    assert len(keys) > 40
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
