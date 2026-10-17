"""T3.14 — Kuryer va logistika: filial, olib ketish nuqtasi, qo'l kassasi.

Qamrov (qabul mezonlari):
  1  to'xtov summary'sida olib ketish filiali (pickup_*), marshrut va kuryer ilovasi, kuryer xabari;
  2  available-orders ?branch_id= filtri (boshqa korxona filiali -> 404);
  3  orders status/assign/cancel rol va filial tekshiruvi, avto-sotuvga current_user;
  4  Mir-maza push: chat'siz mijoz, mashinali kuryer, noma'lum holat chaqirmaydi, xato logga yoziladi;
  5  karta tushumi qo'l kassasidagi naqd (cash_on_hand / handover limiti) ga kirmaydi;
  6  boshqa filial kassasiga topshirish (409 / tasdiq), pending topshiriqni bekor qilish;
  7  Courier.branch_id NULL kuryer hamma filial buyurtmasini ko'radi;
  8  xodim filiali o'zgarsa qo'l kassasi filiali ham o'zgaradi.
Har joyda ikki korxona izolyatsiyasi va ijobiy yo'l tekshiriladi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T3_14.py -q -p no:cacheprovider
"""
import itertools
import json
import logging
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.routers.orders as orders_mod
import app.services.marketplace_service as mp
from app.models.courier import Courier
from app.models.customer import Customer
from app.models.delivery_route import DeliveryRoute
from app.models.moliya import CashTransfer, KassaMovement, Wallet
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.sale_delivery import SaleDelivery, SaleDeliveryStatus
from app.models.user import UserRole, UserWallet
from app.models.vehicle import Vehicle
from app.routers import logistics as L
from app.services import cash_service
from app.services.mobile_service import (
    ensure_personal_wallet, handover_cash, personal_cash_balance, receivable_wallets,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)


# ───────────────────────── yordamchilar ─────────────────────────

def _customer(db, company, **kw):
    n = next(_seq)
    c = Customer(name=f"Mijoz {n}", phone=f"90{n:07d}", company_id=company.id, **kw)
    db.add(c)
    db.flush()
    return c


def _product(db, company):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"SKU-T314-{n}", barcode=f"BC-T314-{n}", company_id=company.id,
                sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    return p


def _order(db, company, customer, branch, product, group=None, status=OrderStatus.confirmed,
           courier=None, payment_type="cash"):
    o = Order(company_id=company.id, customer_id=customer.id, branch_id=branch.id, product_id=product.id,
              quantity=1, unit_price=Decimal("1000"), total_amount=Decimal("1000"), status=status,
              order_group_id=group, payment_type=payment_type, delivery_type="delivery",
              delivery_address=f"Manzil {next(_seq)}", courier_id=courier.id if courier else None)
    db.add(o)
    db.flush()
    return o


def _sale_delivery(db, company, cashier, customer, branch, warehouse=None):
    n = next(_seq)
    s = Sale(number=f"T314-{n}", cashier_id=cashier.id, total_amount=Decimal("5000"), paid_amount=Decimal("0"),
             payment_type=PaymentType.cash, status=SaleStatus.completed, company_id=company.id,
             branch_id=branch.id if branch else None, warehouse_id=warehouse.id if warehouse else None,
             customer_id=customer.id)
    db.add(s)
    db.flush()
    d = SaleDelivery(sale_id=s.id, company_id=company.id, address="Sotuv manzili",
                     status=SaleDeliveryStatus.pending)
    db.add(d)
    db.flush()
    return s, d


def _courier(db, company, branch=None, user=None, vehicle=None, **kw):
    n = next(_seq)
    c = Courier(company_id=company.id, name=f"Kuryer {n}", phone=f"9019{n:07d}", is_active=True,
                branch_id=branch.id if branch else None, user_id=user.id if user else None,
                vehicle_id=vehicle.id if vehicle else None, **kw)
    db.add(c)
    db.flush()
    return c


def _wallet(db, company, branch=None, *, is_open=True, personal=False, name=None):
    w = Wallet(name=name or f"Kassa {next(_seq)}", type="cash", balance=Decimal("0"), company_id=company.id,
               branch_id=branch.id if branch else None, is_active=True, is_open=is_open, is_personal=personal)
    db.add(w)
    db.flush()
    return w


def _put_money(db, user, wallet, amount, ptype):
    cash_service.post_cash(db, user=user, wallet=wallet, direction="in", amount=Decimal(amount),
                           payment_type=ptype, reference_type="sale", reference_id=0,
                           description="test", with_transaction=False)
    db.flush()


