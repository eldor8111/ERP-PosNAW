"""T3.13 — Telegram Mini App va mijoz bot filial tanlovi.

Qabul mezonlari: 1 (filial qoldig'i, qoldiqsiz buyurtma rad etiladi), 2 (orders.branch_id/warehouse_id,
buyurtma ro'yxatida filial), 3 (avto-sotuv Order.warehouse_id dan), 4 (yangi bot mijozi standart filial),
5 (begona korxona filiali 400), 6 (/dokon Mini App tugmasi, o'lik kod yo'q), 7 ("dokon" so'zi xabarlarda yo'q),
korxonalararo izolyatsiya.
"""
import asyncio
import itertools
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import event

from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.user import UserRole
from app.models.warehouse import WarehouseType
from app.services import shop_branch
from app.services.shop_branch import (
    BRANCH_NOT_PICKUP, NO_SHOP_BRANCH, default_branch_for_new_customer, list_pickup_branches,
    pick_fulfillment_warehouse, resolve_order_branch, shop_warehouses,
)

_n = itertools.count(1)
BOT_TOKEN = "123456:T313-bot-token"


def _product(db, company, **kw):
    n = next(_n)
    p = Product(name=kw.pop("name", f"Tovar T313-{n}"), sku=f"T313-{n}", barcode=f"BC313-{n:06d}",
                company_id=company.id, cost_price=Decimal("500"), sale_price=Decimal("1000"), **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty):
    sl = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=Decimal(qty))
    db.add(sl)
    db.flush()
    return sl


def _customer(db, company, chat_id=None, branch=None):
    n = next(_n)
    c = Customer(name=f"Mijoz T313-{n}", phone=f"99890{n:07d}", company_id=company.id,
                 tg_chat_id=chat_id, branch_id=branch.id if branch else None)
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def shop(db, mk):
    """Bitta korxona: 2 filial (Chilonzor, Yunusobod), har birida shop ombori; Mini App mijozi."""
    c = mk.company()
    c.tg_bot_token = BOT_TOKEN
    ch = mk.branch(c, "Chilonzor", address="Chilonzor 1", phone="901111111")
    yu = mk.branch(c, "Yunusobod", address="Yunusobod 2", phone="902222222")
    w_ch = mk.warehouse(c, ch, type=WarehouseType.shop, name="Chilonzor do'kon")
    w_yu = mk.warehouse(c, yu, type=WarehouseType.shop, name="Yunusobod do'kon")
    cust = _customer(db, c, chat_id="777000")
    prod = _product(db, c)
    _stock(db, prod, w_ch, 0)
    _stock(db, prod, w_yu, 10)
    db.flush()
    return SimpleNamespace(c=c, ch=ch, yu=yu, w_ch=w_ch, w_yu=w_yu, cust=cust, prod=prod)


def _auth(company, customer):
    from app.routers.telegram import _generate_shop_token
    return {"u": customer.tg_chat_id, "t": _generate_shop_token(customer.tg_chat_id, company.tg_bot_token)}


def _order_body(prod, qty=1, **kw):
    return {"items": [{"product_id": prod.id, "quantity": qty}], "delivery_type": "pickup", **kw}


# ───────────────────── resolve_order_branch jadvali ─────────────────────

def test_resolve_requested_branch_wins(db, shop):
    cust = shop.cust
    cust.branch_id = shop.yu.id
    shop.c.shop_default_branch_id = shop.yu.id
    db.flush()
    assert resolve_order_branch(db, shop.c, cust, shop.ch.id) == shop.ch.id


def test_resolve_customer_branch_then_company_default_then_min_id(db, shop):
    cust = shop.cust
    cust.branch_id = shop.yu.id
    shop.c.shop_default_branch_id = shop.ch.id
    db.flush()
    assert resolve_order_branch(db, shop.c, cust, None) == shop.yu.id          # mijoz filiali
    cust.branch_id = None
    db.flush()
    assert resolve_order_branch(db, shop.c, cust, None) == shop.ch.id          # korxona standarti
    shop.c.shop_default_branch_id = None
    db.flush()
    assert resolve_order_branch(db, shop.c, cust, None) == min(shop.ch.id, shop.yu.id)   # eng kichik id


