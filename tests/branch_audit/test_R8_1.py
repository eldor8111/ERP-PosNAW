"""R8.1 — Bron: vaqt kesishsa rad (bir stol), qo'shni vaqt va boshqa stol mumkin, tahrir; depozit bron paytida kassaga
kirim, chek yopilganda `deposit` qatori (kassaga qayta kirim yo'q), ortig'i qaytariladi; bekor qilishda qaytarish,
kelmasa qoladi; zal sxemasida `reserved`; eslatma (Telegram, bir marta); ruxsatlar; fiskal to'lov turi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R8_1.py -q -p no:cacheprovider
"""
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.models.customer import Customer
from app.models.moliya import KassaMovement, Transaction, Wallet
from app.models.restaurant import Reservation
from app.models.sale import SalePayment
from app.models.user import UserRole
from app.services import restaurant_orders as svc
from app.services import restaurant_reservations as rsv
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
B = "/api/restaurant/reservations"
O = "/api/restaurant/orders"


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


def _at(hours=3, minutes=0):
    d = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(hours=hours, minutes=minutes)
    return d.isoformat()


def _book(cl, rp, tables=(0,), hours=3, minutes=0, **kw):
    body = {"branch_id": rp.b.id, "table_ids": [rp.tables[i].id for i in tables], "starts_at": _at(hours, minutes),
            "guests": 4, "name": "Aziz", "phone": "+998 90 123 45 67", **kw}
    return cl.post(B, json=body)


def _wallet(db, rp):
    return D(str(db.get(Wallet, rp.wallet.id).balance or 0))


def test_overlap_rejected_adjacent_and_other_table_ok(rp, client, db):
    cl = client.login(rp.cashier)
    r1 = _book(cl, rp, hours=3)
    assert r1.status_code == 201, r1.text
    a = r1.json()
    assert a["status"] == "booked" and a["duration_min"] == 120 and a["table_names"] == [rp.tables[0].name]
    # 1 soatdan keyin shu stol: kesishadi
    r2 = _book(cl, rp, hours=4, name="Bobur")
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "TABLE_BUSY", r2.text
    assert "Aziz" in r2.json()["detail"]["message"]
    # ikki stolli bron, biri band
    assert _book(cl, rp, tables=(1, 0), hours=4).status_code == 409
    # 2 soatdan keyin (qo'shni) va boshqa stol: mumkin
    assert _book(cl, rp, hours=5, name="Bobur").status_code == 201
    assert _book(cl, rp, tables=(1,), hours=4, name="Sardor").status_code == 201
    # bo'sh stollar
    fr = cl.get(f"{B}/free-tables", params={"branch_id": rp.b.id, "starts_at": _at(4)}).json()
    assert rp.tables[0].id in fr["busy"] and rp.tables[1].id in fr["busy"] and rp.tables[2].id in fr["free"]
    # tahrir: boshqa bron vaqtiga surish rad, bo'sh vaqtga mumkin
    res = cl.put(f"{B}/{a['id']}", json={"starts_at": _at(5, 30)})
    assert res.status_code == 409
    res = cl.put(f"{B}/{a['id']}", json={"starts_at": _at(2), "guests": 6, "table_ids": [rp.tables[2].id]})
    assert res.status_code == 200, res.text
    assert res.json()["guests"] == 6 and res.json()["table_ids"] == [rp.tables[2].id]
    # kun ro'yxati
    day = cl.get(B, params={"branch_id": rp.b.id, "days": 2}).json()          # bugun va ertaga (soatdan qat'i nazar)
    assert len(day["items"]) >= 2 and len(day["tables"]) == len(rp.tables)


def test_validation_and_past_time(rp, client):
    cl = client.login(rp.cashier)
    assert _book(cl, rp, hours=-2).status_code == 400                       # o'tgan vaqt
    assert _book(cl, rp, name=" ").status_code == 400
    assert _book(cl, rp, tables=()).status_code == 400
    assert _book(cl, rp, duration_min=5).status_code == 400
    assert _book(cl, rp, phone="12").status_code == 400