@pytest.fixture
def env(mk, db):
    """A korxona (distribution yoqilgan): filiallar a1, a2, omborlar, rollar; B korxona: alohida."""
    a = mk.company("A", distribution_enabled=True)
    a1 = mk.branch(a, "Chilonzor", address="Chilonzor 5", phone="711111111")
    a2 = mk.branch(a, "Yunusobod", address="Yunusobod 7", phone="722222222")
    w1 = mk.warehouse(a, a1, "W1")
    w2 = mk.warehouse(a, a2, "W2")
    admin = mk.user(a, role=UserRole.admin)
    manager1 = mk.user(a, role=UserRole.manager, branch=a1)
    cashier1 = mk.user(a, role=UserRole.cashier, branch=a1)
    acc1 = mk.user(a, role=UserRole.accountant, branch=a1)
    b = mk.company("B", distribution_enabled=True)
    b1 = mk.branch(b, "B filial")
    bw = mk.warehouse(b, b1)
    badmin = mk.user(b, role=UserRole.admin)
    return SimpleNamespace(a=a, a1=a1, a2=a2, w1=w1, w2=w2, admin=admin, manager1=manager1,
                           cashier1=cashier1, acc1=acc1, b=b, b1=b1, bw=bw, badmin=badmin,
                           cust=_customer(db, a), prod=_product(db, a))


# ───────────────────── 1. _Stop.summary pickup maydonlari ─────────────────────

def test_summary_pickup_fields_order_and_sale(db, env):
    o1 = _order(db, env.a, env.cust, env.a1, env.prod, group="g-a1")
    o2 = _order(db, env.a, env.cust, env.a2, env.prod, group="g-a2")
    s, d = _sale_delivery(db, env.a, env.admin, env.cust, env.a2)
    stops = {"g-a1": L._Stop("g-a1", orders=[o1]), "g-a2": L._Stop("g-a2", orders=[o2]),
             f"sale-{s.id}": L._Stop(f"sale-{s.id}", delivery=d)}
    customers = L._customers_map(db, stops)
    bm = L._branches_map(db, stops)
    r1 = stops["g-a1"].summary(customers, bm)
    assert (r1["pickup_branch_id"], r1["pickup_branch_name"], r1["pickup_address"], r1["pickup_phone"]) == \
        (env.a1.id, "Chilonzor", "Chilonzor 5", "711111111")
    assert stops["g-a2"].summary(customers, bm)["pickup_branch_name"] == "Yunusobod"
    rs = stops[f"sale-{s.id}"].summary(customers, bm)
    assert rs["pickup_branch_id"] == env.a2.id and rs["pickup_address"] == "Yunusobod 7"


def test_summary_second_arg_optional_and_warehouse_fallback(db, env):
    o = _order(db, env.a, env.cust, env.a1, env.prod, group="g-x")
    st = L._Stop("g-x", orders=[o])
    r = st.summary({})  # branches berilmasa ham ishlaydi
    assert r["pickup_branch_id"] == env.a1.id and r["pickup_branch_name"] is None
    # T3.13: Order.warehouse_id bo'lsa ombor filiali ustun (ustun hali modelda bo'lmasligi mumkin)
    o.warehouse_id = env.w2.id
    bm = L._branches_map(db, [st])
    assert st.summary({}, bm)["pickup_branch_name"] == "Yunusobod"
    # sotuv: sale.branch_id bo'lmasa ombor filiali
    s, d = _sale_delivery(db, env.a, env.admin, env.cust, None, warehouse=env.w1)
    s.branch_id = None
    stp = L._Stop(f"sale-{s.id}", delivery=d)
    assert stp.summary({}, L._branches_map(db, [stp]))["pickup_branch_name"] == "Chilonzor"
    # ombor ham yo'q -> None
    s.warehouse_id = None
    assert L._Stop("k", delivery=d).pickup_branch_id(None) is None


# ───────────────────── 2. available-orders filtri ─────────────────────

def _avail_env(db, env):
    o1 = _order(db, env.a, env.cust, env.a1, env.prod, group="g-a1")
    o2 = _order(db, env.a, env.cust, env.a2, env.prod, group="g-a2")
    s1, _ = _sale_delivery(db, env.a, env.admin, env.cust, env.a1)
    s2, _ = _sale_delivery(db, env.a, env.admin, env.cust, env.a2)
    return o1, o2, s1, s2


def test_available_orders_branch_filter(client, db, env):
    _, _, s1, s2 = _avail_env(db, env)
    c = client.login(env.admin)
    keys = lambda r: {x["group_key"] for x in r.json()}  # noqa: E731
    assert keys(c.get("/api/logistics/available-orders")) == {"g-a1", "g-a2", f"sale-{s1.id}", f"sale-{s2.id}"}
    r = c.get(f"/api/logistics/available-orders?branch_id={env.a1.id}")
    assert r.status_code == 200 and keys(r) == {"g-a1", f"sale-{s1.id}"}
    assert {x["pickup_branch_id"] for x in r.json()} == {env.a1.id}
    r = c.get(f"/api/logistics/available-orders?branch_id={env.a2.id}")
    assert keys(r) == {"g-a2", f"sale-{s2.id}"}