def test_resolve_skips_invalid_customer_and_default_branch(db, mk, shop):
    cust = shop.cust
    cust.branch_id = shop.ch.id
    shop.ch.is_active = False                       # nofaol — zanjir keyingi qadamga o'tadi
    shop.c.shop_default_branch_id = shop.ch.id
    db.flush()
    assert resolve_order_branch(db, shop.c, cust, None) == shop.yu.id


def test_resolve_single_pickup_branch(db, mk):
    c = mk.company()
    b = mk.branch(c)
    mk.branch(c, "Omborsiz filial")                 # do'kon omborsiz — pickup emas
    mk.warehouse(c, b, type=WarehouseType.shop)
    cust = _customer(db, c)
    assert resolve_order_branch(db, c, cust, None) == b.id


def test_resolve_empty_returns_400(db, mk):
    c = mk.company()
    mk.branch(c)                                    # filial bor, lekin do'kon ombori yo'q
    cust = _customer(db, c)
    with pytest.raises(HTTPException) as e:
        resolve_order_branch(db, c, cust, None)
    assert e.value.status_code == 400 and e.value.detail == NO_SHOP_BRANCH


def test_resolve_rejects_foreign_inactive_and_warehouseless_branch(db, mk, shop):
    other = mk.company()
    ob = mk.branch(other)
    mk.warehouse(other, ob, type=WarehouseType.shop)
    no_wh = mk.branch(shop.c, "Omborsiz")
    shop.yu.is_active = False
    db.flush()
    for bad in (ob.id, no_wh.id, shop.yu.id, 999999):
        with pytest.raises(HTTPException) as e:
            resolve_order_branch(db, shop.c, shop.cust, bad)
        assert e.value.status_code == 400 and e.value.detail == BRANCH_NOT_PICKUP


def test_pickup_branches_ordered_active_with_shop_warehouse(db, mk, shop):
    mk.branch(shop.c, "Omborsiz")
    arch = mk.branch(shop.c, "Arxiv")
    mk.warehouse(shop.c, arch, type=WarehouseType.shop)
    arch.is_active = False
    db.flush()
    assert [b.id for b in list_pickup_branches(db, shop.c.id)] == [shop.ch.id, shop.yu.id]


def test_shop_warehouses_branch_filter_and_nonsellable(db, mk, shop):
    mk.warehouse(shop.c, shop.ch, type=WarehouseType.raw_material, name="Do'kon xom ashyo")
    assert [w.id for w in shop_warehouses(db, shop.c.id)] == [shop.w_ch.id, shop.w_yu.id]
    assert [w.id for w in shop_warehouses(db, shop.c.id, shop.yu.id)] == [shop.w_yu.id]


def test_pick_fulfillment_warehouse_prefers_shop_type_then_min_id(db, mk, shop):
    mk.warehouse(shop.c, shop.ch, type=WarehouseType.shop, name="Chilonzor 2")
    wh = pick_fulfillment_warehouse(db, shop.c.id, shop.ch.id)
    assert wh.id == shop.w_ch.id
    assert pick_fulfillment_warehouse(db, shop.c.id, None) is None
    assert pick_fulfillment_warehouse(db, shop.c.id, 999999) is None


def test_default_branch_for_new_customer(db, mk, shop):
    c = shop.c
    assert default_branch_for_new_customer(db, c) is None                       # 2 faol filial, standart yo'q
    c.shop_default_branch_id = shop.yu.id
    db.flush()
    assert default_branch_for_new_customer(db, c) == shop.yu.id
    shop.yu.is_active = False                                                   # nofaol standart -> yagona faol filial
    db.flush()
    assert default_branch_for_new_customer(db, c) == shop.ch.id
    solo = mk.company()
    sb = mk.branch(solo)
    assert default_branch_for_new_customer(db, solo) == sb.id                   # yagona filial
    assert default_branch_for_new_customer(db, mk.company()) is None            # filialsiz


# ───────────────────── Mini App (HTTP) ─────────────────────

def test_shop_info_lists_pickup_branches_only_own(client, mk, shop):
    other = mk.company()
    ob = mk.branch(other)
    mk.warehouse(other, ob, type=WarehouseType.shop)
    shop.c.shop_default_branch_id = shop.yu.id
    r = client.get(f"/api/shop/{shop.c.id}/info")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [b["id"] for b in body["branches"]] == [shop.ch.id, shop.yu.id]
    assert body["branches"][0] == {"id": shop.ch.id, "name": "Chilonzor", "address": "Chilonzor 1", "phone": "901111111"}
    assert body["default_branch_id"] == shop.yu.id
    assert ob.id not in [b["id"] for b in body["branches"]]