def test_deposit_applied_on_payment_without_double_cash(rp, client, db):
    cl = client.login(rp.cashier)
    before = _wallet(db, rp)
    r = _book(cl, rp, hours=0, minutes=5, deposit_amount=30000, deposit_type="cash")
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["deposit_status"] == "held" and res["deposit_held"] == 30000
    assert _wallet(db, rp) == before + 30000
    km = db.query(KassaMovement).filter(KassaMovement.reference_type == "reservation_deposit").one()
    assert km.direction == "in" and km.amount == D("30000")
    # mehmon keldi: chek ochildi va bog'landi
    arr = cl.post(f"{B}/{res['id']}/arrive", json={})
    assert arr.status_code == 200, arr.text
    oid = arr.json()["order_id"]
    assert arr.json()["status"] == "arrived" and oid
    rp.add(cl, oid, {"product_id": rp.osh.id, "quantity": 2})              # 100 000 + 10% xizmat = 110 000
    assert cl.post(f"{O}/{oid}/send", json={}).status_code == 200
    order = cl.get(f"{O}/{oid}").json()
    assert order["deposit"] == 30000
    # 80 000 naqd yetadi (depozit 30 000), 100 000 berildi: qaytim 20 000
    pay = cl.post(f"{O}/{oid}/pay", json={"payments": [{"type": "cash", "amount": 100000}]})
    assert pay.status_code == 200, pay.text
    out = pay.json()
    assert out["change"] == 20000
    assert {p["type"]: p["amount"] for p in out["payments"]} == {"deposit": 30000.0, "cash": 80000.0}
    assert {p["type"] for p in out["fiscal"]["payments"]} == {"cash"}       # fiskalga depozit naqd bo'lib
    sps = {p.payment_type: p.amount for p in db.query(SalePayment).filter(SalePayment.sale_id == out["sale"]["id"])}
    assert sps == {"deposit": D("30000"), "cash": D("80000")}
    # sotuv kirimi faqat 80 000 (depozit ikkinchi marta yozilmadi)
    sale_tx = db.query(Transaction).filter(Transaction.reference_type == "sale",
                                           Transaction.reference_id == out["sale"]["id"]).all()
    assert sum(t.amount for t in sale_tx) == D("80000")
    assert _wallet(db, rp) == before + 110000
    resv = db.get(Reservation, res["id"])
    assert resv.deposit_status == "applied" and resv.deposit_applied == D("30000") and resv.closed_at is not None
    # yopilgan bron stolni band qilmaydi
    assert _book(cl, rp, hours=0, minutes=30, name="Keyingi").status_code == 201


def test_deposit_larger_than_check_returns_excess(rp, client, db):
    cl = client.login(rp.cashier)
    before = _wallet(db, rp)
    rid = _book(cl, rp, hours=0, minutes=5, deposit_amount=200000, deposit_type="card").json()["id"]
    oid = cl.post(f"{B}/{rid}/arrive", json={}).json()["order_id"]
    rp.add(cl, oid, {"product_id": rp.cola.id})                              # 10 000 + 10% = 11 000
    assert cl.post(f"{O}/{oid}/send", json={}).status_code == 200
    assert cl.post(f"{O}/{oid}/pay", json={"payments": [{"type": "cash", "amount": 5000}]}).status_code == 400
    pay = cl.post(f"{O}/{oid}/pay", json={"payments": []})
    assert pay.status_code == 200, pay.text
    assert pay.json()["change"] == 189000
    assert [p["type"] for p in pay.json()["payments"]] == ["deposit"]
    out = db.query(KassaMovement).filter(KassaMovement.reference_type == "reservation_deposit_refund").one()
    assert out.direction == "out" and out.amount == D("189000") and out.payment_type == "card"
    assert _wallet(db, rp) == before + 11000


def test_cancel_refund_and_no_show_retained(rp, client, db):
    cl = client.login(rp.cashier)
    before = _wallet(db, rp)
    rid = _book(cl, rp, deposit_amount=50000).json()["id"]
    res = cl.post(f"{B}/{rid}/cancel", json={"reason": "Rejasi o'zgardi", "refund_deposit": True})
    assert res.status_code == 200, res.text
    assert res.json()["refunded"] == 50000 and res.json()["deposit_status"] == "refunded"
    assert _wallet(db, rp) == before
    assert cl.post(f"{B}/{rid}/cancel", json={}).status_code == 409
    # kelmadi: vaqti o'tgandan keyin, depozit qoladi
    rid = _book(cl, rp, hours=0, minutes=-10, deposit_amount=40000, tables=(1,)).json()["id"]
    res = cl.post(f"{B}/{rid}/no-show")
    assert res.status_code == 200 and res.json()["deposit_status"] == "retained"
    assert _wallet(db, rp) == before + 40000
    # kelajakdagi bron uchun "kelmadi" mumkin emas
    rid2 = _book(cl, rp, hours=6, tables=(1,)).json()["id"]
    assert cl.post(f"{B}/{rid2}/no-show").status_code == 409