def test_available_orders_other_company_branch_404(client, db, env):
    _avail_env(db, env)
    assert client.login(env.admin).get(f"/api/logistics/available-orders?branch_id={env.b1.id}").status_code == 404
    # begona korxona admini A korxona buyurtmalarini ko'rmaydi
    r = client.login(env.badmin).get("/api/logistics/available-orders")
    assert r.status_code == 200 and r.json() == []


def test_available_orders_manager_scoped_to_own_branch(client, db, env):
    _, _, s1, _ = _avail_env(db, env)
    c = client.login(env.manager1)  # filial a1
    r = c.get("/api/logistics/available-orders")
    assert {x["group_key"] for x in r.json()} == {"g-a1", f"sale-{s1.id}"}
    assert c.get(f"/api/logistics/available-orders?branch_id={env.a2.id}").status_code == 403
    assert c.get(f"/api/logistics/available-orders?branch_id={env.a1.id}").status_code == 200


def test_available_orders_sale_without_branch_uses_warehouse(client, db, env):
    s, _ = _sale_delivery(db, env.a, env.admin, env.cust, env.a2, warehouse=env.w2)
    s.branch_id = None
    db.flush()
    c = client.login(env.admin)
    assert f"sale-{s.id}" in {x["group_key"] for x in c.get(f"/api/logistics/available-orders?branch_id={env.a2.id}").json()}
    assert f"sale-{s.id}" not in {x["group_key"] for x in c.get(f"/api/logistics/available-orders?branch_id={env.a1.id}").json()}


# ───────────────────── 3. kuryer branch_id (CRUD) ─────────────────────

def test_courier_branch_id_company_check(client, db, env, monkeypatch):
    import app.services.tariff_guard as tg
    monkeypatch.setattr(tg, "check_courier_limit", lambda *a, **k: None)
    c = client.login(env.admin)
    r = c.post("/api/couriers", json={"name": "K1", "phone": "901234567", "branch_id": env.a1.id})
    assert r.status_code == 201, r.text
    assert r.json()["branch_id"] == env.a1.id and r.json()["branch_name"] == "Chilonzor"
    cid = r.json()["id"]
    # begona korxona filiali -> 404
    assert c.post("/api/couriers", json={"name": "K2", "phone": "901234568", "branch_id": env.b1.id}).status_code == 404
    assert c.put(f"/api/couriers/{cid}", json={"branch_id": env.b1.id}).status_code == 404
    # o'zgartirish va "barcha filial" (null)
    r = c.put(f"/api/couriers/{cid}", json={"branch_id": env.a2.id})
    assert r.status_code == 200 and r.json()["branch_name"] == "Yunusobod"
    r = c.put(f"/api/couriers/{cid}", json={"branch_id": None})
    assert r.json()["branch_id"] is None and r.json()["branch_name"] is None
    # filialsiz kuryer yaratish (eski xatti-harakat)
    assert c.post("/api/couriers", json={"name": "K3", "phone": "901234569"}).json()["branch_id"] is None
    listed = {x["id"]: x for x in c.get("/api/couriers").json()}
    assert listed[cid]["branch_id"] is None


# ───────────────────── 4. marshrut: origin_branch_id, warnings, pickup ─────────────────────

def test_create_route_origin_branch_warnings_and_pickup(client, db, env):
    _order(db, env.a, env.cust, env.a1, env.prod, group="g-a1")
    _order(db, env.a, env.cust, env.a2, env.prod, group="g-a2")
    courier = _courier(db, env.a)
    c = client.login(env.admin)
    body = {"route_date": "2030-01-01", "courier_id": courier.id, "group_keys": ["g-a1", "g-a2"],
            "origin_branch_id": env.a1.id}
    r = c.post("/api/logistics/routes", json=body)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["origin_branch_id"] == env.a1.id and j["origin_branch_name"] == "Chilonzor"
    assert len(j["warnings"]) == 1 and "g-a2" in j["warnings"][0] and "Yunusobod" in j["warnings"][0]
    by_key = {s["group_key"]: s for s in j["stops"]}
    assert by_key["g-a1"]["pickup_branch_name"] == "Chilonzor" and by_key["g-a1"]["pickup_address"] == "Chilonzor 5"
    assert by_key["g-a2"]["pickup_branch_name"] == "Yunusobod"
    # rad etilmadi: marshrut saqlangan
    assert db.query(DeliveryRoute).filter(DeliveryRoute.id == j["id"]).first().origin_branch_id == env.a1.id
    assert c.get(f"/api/logistics/routes/{j['id']}").json()["stops"][1]["pickup_branch_name"] == "Yunusobod"


def test_create_route_without_origin_no_warnings_and_foreign_origin_404(client, db, env):
    _order(db, env.a, env.cust, env.a1, env.prod, group="g-1")
    _order(db, env.a, env.cust, env.a2, env.prod, group="g-2")
    courier = _courier(db, env.a)  # filialsiz kuryer
    c = client.login(env.admin)
    bad = c.post("/api/logistics/routes", json={"route_date": "2030-01-01", "courier_id": courier.id,
                                                "group_keys": ["g-1"], "origin_branch_id": env.b1.id})
    assert bad.status_code == 404
    r = c.post("/api/logistics/routes", json={"route_date": "2030-01-01", "courier_id": courier.id,
                                              "group_keys": ["g-1", "g-2"]})
    assert r.status_code == 201 and r.json()["warnings"] == [] and r.json()["origin_branch_id"] is None