def test_products_stock_is_per_branch(client, shop):
    p = _auth(shop.c, shop.cust)
    ch = client.get(f"/api/shop/{shop.c.id}/products", params={**p, "branch_id": shop.ch.id}).json()
    yu = client.get(f"/api/shop/{shop.c.id}/products", params={**p, "branch_id": shop.yu.id}).json()
    assert ch[0]["available"] == 0 and yu[0]["available"] == 10
    # filialsiz va mijozda filial yo'q: eski xatti-harakat — yig'indi
    allq = client.get(f"/api/shop/{shop.c.id}/products", params=p).json()
    assert allq[0]["available"] == 10
    # mijoz filiali bo'yicha (parametr yo'q)
    shop.cust.branch_id = shop.ch.id
    assert client.get(f"/api/shop/{shop.c.id}/products", params=p).json()[0]["available"] == 0


def test_products_foreign_branch_400(client, mk, shop):
    other = mk.company()
    ob = mk.branch(other)
    mk.warehouse(other, ob, type=WarehouseType.shop)
    r = client.get(f"/api/shop/{shop.c.id}/products", params={**_auth(shop.c, shop.cust), "branch_id": ob.id})
    assert r.status_code == 400 and r.json()["detail"] == BRANCH_NOT_PICKUP


def test_order_rejected_for_branch_without_stock_when_disallowed(client, db, shop):
    shop.c.shop_allow_out_of_stock_orders = False
    db.flush()
    p = _auth(shop.c, shop.cust)
    url = f"/api/shop/{shop.c.id}/order"
    r = client.post(url, params=p, json=_order_body(shop.prod, 1, branch_id=shop.ch.id))
    assert r.status_code == 400 and "yetarli qoldiq yo'q" in r.json()["detail"]
    assert db.query(Order).filter(Order.company_id == shop.c.id).count() == 0
    ok = client.post(url, params=p, json=_order_body(shop.prod, 1, branch_id=shop.yu.id))
    assert ok.status_code == 200, ok.text


def test_order_records_branch_and_warehouse_and_customer_branch(client, db, shop):
    r = client.post(f"/api/shop/{shop.c.id}/order", params=_auth(shop.c, shop.cust),
                    json=_order_body(shop.prod, 2, branch_id=shop.yu.id))
    assert r.status_code == 200, r.text
    orders = db.query(Order).filter(Order.id.in_(r.json()["order_ids"])).all()
    assert orders and all(o.branch_id == shop.yu.id and o.warehouse_id == shop.w_yu.id for o in orders)
    db.refresh(shop.cust)
    assert shop.cust.branch_id == shop.yu.id          # bo'sh edi — tanlangan filial yozildi


def test_order_keeps_existing_customer_branch(client, db, shop):
    shop.cust.branch_id = shop.ch.id
    db.flush()
    r = client.post(f"/api/shop/{shop.c.id}/order", params=_auth(shop.c, shop.cust),
                    json=_order_body(shop.prod, 1, branch_id=shop.yu.id))
    assert r.status_code == 200, r.text
    db.refresh(shop.cust)
    assert shop.cust.branch_id == shop.ch.id          # mavjud filial ustidan yozilmaydi


def test_old_miniapp_without_branch_uses_chain(client, db, shop):
    """Eski keshdagi Mini App branch_id yubormaydi — mijoz filiali, keyin standart, keyin eng kichik id."""
    url = f"/api/shop/{shop.c.id}/order"
    p = _auth(shop.c, shop.cust)
    shop.cust.branch_id = shop.yu.id
    db.flush()
    r1 = client.post(url, params=p, json=_order_body(shop.prod))
    assert r1.status_code == 200, r1.text
    assert db.get(Order, r1.json()["order_ids"][0]).branch_id == shop.yu.id
    shop.cust.branch_id = None
    shop.c.shop_default_branch_id = shop.ch.id
    db.flush()
    r2 = client.post(url, params=p, json=_order_body(shop.prod))
    o2 = db.get(Order, r2.json()["order_ids"][0])
    assert o2.branch_id == shop.ch.id and o2.warehouse_id == shop.w_ch.id