def test_floor_status_shows_reserved(rp, client, db):
    cl = client.login(rp.cashier)
    rid = _book(cl, rp, hours=0, minutes=30, name="Kamola", guests=6).json()["id"]
    _book(cl, rp, tables=(1,), hours=2, name="Kechki")
    st = {x["table_id"]: x for x in cl.get("/api/restaurant/tables/status", params={"branch_id": rp.b.id}).json()}
    t0, t1 = st[rp.tables[0].id], st[rp.tables[1].id]
    assert t0["status"] == "reserved" and t0["reservation"]["id"] == rid and t0["reservation"]["guests"] == 6
    assert t1["status"] == "free" and t1["reservation"]["name"] == "Kechki"     # 2 soat bor: hali bo'sh
    assert rp.tables[2].id not in st


def test_permissions(rp, client, db, mk):
    waiter = mk.user(rp.c, role=UserRole.cashier, branch=rp.b,
                     permissions={"restaurant": {"take_payment": False}})
    wc = client.login(waiter)
    assert _book(wc, rp).status_code == 201                                   # bron mumkin
    assert _book(wc, rp, tables=(1,), deposit_amount=10000).status_code == 403  # depozit emas
    whs = client.login(mk.user(rp.c, role=UserRole.warehouse, branch=rp.b))
    assert whs.get(B, params={"branch_id": rp.b.id}).status_code == 403
    other = RP(db, mk)
    rid = _book(client.login(other.cashier), other).json()["id"]
    assert client.login(rp.cashier).post(f"{B}/{rid}/cancel", json={}).status_code == 404


def test_reminder_once_by_telegram(rp, client, db, monkeypatch):
    import app.database as database
    import app.services.scheduler as scheduler
    cust = Customer(name="Aziz", phone="998901234567", company_id=rp.c.id, tg_chat_id="555")
    db.add(cust)
    rp.c.tg_bot_token = "TEST:TOKEN"
    db.flush()
    cl = client.login(rp.cashier)
    rid = _book(cl, rp, hours=1, minutes=30).json()["id"]                    # 2 soatlik oyna ichida
    late = _book(cl, rp, tables=(1,), hours=5).json()["id"]                  # hali erta
    r = db.get(Reservation, rid)
    assert r.customer_id == cust.id                                          # telefon bo'yicha bog'landi
    assert [x.id for x in rsv.due_reminders(db)] == [rid]
    sent = []

    async def fake_tg(token, chat_id, text, **kw):
        sent.append((token, chat_id, text))
        return True

    class _S:
        def __getattr__(self, k):
            return getattr(db, k)

        def close(self):
            pass

    monkeypatch.setattr(scheduler, "send_tg_msg_async", fake_tg)
    monkeypatch.setattr(database, "SessionLocal", lambda: _S())
    import asyncio
    assert asyncio.run(rsv.send_reminders()) == 1
    assert asyncio.run(rsv.send_reminders()) == 0                            # ikkinchi marta yuborilmaydi
    assert len(sent) == 1 and sent[0][1] == "555" and "4 kishilik" in sent[0][2]
    db.refresh(r)
    assert r.remind_channel == "telegram" and r.reminded_at is not None
    assert db.get(Reservation, late).reminded_at is None


def test_frontend_wired_and_i18n():
    app_jsx = _read('frontend/src/App.jsx')
    assert "RestaurantReservations" in app_jsx and 'path="restaurant/reservations"' in app_jsx
    layout = _read('frontend/src/components/AdminLayout.jsx')
    assert "path: '/admin/restaurant/reservations'" in layout
    page = _read('frontend/src/pages/admin/restaurant/RestaurantReservations.jsx')
    for token in ("/restaurant/reservations", "/free-tables", "/arrive", "/no-show", "/cancel", "TABLE_BUSY",
                  "deposit_amount"):
        assert token in page, token
    orders = _read('frontend/src/pages/admin/restaurant/RestaurantOrders.jsx')
    assert "reserved" in orders and "order.deposit" in orders
    keys = set(re.findall(r"'(restRes\.[\w.]+)'", page)) | {'nav.restaurantReservations'}
    keys |= set(re.findall(r"'(restRes\.[\w.]+)'", orders))
    assert len(keys) > 25
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