def test_create_route_warns_by_courier_branch(client, db, env):
    _order(db, env.a, env.cust, env.a2, env.prod, group="g-9")
    courier = _courier(db, env.a, branch=env.a1)
    r = client.login(env.admin).post("/api/logistics/routes", json={
        "route_date": "2030-01-01", "courier_id": courier.id, "group_keys": ["g-9"]})
    assert r.status_code == 201 and len(r.json()["warnings"]) == 1


def test_set_stop_status_passes_current_user_to_auto_sale(client, db, env, monkeypatch):
    import app.services.order_to_sale as o2s
    calls = []
    monkeypatch.setattr(o2s, "maybe_create_sale_for_delivered_group", lambda db_, o, *a: calls.append(a))
    _order(db, env.a, env.cust, env.a1, env.prod, group="g-d")
    courier = _courier(db, env.a)
    c = client.login(env.admin)
    rid = c.post("/api/logistics/routes", json={"route_date": "2030-01-01", "courier_id": courier.id,
                                                "group_keys": ["g-d"]}).json()["id"]
    assert c.post(f"/api/logistics/routes/{rid}/start").status_code == 200
    r = c.post(f"/api/logistics/routes/{rid}/stops/g-d/status", json={"status": "delivered"})
    assert r.status_code == 200, r.text
    assert calls and calls[0][0].id == env.admin.id


# ───────────────────── 5. kuryer ilovasi: pickup + eski (filialsiz) kuryer ─────────────────────

def test_mobile_courier_today(client, db, env, mk):
    cu = mk.user(env.a, role=UserRole.courier)  # filialsiz kuryer foydalanuvchi
    courier = _courier(db, env.a, user=cu)      # Courier.branch_id = NULL (eski kuryer)
    _order(db, env.a, env.cust, env.a1, env.prod, group="g-a1", status=OrderStatus.assigned, courier=courier)
    _order(db, env.a, env.cust, env.a2, env.prod, group="g-a2", status=OrderStatus.assigned, courier=courier)
    r = client.login(cu).get("/api/mobile/courier/today")
    assert r.status_code == 200, r.text
    loose = {s["group_key"]: s for s in r.json()["loose"]}
    assert set(loose) == {"g-a1", "g-a2"}  # NULL branch: hamma filial buyurtmasi
    assert loose["g-a1"]["pickup_branch_name"] == "Chilonzor" and loose["g-a1"]["pickup_address"] == "Chilonzor 5"
    assert loose["g-a2"]["pickup_branch_name"] == "Yunusobod"
    d = client.login(cu).get("/api/mobile/courier/stops/g-a2").json()
    assert d["pickup_branch_name"] == "Yunusobod" and d["pickup_phone"] == "722222222"


def test_courier_bot_my_orders_has_pickup(client, db, env, monkeypatch):
    import app.routers.courier_bot as cb
    courier = _courier(db, env.a)
    env.a.courier_bot_token = "tok"
    _order(db, env.a, env.cust, env.a1, env.prod, group="g-a1", status=OrderStatus.assigned, courier=courier)
    s, d = _sale_delivery(db, env.a, env.admin, env.cust, env.a2)
    d.courier_id, d.status = courier.id, SaleDeliveryStatus.assigned
    db.flush()
    monkeypatch.setattr(cb, "_resolve_courier_context", lambda *a, **k: (env.a, courier))
    r = client.get(f"/api/courier-bot/{env.a.id}/my-orders?u=1&t=x")
    assert r.status_code == 200, r.text
    groups = {g["group_id"]: g for g in r.json()["orders"]}
    assert groups["g-a1"]["pickup_branch_name"] == "Chilonzor" and groups["g-a1"]["pickup_address"] == "Chilonzor 5"
    assert groups[f"sale-{s.id}"]["pickup_branch_name"] == "Yunusobod"


def test_order_group_pickup_helper_and_courier_message(db, env, monkeypatch):
    o = _order(db, env.a, env.cust, env.a2, env.prod, group="g-m", status=OrderStatus.assigned)
    pk = L.order_group_pickup(db, [o])
    assert pk["pickup_branch_name"] == "Yunusobod" and pk["pickup_address"] == "Yunusobod 7"
    assert L.order_group_pickup(db, [])["pickup_branch_name"] is None
    # kuryer Telegram xabari
    import app.services.sale_helpers as sh
    sent = []
    monkeypatch.setattr(sh, "send_tg_sync", lambda token, chat, text: sent.append(text))
    env.a.courier_bot_token = "tok"
    courier = _courier(db, env.a, tg_chat_id="555")
    orders_mod._notify_courier_assigned(db, [o], courier.id)
    assert sent and "Olib ketish" in sent[0] and "Yunusobod" in sent[0] and "Yunusobod 7" in sent[0]


