"""T1.17 — POS/agent/do'kon katalogida filial bo'yicha qoldiq va assortiment.

Qabul mezonlari: 1 (pos-list filial qoldig'i), 2 (nofaol/xom ashyo/NULL-ombor qatorlari),
3-4 (default sotuv ombori: shop > main > min id, bo'sh filialda 400), 6 (agent cost_price yo'q),
8 (Telegram do'kon ro'yxati), korxonalararo izolyatsiya.
"""
import asyncio
import itertools
from decimal import Decimal

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.user import UserRole
from app.models.warehouse import WarehouseType
from app.schemas.sale import SaleCreate
from app.services.sale_create import create_pending_sale, create_sale
from app.services.warehouse_scope import (
    NON_SELLABLE_TYPES, default_sale_warehouse_id, sellable_warehouse_ids, stock_totals,
)

_n = itertools.count(1)


def _product(db, company, **kw):
    n = next(_n)
    p = Product(name=kw.pop("name", f"Tovar T117-{n}"), sku=f"T117-{n}", barcode=f"BC117-{n:06d}",
                company_id=company.id, cost_price=Decimal("500"), sale_price=Decimal("1000"), **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty):
    sl = StockLevel(product_id=product.id, warehouse_id=wh.id if wh else None, quantity=Decimal(qty))
    db.add(sl)
    db.flush()
    return sl


def _pos_stock(client, user, **params):
    r = client.login(user).get("/api/products/pos-list", params={"limit": 100, **params})
    assert r.status_code == 200, r.text
    return {row["id"]: row["stock_quantity"] for row in r.json()}


@pytest.fixture
def two_branches(db, mk):
    """Bitta korxona, ikki filial (A, B), har birida bittadan main ombor va kassir."""
    c = mk.company()
    ba, bb = mk.branch(c), mk.branch(c)
    wa = mk.warehouse(c, ba, type=WarehouseType.main)
    wb = mk.warehouse(c, bb, type=WarehouseType.main)
    ua = mk.user(c, role=UserRole.cashier, branch=ba)
    ub = mk.user(c, role=UserRole.cashier, branch=bb)
    return c, ba, bb, wa, wb, ua, ub


# ───────────────────── warehouse_scope yordamchilari ─────────────────────

def test_sellable_ids_filters_type_active_branch(db, mk):
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    ok = mk.warehouse(c, b1, type=WarehouseType.main)
    shop = mk.warehouse(c, b1, type=WarehouseType.shop)
    ret = mk.warehouse(c, b1, type=WarehouseType.returns)
    for t in NON_SELLABLE_TYPES:
        mk.warehouse(c, b1, type=t)
    mk.warehouse(c, b1, type=WarehouseType.main, is_active=False)
    other_branch = mk.warehouse(c, b2, type=WarehouseType.main)
    other_company = mk.warehouse(mk.company(), None, type=WarehouseType.main)

    assert sellable_warehouse_ids(db, c.id, b1.id) == sorted([ok.id, shop.id, ret.id])
    assert sellable_warehouse_ids(db, c.id, b2.id) == [other_branch.id]
    # branch berilmasa — butun korxona (begona korxona kirmaydi)
    all_ids = sellable_warehouse_ids(db, c.id)
    assert other_company.id not in all_ids and other_branch.id in all_ids and ok.id in all_ids
    # branch_ids — to'plam; bo'sh to'plam — hech narsa
    assert sellable_warehouse_ids(db, c.id, branch_ids=[b2.id]) == [other_branch.id]
    assert sellable_warehouse_ids(db, c.id, branch_ids=[]) == []


def test_default_sale_warehouse_is_deterministic_shop_main_minid(db, mk):
    c = mk.company()
    b = mk.branch(c)
    assert default_sale_warehouse_id(db, c.id, b.id) is None          # bo'sh filial
    mk.warehouse(c, b, type=WarehouseType.raw_material)               # sotilmaydi
    assert default_sale_warehouse_id(db, c.id, b.id) is None
    ret = mk.warehouse(c, b, type=WarehouseType.returns)
    assert default_sale_warehouse_id(db, c.id, b.id) == ret.id        # boshqa sotiladigan tur
    main2 = mk.warehouse(c, b, type=WarehouseType.main)
    main1 = mk.warehouse(c, b, type=WarehouseType.main)
    assert default_sale_warehouse_id(db, c.id, b.id) == main2.id      # main > returns, min id
    shop = mk.warehouse(c, b, type=WarehouseType.shop)
    for _ in range(3):                                                # takror chaqirishda o'zgarmaydi
        assert default_sale_warehouse_id(db, c.id, b.id) == shop.id
    assert main1.id > main2.id


