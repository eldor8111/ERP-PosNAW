"""T1.15 — Mijoz va buyurtma filiali.

Qamrov (qabul mezonlari 1-10):
  1-4  mijoz yaratish/tahrirlash/assign-branch/filtr/import;
  5-7  buyurtmalar ro'yxati filial scope'i, sahifalash, customer_id filtri, status o'tishlari;
  8    resolve_customer_branch_id zanjiri va POST /orders fallback;
  9    mijoz tarixida kassir/ombor/filial;
  10   telegram.py da o'lik funksiya yo'q.
Ikki korxona izolyatsiyasi ham tekshiriladi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T1_15.py -q -p no:cacheprovider
"""
import itertools
from decimal import Decimal

import pytest

from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.sale import PaymentType, Sale
from app.models.user import UserRole
import app.routers.orders as orders_mod
from app.routers.customers import bulk_import_customers
from app.routers.orders import ALLOWED_TRANSITIONS
from app.services.branch_helpers import default_branch_id, resolve_customer_branch_id

_seq = itertools.count(1)


# ───────────────────────── yordamchilar ─────────────────────────

def _customer(db, company, name=None, branch=None, **kw):
    n = next(_seq)
    c = Customer(name=name or f"Mijoz {n}", phone=kw.pop("phone", f"90{n:07d}"),
                 company_id=company.id, branch_id=branch.id if branch else None, **kw)
    db.add(c)
    db.flush()
    return c


def _product(db, company):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"SKU-T115-{n}", barcode=f"BC-T115-{n}", company_id=company.id,
                sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    return p


def _order(db, company, customer, branch, product, group=None, status=OrderStatus.pending, qty=1):
    o = Order(company_id=company.id, customer_id=customer.id, branch_id=branch.id,
              product_id=product.id, quantity=qty, unit_price=Decimal("1000"),
              total_amount=Decimal("1000") * qty, status=status, order_group_id=group,
              payment_type="cash")
    db.add(o)
    db.flush()
    return o


@pytest.fixture
def env(mk, db):
    """A korxona: 2 faol filial (a1, a2), ombor, rollar; B korxona: alohida."""
    a = mk.company("A")
    a1 = mk.branch(a, "Chilonzor")
    a2 = mk.branch(a, "Yunusobod")
    w1 = mk.warehouse(a, a1, "W1")
    w2 = mk.warehouse(a, a2, "W2")
    admin = mk.user(a, role=UserRole.admin)
    manager = mk.user(a, role=UserRole.manager, branch=a1)
    cashier1 = mk.user(a, role=UserRole.cashier, branch=a1)
    cashier2 = mk.user(a, role=UserRole.cashier, branch=a2)
    b, b1, bw, badmin = mk.tenant()
    prod = _product(db, a)
    return dict(a=a, a1=a1, a2=a2, w1=w1, w2=w2, admin=admin, manager=manager, cashier1=cashier1,
                cashier2=cashier2, b=b, b1=b1, bw=bw, badmin=badmin, prod=prod)


# ───────────────────── 1. POST /customers ─────────────────────

def test_create_customer_with_branch(client, env):
    c = client.login(env["admin"])
    r = c.post("/api/customers", json={"name": "Ali", "branch_id": env["a2"].id})
    assert r.status_code == 201, r.text
    assert r.json()["branch_id"] == env["a2"].id
    got = c.get("/api/customers/paginated?search=Ali").json()["items"]
    assert got[0]["branch_id"] == env["a2"].id


def test_create_customer_other_company_branch_404(client, env):
    c = client.login(env["admin"])
    r = c.post("/api/customers", json={"name": "Ali", "branch_id": env["b1"].id})
    assert r.status_code == 404


def test_create_customer_inactive_branch_400(client, env, db):
    env["a2"].is_active = False
    db.flush()
    c = client.login(env["admin"])
    r = c.post("/api/customers", json={"name": "Ali", "branch_id": env["a2"].id})
    assert r.status_code == 400


def test_create_customer_defaults_to_creator_branch(client, env):
    r = client.login(env["manager"]).post("/api/customers", json={"name": "Vali"})
    assert r.status_code == 201, r.text
    assert r.json()["branch_id"] == env["a1"].id