# ───────────────────── 6. orders.py: rol / filial / acting user ─────────────────────

def test_order_endpoints_roles(client, db, env, mk):
    _order(db, env.a, env.cust, env.a1, env.prod, group="grp-r", status=OrderStatus.confirmed)
    courier = _courier(db, env.a)
    for role in (UserRole.courier, UserRole.agent):
        u = mk.user(env.a, role=role, branch=env.a1)
        c = client.login(u)
        assert c.put("/api/orders/group/grp-r/status", json={"status": "preparing"}).status_code == 403
        assert c.put("/api/orders/group/grp-r/assign", json={"courier_id": courier.id}).status_code == 403
        assert c.delete("/api/orders/group/grp-r").status_code == 403
    # ijobiy yo'l: kassir o'z filiali buyurtmasini boshqaradi
    c = client.login(env.cashier1)
    assert c.put("/api/orders/group/grp-r/status", json={"status": "preparing"}).status_code == 200
    assert c.put("/api/orders/group/grp-r/assign", json={"courier_id": courier.id}).status_code == 200
    # begona korxona admini 404
    assert client.login(env.badmin).put("/api/orders/group/grp-r/status", json={"status": "on_way"}).status_code == 404


def test_cashier_cannot_deliver_other_branch_order(client, db, env, mk):
    o2 = _order(db, env.a, env.cust, env.a2, env.prod, group="grp-b2", status=OrderStatus.on_way)
    mgr = env.manager1
    for u in (env.cashier1, mgr):
        r = client.login(u).put("/api/orders/group/grp-b2/status", json={"status": "delivered"})
        assert r.status_code in (403, 404)  # T1.15: mavjudligini oshkor qilmaslik uchun 404
        assert o2.status == OrderStatus.on_way
    courier = _courier(db, env.a)
    assert client.login(env.cashier1).put("/api/orders/group/grp-b2/assign", json={"courier_id": courier.id}).status_code in (403, 404)
    assert client.login(env.cashier1).delete("/api/orders/group/grp-b2").status_code in (403, 404)
    # admin hamma filialni o'zgartira oladi
    assert client.login(env.admin).put("/api/orders/group/grp-b2/status", json={"status": "delivered"}).status_code == 200


def test_group_status_passes_current_user_to_auto_sale(client, db, env, monkeypatch):
    import app.services.order_to_sale as o2s
    calls = []
    monkeypatch.setattr(o2s, "maybe_create_sale_for_delivered_group", lambda db_, o, *a: calls.append(a))
    _order(db, env.a, env.cust, env.a1, env.prod, group="grp-s", status=OrderStatus.on_way)
    r = client.login(env.cashier1).put("/api/orders/group/grp-s/status", json={"status": "delivered"})
    assert r.status_code == 200
    assert len(calls) == 1 and calls[0][0].id == env.cashier1.id


# ───────────────────── 7. Mir-maza push (EDGE-43, EDGE-X18) ─────────────────────

@pytest.fixture
def mm(db, env, monkeypatch):
    """Mir-maza buyurtmasi (mijozda tg_chat_id yo'q), mashinali kuryer; httpx.patch yozib olinadi."""
    calls = []
    monkeypatch.setattr(mp, "_mirmaza_headers", lambda: {"X-Integration-Key": "k"})
    monkeypatch.setattr(mp.httpx, "patch", lambda url, **kw: calls.append((url, kw["json"])))
    veh = Vehicle(company_id=env.a.id, plate_number="01A123BC", model="Damas", fuel_type="petrol")
    db.add(veh)
    db.flush()
    courier = _courier(db, env.a, vehicle=veh)
    cust = _customer(db, env.a, tg_chat_id=None)
    o = _order(db, env.a, cust, env.a1, env.prod, group=f"mirmaza-77-c{env.a.id}", status=OrderStatus.confirmed,
               courier=courier)
    return SimpleNamespace(calls=calls, courier=courier, order=o, veh=veh)


def test_mirmaza_assigned_with_vehicle_no_chat(db, env, mm):
    orders_mod._notify_courier_assigned(db, [mm.order], mm.courier.id)
    assert len(mm.calls) == 1
    url, payload = mm.calls[0]
    assert url.endswith("/orders/77/courier")
    assert payload["deliveryStatus"] == "ASSIGNED" and payload["vehicle"] == "CAR"
    assert payload["vehicleNumber"] == "01A123BC" and payload["courierName"] == mm.courier.name


@pytest.mark.parametrize("st,expected", [(OrderStatus.on_way, "ON_THE_WAY"), (OrderStatus.delivered, "DELIVERED"),
                                         (OrderStatus.cancelled, "CANCELLED")])