def test_order_foreign_company_branch_400(client, db, mk, shop):
    other = mk.company()
    ob = mk.branch(other)
    mk.warehouse(other, ob, type=WarehouseType.shop)
    r = client.post(f"/api/shop/{shop.c.id}/order", params=_auth(shop.c, shop.cust),
                    json=_order_body(shop.prod, 1, branch_id=ob.id))
    assert r.status_code == 400 and r.json()["detail"] == BRANCH_NOT_PICKUP
    assert db.query(Order).filter(Order.company_id == shop.c.id).count() == 0


def test_my_orders_shows_branch_and_pickup_address(client, db, shop):
    p = _auth(shop.c, shop.cust)
    client.post(f"/api/shop/{shop.c.id}/order", params=p, json=_order_body(shop.prod, 1, branch_id=shop.ch.id))
    client.post(f"/api/shop/{shop.c.id}/order", params=p, json={
        **_order_body(shop.prod, 1, branch_id=shop.yu.id), "delivery_type": "delivery", "delivery_address": "Manzil 5"})
    rows = client.get(f"/api/shop/{shop.c.id}/my-orders", params=p).json()
    by_branch = {r["branch_name"]: r for r in rows}
    assert by_branch["Chilonzor"]["pickup_address"] == "Chilonzor 1"
    assert by_branch["Yunusobod"]["pickup_address"] is None          # yetkazish buyurtmasi


def test_shop_me_returns_customer_branch(client, db, shop):
    shop.cust.branch_id = shop.yu.id
    db.flush()
    r = client.get(f"/api/shop/{shop.c.id}/me", params=_auth(shop.c, shop.cust))
    assert r.status_code == 200 and r.json()["branch_id"] == shop.yu.id


# ───────────────────── /orders ro'yxati va companies ─────────────────────

def _mk_order(db, c, cust, branch, prod, wh=None, group="g-t313-1", **kw):
    o = Order(company_id=c.id, customer_id=cust.id, branch_id=branch.id, warehouse_id=wh.id if wh else None,
              product_id=prod.id, quantity=1, unit_price=Decimal("1000"), total_amount=Decimal("1000"),
              status=OrderStatus.pending, order_group_id=group, payment_type="cash", **kw)
    db.add(o)
    db.flush()
    return o


def test_list_orders_has_branch_warehouse_and_pickup_address(client, db, mk, shop):
    admin = mk.user(shop.c, role=UserRole.admin)
    _mk_order(db, shop.c, shop.cust, shop.ch, shop.prod, wh=shop.w_ch, group="g-a")
    _mk_order(db, shop.c, shop.cust, shop.yu, shop.prod, wh=shop.w_yu, group="g-b", delivery_type="delivery")
    rows = {r["group_id"]: r for r in client.login(admin).get("/api/orders").json()}
    assert rows["g-a"]["branch_name"] == "Chilonzor" and rows["g-a"]["warehouse_id"] == shop.w_ch.id
    assert rows["g-a"]["pickup_address"] == "Chilonzor 1"
    assert rows["g-b"]["pickup_address"] is None
    flt = client.login(admin).get("/api/orders", params={"branch_id": shop.yu.id}).json()
    assert [r["group_id"] for r in flt] == ["g-b"]


def test_list_orders_company_isolation(client, db, mk, shop):
    other_c, other_b, other_w, other_admin = mk.tenant()
    other_cust = _customer(db, other_c)
    other_prod = _product(db, other_c)
    _mk_order(db, other_c, other_cust, other_b, other_prod, group="g-other")
    _mk_order(db, shop.c, shop.cust, shop.ch, shop.prod, group="g-own")
    admin = mk.user(shop.c, role=UserRole.admin)
    ids = [r["group_id"] for r in client.login(admin).get("/api/orders").json()]
    assert ids == ["g-own"]
    other_ids = [r["group_id"] for r in client.login(other_admin).get("/api/orders").json()]
    assert other_ids == ["g-other"]