def test_default_sale_warehouse_never_falls_to_other_branch(db, mk):
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    mk.warehouse(c, b2, type=WarehouseType.shop)
    assert default_sale_warehouse_id(db, c.id, b1.id) is None


def test_stock_totals_skips_null_warehouse_and_unlisted(db, mk):
    c = mk.company()
    b = mk.branch(c)
    w1 = mk.warehouse(c, b)
    w2 = mk.warehouse(c, b)
    p = _product(db, c)
    _stock(db, p, w1, 5)
    _stock(db, p, w2, 7)
    _stock(db, p, None, 100)            # NULL-ombor qatori hisoblanmasin
    assert stock_totals(db, [p.id], [w1.id])[p.id] == Decimal("5")
    assert stock_totals(db, [p.id], [w1.id, w2.id])[p.id] == Decimal("12")
    assert stock_totals(db, [p.id], []) == {}
    assert stock_totals(db, [], [w1.id]) == {}


# ───────────────────── /products/pos-list ─────────────────────

def test_pos_list_stock_by_branch(db, client, two_branches):
    """Mezon 1: faqat B filialda bor tovar A kassiriga 0 ko'rinadi."""
    c, ba, bb, wa, wb, ua, ub = two_branches
    p = _product(db, c)
    _stock(db, p, wb, 12)
    assert _pos_stock(client, ua)[p.id] == 0
    assert _pos_stock(client, ub)[p.id] == 12
    _stock(db, _product(db, c), wa, 3)  # ijobiy yo'l: o'z filialidagi qoldiq ko'rinadi
    assert _pos_stock(client, ua)[p.id] == 0


def test_pos_list_own_branch_stock_positive(db, client, two_branches):
    c, ba, bb, wa, wb, ua, ub = two_branches
    p = _product(db, c)
    _stock(db, p, wa, 4)
    _stock(db, p, wb, 9)
    assert _pos_stock(client, ua)[p.id] == 4
    assert _pos_stock(client, ub)[p.id] == 9


def test_pos_list_excludes_inactive_rawmaterial_null(db, client, mk):
    """Mezon 2: nofaol, xom ashyo/wip/tranzit va NULL-ombor qatorlari kirmaydi."""
    c, b, wh, user = mk.tenant(UserRole.cashier)
    p = _product(db, c)
    _stock(db, p, wh, 2)
    _stock(db, p, None, 50)
    _stock(db, p, mk.warehouse(c, b, type=WarehouseType.raw_material), 10)
    _stock(db, p, mk.warehouse(c, b, type=WarehouseType.wip), 10)
    _stock(db, p, mk.warehouse(c, b, type=WarehouseType.transit), 10)
    _stock(db, p, mk.warehouse(c, b, is_active=False), 10)
    assert _pos_stock(client, user)[p.id] == 2


def test_pos_list_admin_without_branch_sums_company_sellable(db, client, two_branches, mk):
    c, ba, bb, wa, wb, ua, ub = two_branches
    admin = mk.user(c, role=UserRole.admin)
    p = _product(db, c)
    _stock(db, p, wa, 4)
    _stock(db, p, wb, 9)
    assert _pos_stock(client, admin)[p.id] == 13


def test_pos_list_foreign_warehouse_rejected(db, client, two_branches, mk):
    """begona korxona -> 404; boshqa filial (kassir) -> 403; o'z ombori -> 200."""
    c, ba, bb, wa, wb, ua, ub = two_branches
    other_wh = mk.warehouse(mk.company(), None)
    r = client.login(ua).get("/api/products/pos-list", params={"warehouse_id": other_wh.id})
    assert r.status_code == 404
    r = client.login(ua).get("/api/products/pos-list", params={"warehouse_id": wb.id})
    assert r.status_code == 403
    p = _product(db, c)
    _stock(db, p, wa, 6)
    assert _pos_stock(client, ua, warehouse_id=wa.id)[p.id] == 6