def test_mirmaza_status_push_without_customer_chat(db, env, mm, st, expected):
    orders_mod._notify_customer_status(db, [mm.order], st)
    assert [p["deliveryStatus"] for _, p in mm.calls] == [expected]


@pytest.mark.parametrize("st", [OrderStatus.pending, OrderStatus.confirmed, OrderStatus.preparing])
def test_mirmaza_unknown_status_does_not_call(db, env, mm, st):
    orders_mod._notify_customer_status(db, [mm.order], st)
    mp.push_courier_status_to_mirmaza(db, mm.order.order_group_id, mm.courier.id, st.value)
    assert mm.calls == []


def test_mirmaza_not_called_for_regular_group(db, env, mm):
    o = _order(db, env.a, env.cust, env.a1, env.prod, group="plain-1", status=OrderStatus.on_way, courier=mm.courier)
    orders_mod._notify_customer_status(db, [o], OrderStatus.delivered)
    orders_mod._notify_courier_assigned(db, [o], mm.courier.id)
    assert mm.calls == []


def test_mirmaza_via_assign_endpoint_and_error_logged(client, db, env, mm, monkeypatch, caplog):
    # endpoint orqali: kuryer biriktirilganda push ketadi
    r = client.login(env.admin).put(f"/api/orders/group/{mm.order.order_group_id}/assign",
                                    json={"courier_id": mm.courier.id})
    assert r.status_code == 200
    assert "ASSIGNED" in [p["deliveryStatus"] for _, p in mm.calls]
    # xato bo'lsa logger.exception, status yangilash yiqilmaydi
    def boom(*a, **k):
        raise RuntimeError("tarmoq")
    monkeypatch.setattr(mp, "push_courier_status_to_mirmaza", boom)
    with caplog.at_level(logging.ERROR, logger=orders_mod.logger.name):
        orders_mod._notify_customer_status(db, [mm.order], OrderStatus.on_way)
    assert any("Mir-maza" in rec.getMessage() and rec.exc_info for rec in caplog.records)


# ───────────────────── 8. qo'l kassasi: karta balansga kirmaydi ─────────────────────

def test_card_does_not_count_as_cash_on_hand(client, db, env, mk):
    cu = mk.user(env.a, role=UserRole.courier, branch=env.a1)
    w = ensure_personal_wallet(db, cu)
    _put_money(db, cu, w, "700", "card")
    assert Decimal(str(w.balance)) == Decimal("700")  # Wallet.balance'ga kirgan
    assert personal_cash_balance(db, w) == Decimal("0")  # lekin qo'ldagi naqd emas
    _put_money(db, cu, w, "300", "cash")
    assert personal_cash_balance(db, w) == Decimal("300")
    j = client.login(cu).get("/api/mobile/cash").json()
    assert j["balance"] == 300.0
    # limit faqat naqd qoldig'iga qaraydi
    r = client.login(cu).post("/api/mobile/cash/handover",
                              json={"wallet_id": _wallet(db, env.a, env.a1).id, "amount": 500})
    assert r.status_code == 400


def test_agent_kpi_cash_on_hand_is_cash_only(client, db, env, mk):
    ag = mk.user(env.a, role=UserRole.agent, branch=env.a1)
    w = ensure_personal_wallet(db, ag)
    _put_money(db, ag, w, "900", "card")
    _put_money(db, ag, w, "100", "cash")
    r = client.login(ag).get("/api/mobile/agent/kpi")
    assert r.status_code == 200, r.text
    assert r.json()["cash_on_hand"] == 100.0


# ───────────────────── 9. receivable_wallets tartibi, branch_name, is_open ─────────────────────

def test_receivable_wallets_order_and_fields(client, db, env, mk):
    cu = mk.user(env.a, role=UserRole.courier, branch=env.a1)
    other = _wallet(db, env.a, env.a2, name="A-Yunusobod")
    nobranch = _wallet(db, env.a, None, name="B-Umumiy")
    own_closed = _wallet(db, env.a, env.a1, is_open=False, name="C-Chilonzor yopiq")
    own = _wallet(db, env.a, env.a1, name="D-Chilonzor")
    foreign = _wallet(db, env.b, env.b1, name="Begona")
    ensure_personal_wallet(db, cu)
    ids = [w.id for w in receivable_wallets(db, cu)]
    assert ids == [own_closed.id, own.id, nobranch.id, other.id]  # o'z filial, filialsiz, qolgan; is_open filtri yo'q
    assert foreign.id not in ids
    wallets = client.login(cu).get("/api/mobile/cash").json()["wallets"]
    byid = {w["id"]: w for w in wallets}
    assert byid[own_closed.id]["is_open"] is False and byid[own.id]["is_open"] is True
    assert byid[own.id]["branch_name"] == "Chilonzor" and byid[nobranch.id]["branch_name"] is None
    assert byid[other.id]["branch_name"] == "Yunusobod"


# ───────────────────── 10. handover: boshqa filial + bekor qilish ─────────────────────