def test_company_update_shop_default_branch(client, db, mk, shop):
    admin = mk.user(shop.c, role=UserRole.admin)
    r = client.login(admin).put(f"/api/companies/{shop.c.id}", json={"shop_default_branch_id": shop.yu.id})
    assert r.status_code == 200, r.text
    assert r.json()["shop_default_branch_id"] == shop.yu.id
    # begona korxona filiali — 400
    other = mk.company()
    ob = mk.branch(other)
    bad = client.login(admin).put(f"/api/companies/{shop.c.id}", json={"shop_default_branch_id": ob.id})
    assert bad.status_code == 400
    db.refresh(shop.c)
    assert shop.c.shop_default_branch_id == shop.yu.id
    # tozalash
    clr = client.login(admin).put(f"/api/companies/{shop.c.id}", json={"shop_default_branch_id": None})
    assert clr.status_code == 200 and clr.json()["shop_default_branch_id"] is None


def test_company_update_foreign_company_404(client, mk, shop):
    other_admin = mk.user(mk.company(), role=UserRole.admin)
    r = client.login(other_admin).put(f"/api/companies/{shop.c.id}", json={"shop_default_branch_id": shop.yu.id})
    assert r.status_code == 404


# ───────────────────── avto-sotuv (order_to_sale) ─────────────────────

def _auto_sale_env(db, mk, shop):
    shop.c.orders_auto_create_sale = True
    admin = mk.user(shop.c, role=UserRole.admin, branch=shop.ch)           # birinchi admin — Chilonzor xodimi
    cashier = mk.user(shop.c, role=UserRole.cashier, branch=shop.yu)
    db.flush()
    return admin, cashier


def _capture_create_sale(monkeypatch):
    import app.services.sale_create as sc
    calls = []

    def fake_create_sale(db, data, current_user):
        calls.append((data, current_user))
        return SimpleNamespace(id=None, number="T313")

    monkeypatch.setattr(sc, "create_sale", fake_create_sale)
    return calls


def test_auto_sale_uses_order_warehouse_and_branch_cashier(db, mk, shop, monkeypatch):
    from app.services.order_to_sale import maybe_create_sale_for_delivered_group
    admin, cashier = _auto_sale_env(db, mk, shop)
    calls = _capture_create_sale(monkeypatch)
    o = _mk_order(db, shop.c, shop.cust, shop.yu, shop.prod, wh=shop.w_yu)
    maybe_create_sale_for_delivered_group(db, [o])
    assert len(calls) == 1
    data, user = calls[0]
    assert data.warehouse_id == shop.w_yu.id          # Order.warehouse_id
    assert user.id == cashier.id                       # buyurtma filialidagi kassir, birinchi admin emas


def test_auto_sale_old_order_without_warehouse_uses_branch_shop_warehouse(db, mk, shop, monkeypatch):
    from app.services.order_to_sale import maybe_create_sale_for_delivered_group
    admin, cashier = _auto_sale_env(db, mk, shop)
    calls = _capture_create_sale(monkeypatch)
    o = _mk_order(db, shop.c, shop.cust, shop.ch, shop.prod, wh=None)       # eski buyurtma: warehouse_id NULL
    maybe_create_sale_for_delivered_group(db, [o])
    data, user = calls[0]
    assert data.warehouse_id == shop.w_ch.id
    assert user.id == admin.id                         # Chilonzorda kassir/menejer yo'q — admin zaxirasi


def test_auto_sale_ignores_foreign_company_order_warehouse(db, mk, shop, monkeypatch):
    from app.services.order_to_sale import maybe_create_sale_for_delivered_group
    _auto_sale_env(db, mk, shop)
    calls = _capture_create_sale(monkeypatch)
    other = mk.company()
    ob = mk.branch(other)
    ow = mk.warehouse(other, ob, type=WarehouseType.shop)
    o = _mk_order(db, shop.c, shop.cust, shop.yu, shop.prod, wh=ow)         # begona ombor — e'tiborga olinmaydi
    maybe_create_sale_for_delivered_group(db, [o])
    assert calls[0][0].warehouse_id == shop.w_yu.id


# ───────────────────── Telegram bot ─────────────────────

def test_handle_dokon_sends_miniapp_button_without_stock_queries(db, mk, shop):
    from app.routers.telegram import _handle_dokon
    customer = object()                                # faqat "None emas" tekshiriladi
    bg = BackgroundTasks()
    stmts = []

    def _count(conn, cursor, statement, *a):
        stmts.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", _count)
    try:
        asyncio.run(_handle_dokon(db, BOT_TOKEN, "777000", shop.c, customer, bg))
    finally:
        event.remove(bind, "before_cursor_execute", _count)
    lowered = [s.lower() for s in stmts]
    assert not any("warehouses" in s or "stock_levels" in s or "products" in s for s in lowered)
    args = bg.tasks[0].args
    msg, keyboard = args[2], args[3]
    assert "Buyurtma uchun mahsulot nomini kiriting" not in msg
    button = keyboard["keyboard"][0][0]
    assert "web_app" in button and f"c={shop.c.id}" in button["web_app"]["url"]