def test_pos_list_inactive_warehouse_id_404(db, client, mk):
    c, b, wh, user = mk.tenant(UserRole.cashier)
    dead = mk.warehouse(c, b, is_active=False)
    r = client.login(user).get("/api/products/pos-list", params={"warehouse_id": dead.id})
    assert r.status_code == 404


# ───────────────────── /products/pos-context ─────────────────────

def test_pos_context(db, client, two_branches, mk):
    c, ba, bb, wa, wb, ua, ub = two_branches
    shop = mk.warehouse(c, ba, type=WarehouseType.shop)
    mk.warehouse(c, ba, type=WarehouseType.raw_material)
    mk.warehouse(c, ba, type=WarehouseType.main, is_active=False)
    r = client.login(ua).get("/api/products/pos-context")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["branch_id"] == ba.id
    assert d["default_warehouse_id"] == shop.id
    assert sorted(w["id"] for w in d["warehouses"]) == sorted([wa.id, shop.id])
    assert {w["type"] for w in d["warehouses"]} == {"main", "shop"}
    # begona korxona foydalanuvchisi bu omborlarni ko'rmaydi
    other = mk.user(mk.company(), role=UserRole.cashier)
    assert client.login(other).get("/api/products/pos-context").json()["warehouses"] == []


# ───────────────────── sotuvdagi default ombor ─────────────────────

def _sd(prod, **kw):
    return SaleCreate(items=[{"product_id": prod.id, "quantity": 1, "unit_price": 1000}],
                      payment_type="cash", paid_amount=Decimal("1000"), **kw)


def test_default_warehouse_shop_for_pending_and_regular_sale(db, mk):
    """Mezon 3: main ham, shop ham bo'lsa warehouse_id'siz sotuv shop'dan yechiladi."""
    c = mk.company()
    b = mk.branch(c)
    mk.warehouse(c, b, type=WarehouseType.main)
    shop = mk.warehouse(c, b, type=WarehouseType.shop)
    user = mk.user(c, role=UserRole.cashier, branch=b)
    prod = _product(db, c)
    _stock(db, prod, shop, 10)
    pend = create_pending_sale(db, _sd(prod), user)
    assert pend.warehouse_id == shop.id
    sale = create_sale(db, _sd(prod), user)
    assert sale.warehouse_id == shop.id
    # takroran ham o'zgarmaydi
    assert create_pending_sale(db, _sd(prod), user).warehouse_id == shop.id


def test_sale_without_branch_warehouse_is_400_not_other_branch(db, mk):
    """Mezon 4: filialida sotuv ombori yo'q — boshqa filial omboridan yechilmaydi."""
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    mk.warehouse(c, b2, type=WarehouseType.main)
    mk.warehouse(c, b1, type=WarehouseType.raw_material)
    user = mk.user(c, role=UserRole.cashier, branch=b1)
    prod = _product(db, c)
    with pytest.raises(HTTPException) as e1:
        create_sale(db, _sd(prod), user)
    assert e1.value.status_code == 409   # T1.5: "Filialda faol savdo ombori yo'q"
    with pytest.raises(HTTPException) as e2:
        create_pending_sale(db, _sd(prod), user)
    assert e2.value.status_code == 409


def test_sale_deducts_from_displayed_warehouse(db, mk):
    """Mezon 5: ekranda ko'ringan (pos-list) qoldiq ombori sotuv yechadigan ombor."""
    c, b, wh, user = mk.tenant(UserRole.cashier)
    prod = _product(db, c)
    _stock(db, prod, wh, 5)
    sale = create_sale(db, _sd(prod), user)
    assert sale.warehouse_id == wh.id
    sl = db.query(StockLevel).filter_by(product_id=prod.id, warehouse_id=wh.id).one()
    assert sl.quantity == Decimal("4")


# ───────────────────── agent katalogi ─────────────────────