def _courier_with_cash(db, env, mk, amount="1000"):
    cu = mk.user(env.a, role=UserRole.courier, branch=env.a1)
    w = ensure_personal_wallet(db, cu)
    _put_money(db, cu, w, amount, "cash")
    return cu, w


def test_handover_other_branch_needs_confirmation(client, db, env, mk):
    cu, w = _courier_with_cash(db, env, mk)
    other = _wallet(db, env.a, env.a2)
    own = _wallet(db, env.a, env.a1)
    nobranch = _wallet(db, env.a, None)
    c = client.login(cu)
    r = c.post("/api/mobile/cash/handover", json={"wallet_id": other.id, "amount": 100})
    assert r.status_code == 409 and r.json()["detail"] == "Boshqa filial kassasi"
    assert Decimal(str(w.balance)) == Decimal("1000")  # hech narsa chiqmadi
    r = c.post("/api/mobile/cash/handover", json={"wallet_id": other.id, "amount": 100, "confirm_other_branch": True})
    assert r.status_code == 200 and r.json()["balance"] == 900.0
    assert c.post("/api/mobile/cash/handover", json={"wallet_id": own.id, "amount": 100}).status_code == 200
    assert c.post("/api/mobile/cash/handover", json={"wallet_id": nobranch.id, "amount": 100}).status_code == 200
    # begona korxona kassasi: 404
    foreign = _wallet(db, env.b, env.b1)
    assert c.post("/api/mobile/cash/handover",
                  json={"wallet_id": foreign.id, "amount": 10, "confirm_other_branch": True}).status_code == 404


def test_handover_to_closed_wallet_stays_pending(client, db, env, mk):
    cu, w = _courier_with_cash(db, env, mk)
    closed = _wallet(db, env.a, env.a1, is_open=False)
    r = client.login(cu).post("/api/mobile/cash/handover", json={"wallet_id": closed.id, "amount": 200})
    assert r.status_code == 200 and r.json()["status"] == "pending"


