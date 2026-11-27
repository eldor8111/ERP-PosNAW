"""R5.4 — Restoran chekini qaytarish: to'liq va qisman, xizmat haqi va chegirma ulushi, kassa balansi, taom
omborga qaytmaydi, tovar faqat belgilansa qaytadi, menejer tasdig'i, takroriy qaytarish, yopilgan cheklar ro'yxati.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R5_4.py -q -p no:cacheprovider
"""
import os
from decimal import Decimal as D

import pytest

from app.models.restaurant_order import RestaurantOrder
from app.models.sale import Sale, SaleStatus
from app.services import restaurant_orders as svc
from tests.branch_audit.test_R3 import PIN
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


@pytest.fixture
def rp(db, mk):
    return RP(db, mk)


def _paid(rp, cl, *rows, discount=None):
    oid = rp.ready_check(cl, *rows)
    if discount:
        assert cl.post(f"{O}/{oid}/discount", json={"pct": discount, "reason": "aksiya"}).status_code == 200
    total = cl.get(f"{O}/{oid}").json()["total"]
    r = cl.post(f"{O}/{oid}/pay", json={"payments": [{"type": "cash", "amount": total}]})
    assert r.status_code == 200, r.text
    return oid, r.json()


def _refund(cl, oid, **body):
    body.setdefault("reason", "quality")
    return cl.post(f"{O}/{oid}/refund", json=body)


def test_full_refund_cash(rp, client, db):
    cl = client.login(rp.admin)
    oid, paid = _paid(rp, cl, {"product_id": rp.osh.id, "quantity": 2}, {"product_id": rp.cola.id})
    db.refresh(rp.wallet)
    assert rp.wallet.balance == D("121000")
    r = _refund(cl, oid)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["refund"]["amount"] == 121000 and out["refunded_amount"] == 121000 and out["status"] == "paid"
    assert all(i["refunded_qty"] == i["quantity"] for i in out["items"])
    db.refresh(rp.wallet)
    assert rp.wallet.balance == D("0")
    ret = db.get(Sale, out["refund"]["sale_id"])
    assert ret.status == SaleStatus.refunded and ret.original_sale_id == paid["sale_id"]
    assert db.get(Sale, paid["sale_id"]).status == SaleStatus.refunded
    # taom ingredientlari va qaytarish belgilanmagan tovar omborga qaytmaydi
    assert rp.qty(rp.rice, rp.kitchen) == D("9.700") and rp.qty(rp.cola, rp.main_wh) == D("49")
    assert _refund(cl, oid).status_code == 409


def test_partial_then_rest_sums_exactly(rp, client, db):
    cl = client.login(rp.admin)
    oid, paid = _paid(rp, cl, {"product_id": rp.osh.id, "quantity": 2}, {"product_id": rp.cola.id})
    osh = next(i for i in paid["items"] if i["name"] == "Osh")
    r = _refund(cl, oid, lines=[{"item_id": osh["id"], "quantity": 1}])
    assert r.status_code == 200, r.text
    first = r.json()["refund"]["amount"]
    # 50000 + xizmat 11000 * 0.454 (ulush 3 xonagacha pastga) = 54994
    assert first == 54994
    rest = _refund(cl, oid)
    assert rest.status_code == 200, rest.text
    assert round(first + rest.json()["refund"]["amount"], 2) == 121000
    assert rest.json()["refunded_amount"] == 121000
    db.refresh(rp.wallet)
    assert rp.wallet.balance == D("0")


def test_discount_share_and_goods_restock(rp, client, db):
    cl = client.login(rp.admin)
    oid, paid = _paid(rp, cl, {"product_id": rp.osh.id, "quantity": 2}, {"product_id": rp.cola.id}, discount=10)
    assert paid["total"] == 108900          # 110000 - 11000 + 10% xizmat (99000) = 108900
    cola = next(i for i in paid["items"] if i["name"] == "Cola")
    r = _refund(cl, oid, lines=[{"item_id": cola["id"], "quantity": 1, "restock": True}])
    assert r.status_code == 200, r.text
    # 10000 - chegirma ulushi 1000 + xizmat (9900) * 0.090 = 891 -> 9891
    assert r.json()["refund"]["amount"] == 9891
    assert rp.qty(rp.cola, rp.main_wh) == D("50")           # belgilangan tovar omborga qaytdi
    rest = _refund(cl, oid).json()
    assert round(r.json()["refund"]["amount"] + rest["refund"]["amount"], 2) == 108900


def test_cashier_needs_manager_pin(rp, client):
    cl = client.login(rp.cashier)
    oid, _ = _paid(rp, cl, {"product_id": rp.cola.id})
    r = _refund(cl, oid)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "APPROVAL_REQUIRED"
    r = _refund(cl, oid, approval={"user_id": rp.mgr.id, "pin": PIN}, payment_type="card")
    assert r.status_code == 200, r.text
    assert r.json()["refunds"][0]["approved_by"] == rp.mgr.id and r.json()["refunds"][0]["payment_type"] == "card"


def test_validation(rp, client):
    cl = client.login(rp.admin)
    open_oid = rp.ready_check(cl, {"product_id": rp.cola.id}, table=4)
    assert _refund(cl, open_oid).status_code == 409                   # to'lanmagan
    oid, paid = _paid(rp, cl, {"product_id": rp.cola.id, "quantity": 2})
    iid = paid["items"][0]["id"]
    assert _refund(cl, oid, reason="bad").status_code == 400
    assert _refund(cl, oid, payment_type="debt").status_code == 400
    assert _refund(cl, oid, lines=[{"item_id": iid, "quantity": 3}]).status_code == 400
    assert _refund(cl, oid, lines=[{"item_id": 999999, "quantity": 1}]).status_code == 400
    assert _refund(cl, oid, lines=[{"item_id": iid, "quantity": 1}, {"item_id": iid, "quantity": 1}]).status_code == 400


def test_closed_today_list(rp, client):
    cl = client.login(rp.admin)
    oid, _ = _paid(rp, cl, {"product_id": rp.cola.id})
    rows = cl.get(O, params={"branch_id": rp.b.id, "status": "paid", "closed_today": True}).json()
    assert [o["id"] for o in rows] == [oid]


def test_generic_return_still_blocked(rp, client):
    cl = client.login(rp.admin)
    oid, paid = _paid(rp, cl, {"product_id": rp.cola.id})
    r = cl.post("/api/sales/return", json={"items": [{"product_id": rp.cola.id, "quantity": 1}], "payment_type": "cash",
                                           "paid_amount": 1000, "warehouse_id": rp.main_wh.id,
                                           "original_sale_id": paid["sale_id"]})
    assert r.status_code == 409


def test_frontend_refund_wired():
    import re
    page = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantOrders.jsx'), encoding='utf-8').read()
    for token in ("/refund", "closed_today", "registerReturn", "restock", "refunded_qty"):
        assert token in page, token
    keys = set(re.findall(r"'(restOrd\.[\w.]+)'", page))
    for lang in ('uz', 'ru', 'en'):
        d = open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8').read()
        for k in keys | {f'restOrd.refundReason.{x}' for x in ('quality', 'guest_refused', 'mistake', 'long_wait', 'other')}:
            assert d.count(f"'{k}':") == 1, (lang, k)