def test_agent_catalog_branch_stock_no_cost_price(db, mk):
    """Mezon 2 va 6: agent filiali omborlari bo'yicha qoldiq, cost_price yo'q."""
    from app.routers.mobile.agent import catalog, my_customers

    c = mk.company()
    ba, bb = mk.branch(c), mk.branch(c)
    wa = mk.warehouse(c, ba)
    wb = mk.warehouse(c, bb)
    agent = mk.user(c, role=UserRole.agent, branch=ba)
    p = _product(db, c)
    _stock(db, p, wa, 3)
    _stock(db, p, wb, 40)
    _stock(db, p, None, 7)
    _stock(db, p, mk.warehouse(c, ba, type=WarehouseType.raw_material), 11)
    rows = catalog(db=db, current_user=agent)
    row = next(r for r in rows if r["id"] == p.id)
    assert row["stock"] == 3.0
    assert "cost_price" not in row

    # "tannarx" narx turidagi mijoz narxi serverda hisoblanib prices ga tushadi
    from app.models.customer import Customer
    cust = Customer(name="Tannarx mijoz", phone="998900000117", company_id=c.id, agent_id=agent.id,
                    price_type="cost")
    db.add(cust)
    db.flush()
    out = next(x for x in my_customers(db=db, current_user=agent) if x["id"] == cust.id)
    assert out["prices"][str(p.id)] == 500.0


def test_agent_catalog_company_isolation(db, mk):
    from app.routers.mobile.agent import catalog

    ca, ba, wa, agent_a = mk.tenant(UserRole.agent)
    cb, bb, wb, _ = mk.tenant(UserRole.agent)
    pb = _product(db, cb)
    _stock(db, pb, wb, 5)
    assert all(r["id"] != pb.id for r in catalog(db=db, current_user=agent_a))


# ───────────────────── Telegram "Do'kon" ─────────────────────

def test_telegram_dokon_single_query_sellable_only(db, mk):
    """Mezon 8: bir mahsulot bir marta, faqat faol sotiladigan omborlar, sikl ichida so'rov yo'q."""
    from sqlalchemy import event

    from app.routers.telegram import _handle_dokon

    c = mk.company()
    b = mk.branch(c)
    w1, w2 = mk.warehouse(c, b), mk.warehouse(c, b, type=WarehouseType.shop)
    p = _product(db, c, name="Cola T117")
    hidden = _product(db, c, name="Xom ashyo T117")
    _stock(db, p, w1, 3)
    _stock(db, p, w2, 4)
    _stock(db, p, None, 100)
    _stock(db, hidden, mk.warehouse(c, b, type=WarehouseType.raw_material), 9)
    _stock(db, hidden, mk.warehouse(c, b, is_active=False), 9)
    other = mk.company()
    _stock(db, _product(db, other, name="Begona T117"), mk.warehouse(other, None), 5)

    customer = object()  # faqat "None emas" tekshiriladi
    bg = BackgroundTasks()
    stmts = []

    def _count(conn, cursor, statement, *a):
        stmts.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", _count)
    try:
        asyncio.run(_handle_dokon(db, "tok", "1", c, customer, bg))
    finally:
        event.remove(bind, "before_cursor_execute", _count)
    msg = bg.tasks[0].args[2]
    # T3.13: katalog Mini App ga o'tdi — bot xabarida mahsulot ro'yxati ham, qoldiq so'rovi ham yo'q
    assert "Cola T117" not in msg and "Xom ashyo T117" not in msg and "Begona T117" not in msg
    assert len([s for s in stmts if s.lstrip().upper().startswith("SELECT")]) == 0


# ───────────────────── do'kon katalogi ─────────────────────

def test_shop_warehouse_ids_exclude_nonsellable(db, mk):
    from app.routers.shop import _shop_warehouse_ids

    c = mk.company()
    b = mk.branch(c)
    mk.warehouse(c, b, type=WarehouseType.raw_material, name="Do'kon xom ashyo")
    mk.warehouse(c, b, type=WarehouseType.main, is_active=False, name="Do'kon nofaol")
    named = mk.warehouse(c, b, type=WarehouseType.main, name="Do'kon asosiy")
    assert _shop_warehouse_ids(db, c.id) == [named.id]
    typed = mk.warehouse(c, b, type=WarehouseType.shop, name="Savdo")
    assert _shop_warehouse_ids(db, c.id) == [typed.id]