def test_cancel_handover_returns_money(client, db, env, mk):
    cu, w = _courier_with_cash(db, env, mk)
    recv = _wallet(db, env.a, env.a1)
    c = client.login(cu)
    tid = c.post("/api/mobile/cash/handover", json={"wallet_id": recv.id, "amount": 400}).json()["transfer_id"]
    assert Decimal(str(w.balance)) == Decimal("600")
    r = c.post(f"/api/mobile/cash/handover/{tid}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == 1000.0 and Decimal(str(w.balance)) == Decimal("1000")
    assert db.get(CashTransfer, tid).status == "rejected"
    assert personal_cash_balance(db, w) == Decimal("1000")
    # qayta bekor qilib bo'lmaydi
    assert c.post(f"/api/mobile/cash/handover/{tid}/cancel").status_code == 400
    assert Decimal(str(w.balance)) == Decimal("1000")


def test_cancel_handover_foreign_and_nonexistent_404(client, db, env, mk):
    cu, w = _courier_with_cash(db, env, mk)
    cu2, _ = _courier_with_cash(db, env, mk)
    recv = _wallet(db, env.a, env.a1)
    tid = client.login(cu).post("/api/mobile/cash/handover", json={"wallet_id": recv.id, "amount": 50}).json()["transfer_id"]
    assert client.login(cu2).post(f"/api/mobile/cash/handover/{tid}/cancel").status_code == 404  # boshqa xodim
    assert client.login(env.badmin).post(f"/api/mobile/cash/handover/{tid}/cancel").status_code == 404  # boshqa korxona
    assert client.login(cu).post("/api/mobile/cash/handover/999999/cancel").status_code == 404
    assert db.get(CashTransfer, tid).status == "pending"


def test_cancel_completed_handover_400(client, db, env, mk):
    cu, w = _courier_with_cash(db, env, mk)
    recv = _wallet(db, env.a, env.a1)
    ct = handover_cash(db, cu, recv.id, Decimal("100"), None)
    ct.status = "completed"
    db.flush()
    assert client.login(cu).post(f"/api/mobile/cash/handover/{ct.id}/cancel").status_code == 400


# ───────────────────── 11. kassa transfer in/reject: filial tekshiruvi ─────────────────────

def _pending_to(db, env, mk, receiver):
    cu, w = _courier_with_cash(db, env, mk)
    return handover_cash(db, cu, receiver.id, Decimal("100"), None, confirm_other_branch=True), cu


def test_transfer_in_requires_receiver_branch(client, db, env, mk):
    recv_a2 = _wallet(db, env.a, env.a2)
    db.add(UserWallet(user_id=env.acc1.id, wallet_id=recv_a2.id, is_default=False, company_id=env.a.id))
    db.flush()
    ct, _cu = _pending_to(db, env, mk, recv_a2)
    r = client.login(env.acc1).post("/api/kassa/transfer/in", json={"transfer_id": ct.id})
    assert r.status_code == 403
    assert db.get(CashTransfer, ct.id).status == "pending"
    r = client.login(env.acc1).post("/api/kassa/transfer/reject", json={"transfer_id": ct.id})
    assert r.status_code == 403
    assert db.get(CashTransfer, ct.id).status == "pending"
    # admin istisno
    assert client.login(env.admin).post("/api/kassa/transfer/in", json={"transfer_id": ct.id}).status_code == 200
    assert db.get(CashTransfer, ct.id).status == "completed"


def test_transfer_in_and_reject_own_branch_ok(client, db, env, mk):
    recv = _wallet(db, env.a, env.a1)
    db.add(UserWallet(user_id=env.acc1.id, wallet_id=recv.id, is_default=False, company_id=env.a.id))
    db.flush()
    ct, cu = _pending_to(db, env, mk, recv)
    ct2, cu2 = _pending_to(db, env, mk, recv)
    c = client.login(env.acc1)
    r = c.post("/api/kassa/transfer/in", json={"transfer_id": ct.id}); assert r.status_code == 200, r.text
    assert db.get(CashTransfer, ct.id).status == "completed"
    assert Decimal(str(recv.balance)) == Decimal("100")
    w2 = db.get(Wallet, ct2.sender_wallet_id)
    before = Decimal(str(w2.balance))
    assert c.post("/api/kassa/transfer/reject", json={"transfer_id": ct2.id}).status_code == 200
    assert db.get(CashTransfer, ct2.id).status == "rejected"
    assert Decimal(str(w2.balance)) == before + Decimal("100")
    # begona korxona admini 404
    ct3, _ = _pending_to(db, env, mk, recv)
    assert client.login(env.badmin).post("/api/kassa/transfer/in", json={"transfer_id": ct3.id}).status_code == 404


# ───────────────────── 12. filial o'zgarsa qo'l kassasi filiali ham o'zgaradi ─────────────────────

def test_ensure_personal_wallet_syncs_branch(db, env, mk):
    cu = mk.user(env.a, role=UserRole.courier, branch=env.a1)
    w = ensure_personal_wallet(db, cu)
    assert w.branch_id == env.a1.id
    cu.branch_id = env.a2.id
    assert ensure_personal_wallet(db, cu).branch_id == env.a2.id


def test_update_user_branch_syncs_personal_wallet(client, db, env, mk):
    cu = mk.user(env.a, role=UserRole.courier, branch=env.a1)
    w = ensure_personal_wallet(db, cu)
    shared = _wallet(db, env.a, env.a1)
    db.add(UserWallet(user_id=cu.id, wallet_id=shared.id, is_default=False, company_id=env.a.id))
    db.flush()
    assert w.branch_id == env.a1.id
    r = client.login(env.admin).put(f"/api/users/{cu.id}", json={"branch_id": env.a2.id})
    assert r.status_code == 200, r.text
    db.refresh(w)
    assert w.branch_id == env.a2.id
    assert shared.branch_id == env.a1.id  # umumiy kassaga tegilmadi


# ───────────────────── 13. migratsiya, modellar, frontend, i18n ─────────────────────

def test_migration_and_models():
    import py_compile
    path = os.path.join(ROOT, 'alembic', 'versions', 't3_14_courier_route_branch.py')
    py_compile.compile(path, doraise=True)
    src = open(path, encoding='utf-8').read()
    assert "revision: str = 't3_14'" in src and "down_revision: Union[str, None] = 't3_13'" in src
    for frag in ("ALTER TABLE couriers ADD COLUMN IF NOT EXISTS branch_id INTEGER REFERENCES branches(id)",
                 "CREATE INDEX IF NOT EXISTS ix_couriers_branch_id ON couriers(branch_id)",
                 "ALTER TABLE delivery_routes ADD COLUMN IF NOT EXISTS origin_branch_id INTEGER REFERENCES branches(id)",
                 "DROP COLUMN IF EXISTS origin_branch_id", "DROP INDEX IF EXISTS ix_couriers_branch_id"):
        assert frag in src
    assert Courier.__table__.c.branch_id.nullable and DeliveryRoute.__table__.c.origin_branch_id.nullable
    assert not hasattr(Vehicle, "vehicle_type")


def test_pending_i18n_keys_and_frontend_wiring():
    with open(os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T3.14.json'), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"])
    for key in ("logistics.pickupBranch", "m.handoverOtherBranch", "m.handoverCancel", "courier.branch"):
        assert key in data["uz"]
    read = lambda *p: open(os.path.join(ROOT, 'frontend', 'src', *p), encoding='utf-8').read()  # noqa: E731
    assert "pickup_branch_name" in read('pages', 'admin', 'Logistics.jsx')
    assert "origin_branch_id" in read('pages', 'admin', 'Logistics.jsx')
    assert "branch_id" in read('pages', 'admin', 'Couriers.jsx')
    assert "pickup_branch_name" in read('mobile', 'courier', 'StopSheet.jsx')