def test_create_customer_branchless_admin_gets_none(client, env):
    r = client.login(env["admin"]).post("/api/customers", json={"name": "Soli"})
    assert r.status_code == 201, r.text
    assert r.json()["branch_id"] is None


# ───────────────────── 2. PUT /customers ─────────────────────

def test_update_without_branch_keeps_and_null_detaches(client, env, db):
    cust = _customer(db, env["a"], branch=env["a1"])
    c = client.login(env["admin"])
    r = c.put(f"/api/customers/{cust.id}", json={"name": "Yangi ism"})   # eski POS forma
    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] == env["a1"].id
    r = c.put(f"/api/customers/{cust.id}", json={"name": "Yangi ism", "branch_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] is None
    r = c.put(f"/api/customers/{cust.id}", json={"name": "Yangi ism", "branch_id": env["a2"].id})
    assert r.json()["branch_id"] == env["a2"].id


def test_update_branch_validation_and_role(client, env, db):
    cust = _customer(db, env["a"], branch=env["a1"])
    r = client.login(env["admin"]).put(f"/api/customers/{cust.id}", json={"name": "X", "branch_id": env["b1"].id})
    assert r.status_code == 404
    # kassir filialni o'zgartira olmaydi, lekin o'zgartirmasdan yuborsa (forma) ishlaydi
    c = client.login(env["cashier1"])
    assert c.put(f"/api/customers/{cust.id}", json={"name": "X", "branch_id": env["a2"].id}).status_code == 403
    assert c.put(f"/api/customers/{cust.id}", json={"name": "X", "branch_id": env["a1"].id}).status_code == 200


# ───────────────────── 3. assign-branch ─────────────────────

def test_assign_branch_roles_and_null(client, env, db):
    cust = _customer(db, env["a"])
    url = f"/api/customers/{cust.id}/assign-branch"
    assert client.login(env["cashier1"]).put(f"{url}?branch_id={env['a1'].id}").status_code == 403
    for user in (env["admin"], env["manager"]):
        r = client.login(user).put(f"{url}?branch_id={env['a2'].id}")
        assert r.status_code == 200, r.text
        assert r.json()["branch_id"] == env["a2"].id
    db.refresh(cust)
    assert cust.branch_id == env["a2"].id
    r = client.login(env["admin"]).put(url)           # branch_id berilmasa — ajratadi
    assert r.status_code == 200 and r.json()["branch_id"] is None
    db.refresh(cust)
    assert cust.branch_id is None


def test_assign_branch_inactive_and_foreign(client, env, db):
    cust = _customer(db, env["a"])
    url = f"/api/customers/{cust.id}/assign-branch"
    c = client.login(env["admin"])
    assert c.put(f"{url}?branch_id={env['b1'].id}").status_code == 404
    env["a2"].is_active = False
    db.flush()
    assert c.put(f"{url}?branch_id={env['a2'].id}").status_code == 400
    # begona korxona admini bu mijozga tega olmaydi
    assert client.login(env["badmin"]).put(f"{url}?branch_id={env['b1'].id}").status_code == 404


# ───────────────────── 4. filtr va import ─────────────────────

def test_paginated_branch_filter(client, env, db):
    c1 = _customer(db, env["a"], "Birinchi", branch=env["a1"])
    _customer(db, env["a"], "Ikkinchi", branch=env["a2"])
    _customer(db, env["a"], "Uchinchi")
    c = client.login(env["admin"])
    items = c.get(f"/api/customers/paginated?branch_id={env['a1'].id}").json()
    assert [i["id"] for i in items["items"]] == [c1.id] and items["total"] == 1
    plain = c.get(f"/api/customers?branch_id={env['a2'].id}").json()
    assert [i["name"] for i in plain] == ["Ikkinchi"]
    assert c.get("/api/customers/paginated").json()["total"] == 3


def test_bulk_import_branch_column(db, env):
    admin = env["admin"]
    rows = [
        {"Ism": "Imp Bir", "Telefon": "901110001", "Filial": "chilonzor"},       # katta-kichik harfsiz
        {"Ism": "Imp Ikki", "Telefon": "901110002", "Filial": "Mavjud emas"},    # xato
        {"Ism": "Imp Uch", "Telefon": "901110003"},                              # filialsiz
    ]
    res = bulk_import_customers(rows=rows, allow_update=False, db=db, current_user=admin)
    assert res["created"] == 2
    assert len(res["errors"]) == 1 and "Filial topilmadi" in res["errors"][0]["error"]
    by_name = {c.name: c for c in db.query(Customer).filter(Customer.company_id == env["a"].id)}
    assert by_name["Imp Bir"].branch_id == env["a1"].id
    assert "Imp Ikki" not in by_name
    assert by_name["Imp Uch"].branch_id is None

    # mavjud mijozni yangilash: bo'sh "Filial" filialni o'zgartirmaydi, to'ldirilgani o'zgartiradi
    res = bulk_import_customers(rows=[{"Ism": "Imp Bir", "Telefon": "901110001"}], allow_update=True,
                                db=db, current_user=admin)
    assert res["updated"] == 1 and by_name["Imp Bir"].branch_id == env["a1"].id
    res = bulk_import_customers(rows=[{"Ism": "Imp Bir", "Telefon": "901110001", "Filial": "Yunusobod"}],
                                allow_update=True, db=db, current_user=admin)
    assert res["updated"] == 1 and by_name["Imp Bir"].branch_id == env["a2"].id


def test_bulk_import_branch_other_company_not_found(db, env):
    rows = [{"Ism": "Begona", "Telefon": "901119999", "Filial": env["b1"].name}]
    res = bulk_import_customers(rows=rows, allow_update=False, db=db, current_user=env["admin"])
    assert res["created"] == 0 and "Filial topilmadi" in res["errors"][0]["error"]


# ───────────────────── 9. mijoz tarixi ─────────────────────

def test_customer_history_cashier_warehouse_branch(client, env, db):
    cust = _customer(db, env["a"])
    s = Sale(number="T115-1", cashier_id=env["cashier2"].id, total_amount=Decimal("100"),
             paid_amount=Decimal("100"), payment_type=PaymentType.cash, company_id=env["a"].id,
             warehouse_id=env["w2"].id, customer_id=cust.id)
    db.add(s)
    db.flush()
    rows = client.login(env["admin"]).get(f"/api/customers/{cust.id}/history").json()
    sale_row = next(r for r in rows if r.get("sale_number") == "T115-1")
    assert sale_row["cashier"] == env["cashier2"].name
    assert sale_row["warehouse_name"] == "W2"
    assert sale_row["branch_id"] == env["a2"].id and sale_row["branch_name"] == "Yunusobod"
    # begona korxona mijoz tarixini ko'ra olmaydi
    assert client.login(env["badmin"]).get(f"/api/customers/{cust.id}/history").status_code == 404


# ───────────────────── 5, 6. buyurtmalar ro'yxati ─────────────────────

@pytest.fixture
def orders(db, env):
    a = env["a"]
    cust1 = _customer(db, a, "Mijoz1")
    cust2 = _customer(db, a, "Mijoz2")
    prod = env["prod"]
    # A1: ko'p qatorli guruh + single
    g1 = [_order(db, a, cust1, env["a1"], prod, group="grp-a1", qty=q) for q in (1, 2)]
    s1 = _order(db, a, cust1, env["a1"], prod)
    # A2: ko'p qatorli guruh + single
    g2 = [_order(db, a, cust2, env["a2"], prod, group="grp-a2", qty=q) for q in (1, 2)]
    s2 = _order(db, a, cust2, env["a2"], prod)
    # B korxona
    bc = _customer(db, env["b"], "Begona")
    bprod = _product(db, env["b"])
    bo = _order(db, env["b"], bc, env["b1"], bprod, group="grp-b")
    return dict(cust1=cust1, cust2=cust2, g1=g1, s1=s1, g2=g2, s2=s2, bo=bo)


def _group_ids(resp):
    return [g["group_id"] for g in resp.json()]


def test_list_orders_branch_scope(client, env, orders):
    r = client.login(env["cashier1"]).get("/api/orders")
    assert r.status_code == 200, r.text
    assert set(_group_ids(r)) == {"grp-a1", f"single-{orders['s1'].id}"}
    assert all(g["branch_id"] == env["a1"].id and g["branch_name"] == "Chilonzor" for g in r.json())
    assert r.headers["X-Total-Count"] == "2"
    r2 = client.login(env["cashier2"]).get("/api/orders")
    assert set(_group_ids(r2)) == {"grp-a2", f"single-{orders['s2'].id}"}
    # cashier boshqa filialni parametr bilan ham ko'ra olmaydi
    r3 = client.login(env["cashier1"]).get(f"/api/orders?branch_id={env['a2'].id}")
    assert set(_group_ids(r3)) == {"grp-a1", f"single-{orders['s1'].id}"}


def test_list_orders_admin_sees_all_and_filters(client, env, orders):
    c = client.login(env["admin"])
    r = c.get("/api/orders")
    assert len(r.json()) == 4 and r.headers["X-Total-Count"] == "4"      # begona korxona yo'q
    assert "grp-b" not in _group_ids(r)
    only2 = c.get(f"/api/orders?branch_id={env['a2'].id}")
    assert set(_group_ids(only2)) == {"grp-a2", f"single-{orders['s2'].id}"}
    g = next(x for x in r.json() if x["group_id"] == "grp-a1")
    assert len(g["items"]) == 2 and g["branch_name"] == "Chilonzor"


def test_list_orders_unassigned_staff_sees_nothing(client, env, orders, mk):
    # 2 ta faol filial bor, filialsiz kassir — hech narsa ko'rmaydi
    stray = mk.user(env["a"], role=UserRole.cashier)
    r = client.login(stray).get("/api/orders")
    assert r.status_code == 200 and r.json() == []


def test_list_orders_pagination_and_customer_filter(client, env, orders):
    c = client.login(env["admin"])
    first = c.get("/api/orders?limit=1")
    assert len(first.json()) == 1 and first.headers["X-Total-Count"] == "4"
    seen = []
    for skip in range(4):
        part = c.get(f"/api/orders?skip={skip}&limit=1").json()
        assert len(part) == 1
        seen.append(part[0]["group_id"])
    assert len(set(seen)) == 4
    assert c.get("/api/orders?skip=4&limit=1").json() == []
    assert c.get("/api/orders?limit=201").status_code == 422
    by_cust = c.get(f"/api/orders?customer_id={orders['cust1'].id}")
    assert {g["customer_id"] for g in by_cust.json()} == {orders["cust1"].id}
    assert by_cust.headers["X-Total-Count"] == "2"


def test_list_orders_company_isolation(client, env, orders):
    r = client.login(env["badmin"]).get("/api/orders")
    assert _group_ids(r) == ["grp-b"]


# ───────────────────── 5, 7. status ─────────────────────

def test_status_other_branch_group_404_own_ok(client, env, orders):
    c = client.login(env["cashier1"])
    assert c.put("/api/orders/group/grp-a2/status", json={"status": "confirmed"}).status_code == 404
    assert c.put(f"/api/orders/group/single-{orders['s2'].id}/status", json={"status": "confirmed"}).status_code == 404
    r = c.put("/api/orders/group/grp-a1/status", json={"status": "confirmed"})
    assert r.status_code == 200 and r.json()["count"] == 2
    assert all(o.status == OrderStatus.confirmed for o in orders["g1"])
    # admin hamma filialni o'zgartira oladi; begona korxona admini esa 404 oladi
    assert client.login(env["admin"]).put("/api/orders/group/grp-a2/status", json={"status": "confirmed"}).status_code == 200
    assert client.login(env["badmin"]).put("/api/orders/group/grp-a1/status", json={"status": "confirmed"}).status_code == 404


def test_status_roles(client, env, orders, mk):
    acc = mk.user(env["a"], role=UserRole.accountant, branch=env["a1"])
    assert client.login(acc).put("/api/orders/group/grp-a1/status", json={"status": "confirmed"}).status_code == 403
    # kassir yig'ish/yetkazishni qila oladi, lekin bekor qila olmaydi
    c = client.login(env["cashier1"])
    assert c.put("/api/orders/group/grp-a1/status", json={"status": "cancelled"}).status_code == 403
    assert client.login(env["manager"]).put("/api/orders/group/grp-a1/status", json={"status": "cancelled"}).status_code == 200


_ALL = list(OrderStatus)
_PAIRS = [(a, b) for a in _ALL for b in _ALL if a != b]


@pytest.mark.parametrize("old,new", _PAIRS, ids=[f"{a.value}->{b.value}" for a, b in _PAIRS])
def test_allowed_transitions_table(client, env, db, old, new):
    cust = _customer(db, env["a"])
    o = _order(db, env["a"], cust, env["a1"], env["prod"], group=f"tr-{old.value}-{new.value}", status=old)
    r = client.login(env["admin"]).put(f"/api/orders/group/{o.order_group_id}/status", json={"status": new.value})
    if new in ALLOWED_TRANSITIONS[old]:
        assert r.status_code == 200, r.text
        assert o.status == new
    else:
        assert r.status_code == 400, r.text
        assert "o'tkazib bo'lmaydi" in r.json()["detail"]
        assert o.status == old


def test_terminal_states_are_final():
    assert ALLOWED_TRANSITIONS[OrderStatus.delivered] == ()
    assert ALLOWED_TRANSITIONS[OrderStatus.cancelled] == ()
    assert set(ALLOWED_TRANSITIONS) == set(OrderStatus)


def test_status_same_state_is_idempotent(client, env, orders, monkeypatch):
    calls = []
    monkeypatch.setattr(orders_mod, "_notify_customer_status", lambda db, o, s: calls.append(s))
    c = client.login(env["admin"])
    assert c.put("/api/orders/group/grp-a1/status", json={"status": "confirmed"}).status_code == 200
    assert len(calls) == 1
    r = c.put("/api/orders/group/grp-a1/status", json={"status": "confirmed"})
    assert r.status_code == 200
    assert len(calls) == 1                          # qayta xabar yuborilmadi
    # yetkazilgan guruhni qayta yetkazilgan deb yuborish — 200 va avto-sotuv qayta ishlamaydi
    sale_calls = []
    import app.services.order_to_sale as o2s
    monkeypatch.setattr(o2s, "maybe_create_sale_for_delivered_group", lambda db, o, *a: sale_calls.append(1))
    assert c.put("/api/orders/group/grp-a1/status", json={"status": "delivered"}).status_code == 200
    assert c.put("/api/orders/group/grp-a1/status", json={"status": "delivered"}).status_code == 200
    assert len(sale_calls) == 1
    assert c.put("/api/orders/group/grp-a1/status", json={"status": "confirmed"}).status_code == 400


def test_cancel_group_branch_scope(client, env, orders):
    c = client.login(env["cashier1"])
    assert c.delete("/api/orders/group/grp-a2").status_code == 404
    assert c.delete("/api/orders/group/grp-a1").status_code == 200
    assert all(o.status == OrderStatus.cancelled for o in orders["g1"])


def test_assign_courier_other_branch_404(client, env, orders, db):
    from app.models.courier import Courier
    cour = Courier(name="K", phone="901", company_id=env["a"].id, is_active=True)
    db.add(cour)
    db.flush()
    c = client.login(env["cashier1"])
    assert c.put("/api/orders/group/grp-a2/assign", json={"courier_id": cour.id}).status_code == 404
    assert c.put("/api/orders/group/grp-a1/assign", json={"courier_id": cour.id}).status_code == 200


def test_legacy_endpoints_branch_scope(client, env, orders):
    c = client.login(env["cashier1"])
    assert c.put(f"/api/orders/{orders['s2'].id}/confirm").status_code == 404
    assert c.put(f"/api/orders/{orders['s1'].id}/confirm").status_code == 200
    assert c.delete(f"/api/orders/{orders['g2'][0].id}").status_code == 404
    pend = c.get(f"/api/orders/branch/{env['a2'].id}/pending")
    assert pend.status_code == 200 and pend.json() == []


# ───────────────────── 8. filial tanlash zanjiri ─────────────────────

def test_resolve_customer_branch_chain(db, mk, env):
    a, a1, a2 = env["a"], env["a1"], env["a2"]
    cust = _customer(db, a, branch=a2)
    assert resolve_customer_branch_id(db, cust, a.id) == a2.id                 # 1. mijoz filiali
    a2.is_active = False
    db.flush()
    assert resolve_customer_branch_id(db, cust, a.id) == a1.id                 # nofaol -> default (a1)
    assert resolve_customer_branch_id(db, cust, a.id, [env["w2"].id]) == a1.id  # nofaol ombor filiali ham o'tkazib yuboriladi
    a2.is_active = True
    cust.branch_id = None
    db.flush()
    assert resolve_customer_branch_id(db, cust, a.id, [env["w2"].id, env["w1"].id]) == a2.id   # 2. ombor filiali
    nobranch_wh = mk.warehouse(a, None, "Filialsiz")
    assert resolve_customer_branch_id(db, cust, a.id, [nobranch_wh.id, env["w1"].id]) == a1.id
    assert resolve_customer_branch_id(db, cust, a.id, [nobranch_wh.id]) == a1.id           # 3. default
    assert resolve_customer_branch_id(db, cust, a.id) == default_branch_id(db, a.id) == a1.id
    # begona korxona ombori e'tiborga olinmaydi
    assert resolve_customer_branch_id(db, cust, a.id, [env["bw"].id]) == a1.id
    # begona korxona filialidagi mijoz filiali e'tiborga olinmaydi
    cust.branch_id = env["b1"].id
    db.flush()
    assert resolve_customer_branch_id(db, cust, a.id) == a1.id


def test_resolve_customer_branch_none_when_no_active(db, mk):
    c = mk.company("Bo'sh")
    b = mk.branch(c, "Yopiq", is_active=False)
    cust = _customer(db, c, branch=b)
    assert resolve_customer_branch_id(db, cust, c.id) is None
    assert default_branch_id(db, c.id) is None


def test_post_order_fallback_branch(client, env, db):
    cust = _customer(db, env["a"])                               # filial biriktirilmagan
    c = client.login(env["admin"])
    body = {"customer_id": cust.id, "product_id": env["prod"].id, "quantity": 2}
    r = c.post("/api/orders", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["branch_id"] == env["a1"].id                 # default_branch_id
    cust.branch_id = env["a2"].id
    db.flush()
    assert c.post("/api/orders", json=body).json()["branch_id"] == env["a2"].id


def test_post_order_no_active_branch_400(client, mk, db):
    comp = mk.company("Yopiq")
    mk.branch(comp, "Yopiq filial", is_active=False)
    admin = mk.user(comp, role=UserRole.admin)
    cust = _customer(db, comp)
    prod = _product(db, comp)
    r = client.login(admin).post("/api/orders", json={"customer_id": cust.id, "product_id": prod.id, "quantity": 1})
    assert r.status_code == 400 and "Faol filial topilmadi" in r.json()["detail"]


def test_marketplace_branch_skips_inactive_customer_branch(db, mk, env):
    from app.services.marketplace_service import _resolve_mirmaza_branch_id
    a, a1, a2 = env["a"], env["a1"], env["a2"]
    cust = _customer(db, a, branch=a2)
    assert _resolve_mirmaza_branch_id(db, a.id, cust) == a2.id
    a2.is_active = False
    db.flush()
    assert _resolve_mirmaza_branch_id(db, a.id, cust) == a1.id
    # hech qachon "1" ga tushmaydi: faol filial yo'q bo'lsa None
    a1.is_active = False
    db.flush()
    assert _resolve_mirmaza_branch_id(db, a.id, cust) is None


# ───────────────────── 8. avto-sotuv ombori ─────────────────────

def test_order_to_sale_warehouse_follows_order_branch(db, env):
    from app.services.order_to_sale import _order_branch_warehouse_id
    admin, cashier1 = env["admin"], env["cashier1"]
    assert _order_branch_warehouse_id(db, admin, env["a2"].id, env["a"].id) == env["w2"].id
    assert _order_branch_warehouse_id(db, cashier1, env["a1"].id, env["a"].id) == env["w1"].id
    # boshqa filial xodimi uchun ombor bermaymiz (403 oldini olish): eski xatti-harakat
    assert _order_branch_warehouse_id(db, cashier1, env["a2"].id, env["a"].id) is None
    assert _order_branch_warehouse_id(db, admin, None, env["a"].id) is None


# ───────────────────── 10. telegram.py ─────────────────────

def test_dead_telegram_order_handler_removed():
    import app.routers.telegram as tg
    assert not hasattr(tg, "_handle_order_from_telegram")
    assert hasattr(tg, "telegram_webhook")