def test_dead_telegram_order_handler_removed():
    import app.routers.telegram as tg
    assert not hasattr(tg, "_handle_order_from_telegram")
    assert tg.COMMAND_MAP["/dokon"] is tg._handle_dokon


def test_bot_registration_gets_default_branch(client, db, mk, shop, monkeypatch):
    import app.routers.telegram as tg
    from app.models.bot_session import BotSession

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(tg, "send_telegram_message", _noop)
    monkeypatch.setattr(tg, "send_loyalty_card", _noop)
    shop.c.shop_default_branch_id = shop.yu.id
    db.add(BotSession(chat_id="555001", token=BOT_TOKEN, step="awaiting_phone", temp_name="Yangi Mijoz"))
    db.flush()
    r = client.post(f"/api/telegram/webhook/{BOT_TOKEN}", json={
        "message": {"chat": {"id": 555001}, "contact": {"phone_number": "998935550011"}}})
    assert r.status_code == 200, r.text
    created = db.query(Customer).filter(Customer.company_id == shop.c.id, Customer.tg_chat_id == "555001").one()
    assert created.branch_id == shop.yu.id


def test_bot_registration_single_branch_company(client, db, mk, monkeypatch):
    import app.routers.telegram as tg
    from app.models.bot_session import BotSession

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(tg, "send_telegram_message", _noop)
    monkeypatch.setattr(tg, "send_loyalty_card", _noop)
    c = mk.company()
    c.tg_bot_token = "999:solo-token"
    b = mk.branch(c)
    db.add(BotSession(chat_id="555002", token="999:solo-token", step="awaiting_phone", temp_name="Solo"))
    db.flush()
    r = client.post("/api/telegram/webhook/999:solo-token", json={
        "message": {"chat": {"id": 555002}, "contact": {"phone_number": "998935550022"}}})
    assert r.status_code == 200, r.text
    created = db.query(Customer).filter(Customer.company_id == c.id, Customer.tg_chat_id == "555002").one()
    assert created.branch_id == b.id


# ───────────────────── i18n va xabarlar ─────────────────────

def test_no_dokon_word_in_orders_and_customers_messages():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    for rel in ("app/routers/orders.py", "app/routers/customers.py"):
        text = (root / rel).read_text(encoding="utf-8").lower()
        assert "dokon" not in text, rel


def test_pending_i18n_keys_consistent_and_used():
    import json
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    data = json.loads((root / "tests/branch_audit/i18n_pending/T3.13.json").read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"])
    assert all(v.strip() for lang in data.values() for v in lang.values())
    src = (root / "frontend/src/pages/admin/Orders.jsx").read_text(encoding="utf-8") + \
          (root / "frontend/src/pages/admin/Settings.jsx").read_text(encoding="utf-8")
    for key in data["uz"]:
        assert key in src, key


def test_migration_is_additive_and_chain_open():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    text = (root / "alembic/versions/t3_13_order_warehouse_shop_default_branch.py").read_text(encoding="utf-8")
    assert "revision = 't3_13'" in text and "down_revision = 't3_12'" in text
    assert "ADD COLUMN IF NOT EXISTS warehouse_id" in text and "ADD COLUMN IF NOT EXISTS shop_default_branch_id" in text
    assert "NOT NULL" not in text.split("def downgrade")[0]


def test_single_branch_company_with_branchless_shop_warehouse_unchanged(db, mk):
    """Bir filialli korxonada filialsiz (eski) do'kon ombori yagona filialga tegishli — buyurtma ishlaydi."""
    c = mk.company()
    b = mk.branch(c)
    w = mk.warehouse(c, None, type=WarehouseType.shop)
    cust = _customer(db, c)
    assert resolve_order_branch(db, c, cust, None) == b.id
    assert pick_fulfillment_warehouse(db, c.id, b.id).id == w.id
    # ikkinchi filial ochilsa filialsiz ombor hech kimga tegishli emas
    mk.branch(c)
    assert list_pickup_branches(db, c.id) == []
