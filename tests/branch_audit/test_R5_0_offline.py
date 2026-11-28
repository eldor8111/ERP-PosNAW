"""R5.0 — E-Code POS Restoran oflayn API: bootstrap, oflayn chekni sinxronlash (yaratish, yuborilgan taomlar
tiketlari qayta chop etilmaydi, pre-chek, to'lov asl vaqt bilan, fiskal), idempotentlik (op_id va to'lov qayta
yuborilganda), oflayn narx, stop-list rad etmaydi, mavjud chekni davom ettirish, bekor qilish, vaqt va ruxsatlar.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R5_0_offline.py -q -p no:cacheprovider
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.models.restaurant import MenuStop
from app.models.restaurant_order import KitchenTicket, RestaurantOfflineOp, RestaurantOrder
from app.models.sale import Sale
from app.models.user import UserRole
from app.services import restaurant_orders as svc
from tests.branch_audit.test_R5 import RP

B = "/api/restaurant/offline/bootstrap"
S = "/api/restaurant/offline/sync"


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


@pytest.fixture
def rp(db, mk):
    return RP(db, mk)


def _ago(minutes):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _op(rp, **kw):
    base = {"op_id": uuid.uuid4().hex, "order_uuid": uuid.uuid4().hex, "offline_no": "O-12",
            "table_id": rp.tables[0].id, "guests": 2, "opened_at": _ago(40), "items": []}
    base.update(kw)
    return base


def _sync(cl, rp, op, device="Kassa-1"):
    return cl.post(S, json={"branch_id": rp.b.id, "device": device, "op": op})


def test_bootstrap(rp, client, db):
    out = client.login(rp.cashier).get(B, params={"branch_id": rp.b.id}).json()
    assert out["branch"]["id"] == rp.b.id and out["company"]["name"] == rp.c.name
    assert out["user"]["perms"]["take_payment"] is True and "cash" in out["pay_types"]
    assert len(out["halls"][0]["tables"]) == len(rp.tables)
    menu = {m["name"]: m for m in out["menu"]}
    assert menu["Osh"]["price"] == 50000 and menu["Osh"]["station_id"] == rp.hot.id and menu["Cola"]["kind"] == "goods"
    assert "Guruch" not in menu                                          # ingredient sotilmaydi
    assert out["settings"]["service_pct"] == 10 and out["open_orders"] == [] and "unavailable" in out["stop_list"]
    # oflayn fiskal chek uchun maydonlar; GET "Xizmat haqi" mahsulotini yaratmaydi
    assert menu["Osh"]["vat_percent"] == 12 and "mxik_code" in menu["Osh"]
    from app.models.product import Product
    assert out["service_item"]["name"] and db.query(Product).filter(Product.company_id == rp.c.id,
                                                                    Product.item_kind == "service").count() == 0


def test_new_offline_check_paid_with_original_times(rp, client, db):
    cl = client.login(rp.cashier)
    op = _op(rp, items=[
        {"product_id": rp.osh.id, "quantity": 2, "unit_price": 50000, "sent_at": _ago(35), "created_at": _ago(36)},
        {"product_id": rp.cola.id, "quantity": 1, "unit_price": 10000},          # yuborilmagan: to'lovda yuboriladi
    ], precheck_at=_ago(10), payment={"payments": [{"type": "cash", "amount": 121000}], "paid_at": _ago(5),
                                      "fiscal": {"fiscal_sign": "FS-1", "fiscal_receipt_seq": "77"}})
    res = _sync(cl, rp, op)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["status"] == "paid" and out["created"] is True and out["total"] == 121000 and out["sale_id"]
    o = db.get(RestaurantOrder, out["order_id"])
    assert o.client_uuid == op["order_uuid"] and o.offline_no == "O-12" and o.table_id == rp.tables[0].id
    assert abs((o.opened_at - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() + 40 * 60) < 120
    assert abs((o.closed_at - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() + 5 * 60) < 120
    assert all(it.status == "served" for it in o.items)
    tickets = db.query(KitchenTicket).filter(KitchenTicket.order_id == o.id).all()
    assert tickets and all(t.printed_at is not None for t in tickets)    # qurilmada chop etilgan
    sale = db.get(Sale, out["sale_id"])
    assert sale.fiscal_sign == "FS-1" and str(sale.fiscal_receipt_seq) == "77"
    assert rp.qty(rp.rice, rp.kitchen) == D("9.700")                    # ingredientlar yechildi
    # takror yuborish: ikkinchi sotuv yo'q
    again = _sync(cl, rp, op).json()
    assert again["duplicate"] is True and again["order_id"] == o.id
    # boshqa op_id bilan, lekin shu chekning to'lovi: "to'lov avval yozilgan"
    op2 = {**op, "op_id": uuid.uuid4().hex, "items": []}
    again = _sync(cl, rp, op2).json()
    assert again["duplicate"] is True and again["sale_id"] == o.sale_id
    assert db.query(Sale).filter(Sale.id == out["sale_id"]).count() == 1
    assert db.query(RestaurantOfflineOp).count() == 1


def test_open_then_continue_and_pay(rp, client, db):
    cl = client.login(rp.cashier)
    uid = uuid.uuid4().hex
    r1 = _sync(cl, rp, _op(rp, order_uuid=uid, items=[{"product_id": rp.osh.id, "sent_at": _ago(30)}])).json()
    assert r1["status"] == "open"
    o = db.get(RestaurantOrder, r1["order_id"])
    assert [it.status for it in o.items] == ["sent"]
    # keyingi amal: shu oflayn chekka yana taom va to'lov
    r2 = _sync(cl, rp, _op(rp, order_uuid=uid, items=[{"product_id": rp.cola.id, "sent_at": _ago(20)}],
                           payment={"payments": [{"type": "card", "amount": 66000}], "paid_at": _ago(2)})).json()
    assert r2["order_id"] == o.id and r2["created"] is False and r2["status"] == "paid"
    # serverda ochilgan chekni oflayn davom ettirish (server_id)
    srv = rp.open(cl, table=1)
    r3 = _sync(cl, rp, _op(rp, order_uuid=None, server_id=srv["id"], table_id=None,
                           items=[{"product_id": rp.cola.id, "sent_at": _ago(3)}])).json()
    assert r3["order_id"] == srv["id"] and r3["daily_no"] == srv["daily_no"]


def test_offline_price_and_stop_list_do_not_block(rp, client, db):
    adm = client.login(rp.admin)
    adm.put(f"/api/restaurant/stop-list/{rp.osh.id}", json={"branch_id": rp.b.id, "reason": "tugadi"})
    assert db.query(MenuStop).count() == 1
    cl = client.login(rp.cashier)
    res = _sync(cl, rp, _op(rp, items=[{"product_id": rp.osh.id, "unit_price": 45000, "sent_at": _ago(10)}]))
    assert res.status_code == 200, res.text
    o = db.get(RestaurantOrder, res.json()["order_id"])
    assert o.items[0].unit_price == D("45000.00")                        # mijoz ko'rgan narx
    # nofaol bo'lib qolgan taom ham oflayn sotilgan bo'lsa yoziladi
    from app.models.product import ProductStatus
    rp.cola.status = ProductStatus.inactive
    db.flush()
    assert _sync(cl, rp, _op(rp, table_id=rp.tables[1].id, items=[{"product_id": rp.cola.id}])).status_code == 200


def test_modifier_fallback_and_cancel(rp, client, db):
    cl = client.login(rp.cashier)
    res = _sync(cl, rp, _op(rp, items=[{"product_id": rp.osh.id, "modifiers": [999999]}])).json()
    assert res["warnings"] and "qo'shimchalar" in res["warnings"][0].lower()
    # faqat yuborilmagan taomli chek bekor qilinadi
    res = _sync(cl, rp, _op(rp, table_id=rp.tables[2].id, items=[{"product_id": rp.cola.id}],
                            cancel={"reason": "guest_left"})).json()
    assert res["status"] == "cancelled"
    res = _sync(cl, rp, _op(rp, table_id=rp.tables[3].id, items=[{"product_id": rp.osh.id, "sent_at": _ago(4)}],
                            cancel={"reason": "guest_left"}))
    assert res.status_code == 409
    assert db.query(RestaurantOrder).filter(RestaurantOrder.table_id == rp.tables[3].id).count() == 0   # hech narsa yozilmadi


def test_time_limits_and_permissions(rp, client, db, mk):
    cl = client.login(rp.cashier)
    assert _sync(cl, rp, _op(rp, opened_at=_ago(60 * 80))).status_code == 400          # 72 soatdan eski
    assert _sync(cl, rp, _op(rp, opened_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())).status_code == 400
    assert _sync(cl, rp, _op(rp, op_id="short")).status_code == 422
    wh = client.login(mk.user(rp.c, role=UserRole.warehouse, branch=rp.b))
    assert wh.get(B, params={"branch_id": rp.b.id}).status_code == 403
    # to'lov ruxsati yo'q xodim
    w = mk.user(rp.c, role=UserRole.cashier, branch=rp.b, permissions={"restaurant": {"take_payment": False}})
    res = _sync(client.login(w), rp, _op(rp, items=[{"product_id": rp.cola.id}],
                                         payment={"payments": [{"type": "cash", "amount": 11000}]}))
    assert res.status_code == 403
