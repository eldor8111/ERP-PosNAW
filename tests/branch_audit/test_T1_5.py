"""T1.5 — Sotuv/buyurtma/agent/kirim uchun ombor tanlashning aniq qoidasi (`resolve_warehouse`).

Qamrov: resolver jadval testi (requested_id, filial bor/yo'q, 0/1/2+ filial, returns-only filial,
begona korxona), create_sale / create_pending_sale (50 ketma-ket sotuv, 409/400, X-Branch-Id),
order_to_sale (Order.branch_id), agent buyurtmasi/katalogi/mijozi, field_staff, receivable_wallets,
POST /products (initial_stock), /inventory/receive, bulk-import.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T1_5.py -q -p no:cacheprovider
"""
import itertools
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.user import UserRole
from app.models.warehouse import WarehouseType
from app.schemas.sale import SaleCreate
from app.services.sale_create import create_pending_sale, create_sale
from app.services.warehouse_resolver import resolve_warehouse

_n = itertools.count(1)


def _product(db, company, **kw):
    n = next(_n)
    p = Product(name=kw.pop("name", f"Tovar T15-{n}"), sku=f"T15-{n}", barcode=f"BC15-{n:06d}",
                company_id=company.id, cost_price=Decimal("500"), sale_price=Decimal("1000"), **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty):
    sl = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=Decimal(qty))
    db.add(sl)
    db.flush()
    return sl


def _qty(db, product, wh):
    row = db.query(StockLevel).filter_by(product_id=product.id, warehouse_id=wh.id).first()
    return Decimal(str(row.quantity)) if row else None


def _sd(prod, qty=1, **kw):
    return SaleCreate(items=[{"product_id": prod.id, "quantity": qty, "unit_price": 1000}],
                      payment_type="cash", paid_amount=Decimal(1000 * qty), **kw)


def _status(fn, *a, **kw):
    with pytest.raises(HTTPException) as e:
        fn(*a, **kw)
    return e.value.status_code


# ───────────────────────── resolver jadval testi ─────────────────────────

def test_resolver_branch_default_ignores_returns_and_other_types(db, mk):
    """Mezon 1: main + returns (+ transit/raw_material/wip) bor filialda har doim main tanlanadi."""
    c = mk.company()
    b = mk.branch(c)
    mk.warehouse(c, b, type=WarehouseType.returns)      # eng kichik id — returns
    mk.warehouse(c, b, type=WarehouseType.transit)
    mk.warehouse(c, b, type=WarehouseType.raw_material)
    mk.warehouse(c, b, type=WarehouseType.wip)
    main = mk.warehouse(c, b, type=WarehouseType.main)
    ids = {resolve_warehouse(db, c.id, branch_id=b.id) for _ in range(50)}
    assert ids == {main.id}
    assert resolve_warehouse(db, c.id, branch_id=b.id, purpose="receive") == main.id
    assert resolve_warehouse(db, c.id, branch_id=b.id, purpose="order") == main.id


def test_resolver_is_default_wins_then_shop_then_min_id(db, mk):
    c = mk.company()
    b = mk.branch(c)
    w_main = mk.warehouse(c, b, type=WarehouseType.main)
    w_shop = mk.warehouse(c, b, type=WarehouseType.shop)
    assert resolve_warehouse(db, c.id, branch_id=b.id) == w_shop.id        # shop > main
    w_main.is_default = True
    db.flush()
    assert resolve_warehouse(db, c.id, branch_id=b.id) == w_main.id        # is_default ustun
    w_main.is_active = False
    db.flush()
    assert resolve_warehouse(db, c.id, branch_id=b.id) == w_shop.id        # nofaol ombor tanlanmaydi


def test_resolver_returns_only_branch_is_409_not_other_branch(db, mk):
    """Mezon 2: ombori yo'q (faqat returns bor) filial -> 409; boshqa filial omboriga o'tmaydi."""
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    mk.warehouse(c, b1, type=WarehouseType.returns)
    mk.warehouse(c, b2, type=WarehouseType.main)
    assert _status(resolve_warehouse, db, c.id, branch_id=b1.id) == 409
    assert _status(resolve_warehouse, db, c.id, branch_id=b1.id, purpose="receive") == 409
    # customer_branch_id ham xuddi shunday
    assert _status(resolve_warehouse, db, c.id, customer_branch_id=b1.id, purpose="order") == 409


def test_resolver_receive_falls_back_to_raw_material_but_never_returns(db, mk):
    c = mk.company()
    b = mk.branch(c)
    mk.warehouse(c, b, type=WarehouseType.returns)
    mk.warehouse(c, b, type=WarehouseType.transit)
    raw = mk.warehouse(c, b, type=WarehouseType.raw_material)
    assert resolve_warehouse(db, c.id, branch_id=b.id, purpose="receive") == raw.id
    assert _status(resolve_warehouse, db, c.id, branch_id=b.id, purpose="sale") == 409


def test_resolver_requested_id_validation(db, mk):
    c, b, w, user = mk.tenant(UserRole.cashier)
    other_c = mk.company()
    other_wh = mk.warehouse(other_c, mk.branch(other_c))
    inactive = mk.warehouse(c, b, is_active=False)
    b2 = mk.branch(c)
    w2 = mk.warehouse(c, b2)
    assert resolve_warehouse(db, c.id, requested_id=w.id, user=user) == w.id
    assert resolve_warehouse(db, c.id, requested_id=w.id) == w.id
    for bad in (other_wh.id, inactive.id, 999999):
        assert _status(resolve_warehouse, db, c.id, requested_id=bad, user=user) == 404
        assert _status(resolve_warehouse, db, c.id, requested_id=bad) == 404
    # non-bypass kassir boshqa filial omborini so'ray olmaydi (403), admin esa oladi
    assert _status(resolve_warehouse, db, c.id, requested_id=w2.id, user=user) == 403
    admin = mk.user(c, role=UserRole.admin)
    assert resolve_warehouse(db, c.id, requested_id=w2.id, user=admin) == w2.id


def test_resolver_foreign_branch_is_404(db, mk):
    c = mk.company()
    mk.branch(c)
    other = mk.company()
    ob = mk.branch(other)
    mk.warehouse(other, ob)
    assert _status(resolve_warehouse, db, c.id, branch_id=ob.id) == 404


def test_resolver_unknown_branch_rules(db, mk):
    """Mezon 3-4: filial aniq emas — 1 filial: o'sha filial ombori; 2+ filial: 400; 0 filial: filialsiz main/shop."""
    # 1 filial, 1 ombor — hech narsa o'zgarmaydi
    c1, b1, w1, _ = mk.tenant()
    assert resolve_warehouse(db, c1.id) == w1.id
    # 2 filial
    c2 = mk.company()
    mk.warehouse(c2, mk.branch(c2))
    mk.warehouse(c2, mk.branch(c2))
    assert _status(resolve_warehouse, db, c2.id) == 400
    # filialsiz korxona: branch_id IS NULL main/shop (eng kichik id)
    c3 = mk.company()
    mk.warehouse(c3, None, type=WarehouseType.returns)
    w3 = mk.warehouse(c3, None, type=WarehouseType.main)
    mk.warehouse(c3, None, type=WarehouseType.main)
    assert resolve_warehouse(db, c3.id) == w3.id
    # ombori umuman yo'q korxona
    assert _status(resolve_warehouse, db, mk.company().id) == 409
    # begona korxona omborlari hisobga olinmaydi
    c4 = mk.company()
    assert _status(resolve_warehouse, db, c4.id) == 409


# ───────────────────────── create_sale / create_pending_sale ─────────────────────────

def test_fifty_sales_all_from_default_not_returns(db, mk):
    c = mk.company()
    b = mk.branch(c)
    ret = mk.warehouse(c, b, type=WarehouseType.returns)
    main = mk.warehouse(c, b, type=WarehouseType.main)
    user = mk.user(c, role=UserRole.cashier, branch=b)
    prod = _product(db, c)
    _stock(db, prod, ret, 100)
    _stock(db, prod, main, 100)
    for _ in range(50):
        sale = create_sale(db, _sd(prod), user)
        assert sale.warehouse_id == main.id
    assert _qty(db, prod, main) == Decimal("50")
    assert _qty(db, prod, ret) == Decimal("100")
    assert create_pending_sale(db, _sd(prod), user).warehouse_id == main.id


def test_cashier_of_branch_without_warehouse_gets_409_other_branch_untouched(db, mk):
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    w2 = mk.warehouse(c, b2)
    user = mk.user(c, role=UserRole.cashier, branch=b1)
    prod = _product(db, c)
    _stock(db, prod, w2, 10)
    assert _status(create_sale, db, _sd(prod), user) == 409
    assert _status(create_pending_sale, db, _sd(prod), user) == 409
    assert _qty(db, prod, w2) == Decimal("10")


def test_single_branch_single_warehouse_unchanged(db, mk):
    c, b, w, user = mk.tenant(UserRole.cashier)
    prod = _product(db, c)
    _stock(db, prod, w, 5)
    sale = create_sale(db, _sd(prod), user)
    assert sale.warehouse_id == w.id
    assert _qty(db, prod, w) == Decimal("4")


def test_no_stock_row_in_default_creates_row_there_not_other_warehouse(db, mk):
    """Default omborda qoldiq qatori yo'q: boshqa ombordan yechilmaydi, default omborda yangi qator."""
    c = mk.company()
    b = mk.branch(c)
    main = mk.warehouse(c, b, type=WarehouseType.main)
    other = mk.warehouse(c, b, type=WarehouseType.returns)
    user = mk.user(c, role=UserRole.cashier, branch=b)
    prod = _product(db, c)
    _stock(db, prod, other, 50)
    sale = create_sale(db, _sd(prod), user)
    assert sale.warehouse_id == main.id
    assert _qty(db, prod, other) == Decimal("50")
    assert _qty(db, prod, main) == Decimal("-1")


def _admin_two_branches(db, mk):
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    w1 = mk.warehouse(c, b1)
    w2 = mk.warehouse(c, b2)
    admin = mk.user(c, role=UserRole.admin)
    prod = _product(db, c)
    _stock(db, prod, w1, 10)
    _stock(db, prod, w2, 10)
    return c, b1, b2, w1, w2, admin, prod


def test_branchless_admin_two_branches_400_and_header_picks_branch(db, mk, client):
    """Mezon 3: 2+ filial, admin warehouse_id va X-Branch-Id'siz -> 400; header bilan tanlangan filial omboridan."""
    c, b1, b2, w1, w2, admin, prod = _admin_two_branches(db, mk)
    body = {"items": [{"product_id": prod.id, "quantity": 1, "unit_price": 1000}],
            "payment_type": "cash", "paid_amount": 1000}
    cl = client.login(admin)
    r = cl.post("/api/sales/", json=body)
    assert r.status_code == 400, r.text
    assert _qty(db, prod, w1) == Decimal("10") and _qty(db, prod, w2) == Decimal("10")
    r = cl.post("/api/sales/", json=body, headers={"X-Branch-Id": str(b2.id)})
    assert r.status_code == 200, r.text
    assert _qty(db, prod, w2) == Decimal("9") and _qty(db, prod, w1) == Decimal("10")
    # pending ham xuddi shunday
    assert cl.post("/api/sales/pending", json=body).status_code == 400
    r = cl.post("/api/sales/pending", json=body, headers={"X-Branch-Id": str(b1.id)})
    assert r.status_code == 200, r.text
    from app.models.sale import Sale
    assert db.query(Sale).filter(Sale.id == r.json()["id"]).one().warehouse_id == w1.id


# ───────────────────────── order_to_sale ─────────────────────────

def _order_env(db, mk):
    from app.models.customer import Customer
    c = mk.company(orders_auto_create_sale=True)
    b1, b2 = mk.branch(c), mk.branch(c)
    w1, w2 = mk.warehouse(c, b1), mk.warehouse(c, b2)
    admin = mk.user(c, role=UserRole.admin, branch=b1)      # birinchi admin — 1-filial xodimi
    cust = Customer(name="Mijoz T15", phone="998900001500", company_id=c.id, branch_id=b2.id)
    db.add(cust)
    db.flush()
    prod = _product(db, c)
    _stock(db, prod, w1, 10)
    _stock(db, prod, w2, 10)
    return c, b1, b2, w1, w2, admin, cust, prod


def _mk_order(db, c, cust, branch, prod, group, qty=1):
    from app.models.order import Order, OrderStatus
    o = Order(company_id=c.id, customer_id=cust.id, branch_id=branch.id, product_id=prod.id, quantity=qty,
              unit_price=Decimal("1000"), total_amount=Decimal("1000") * qty, status=OrderStatus.delivered,
              order_group_id=group, payment_type="debt")
    db.add(o)
    db.flush()
    return o


def test_order_to_sale_uses_order_branch_warehouse(db, mk):
    """Mezon 5: Order.branch_id=2-filial -> avto-sotuv 2-filial omboridan, 1-filial qoldig'i o'zgarmaydi."""
    from app.models.sale import Sale
    from app.services.order_to_sale import maybe_create_sale_for_delivered_group
    c, b1, b2, w1, w2, admin, cust, prod = _order_env(db, mk)
    o = _mk_order(db, c, cust, b2, prod, "g-t15-1", qty=2)
    maybe_create_sale_for_delivered_group(db, [o])
    sale = db.query(Sale).filter(Sale.id == o.sale_id).one()
    assert sale.warehouse_id == w2.id
    assert _qty(db, prod, w2) == Decimal("8")
    assert _qty(db, prod, w1) == Decimal("10")


def test_order_to_sale_branch_without_warehouse_does_not_touch_other_branch(db, mk):
    from app.services.order_to_sale import maybe_create_sale_for_delivered_group
    c, b1, b2, w1, w2, admin, cust, prod = _order_env(db, mk)
    b3 = mk.branch(c)                                       # ombori yo'q filial
    o = _mk_order(db, c, cust, b3, prod, "g-t15-2")
    maybe_create_sale_for_delivered_group(db, [o])          # xato yutiladi (admin botga xabar)
    assert o.sale_id is None
    assert _qty(db, prod, w1) == Decimal("10") and _qty(db, prod, w2) == Decimal("10")


# ───────────────────────── agent ─────────────────────────

def _agent_env(db, mk):
    from app.models.customer import Customer
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    w1 = mk.warehouse(c, b1, type=WarehouseType.main)
    ret1 = mk.warehouse(c, b1, type=WarehouseType.returns)
    w2 = mk.warehouse(c, b2, type=WarehouseType.main)
    raw2 = mk.warehouse(c, b2, type=WarehouseType.raw_material)
    agent = mk.user(c, role=UserRole.agent, branch=b1)
    cust = Customer(name="Agent mijozi", phone="998900001501", company_id=c.id, agent_id=agent.id)
    db.add(cust)
    db.flush()
    prod = _product(db, c)
    return c, b1, b2, w1, ret1, w2, raw2, agent, cust, prod


def _order_in(cust, prod):
    from app.routers.mobile.agent import AgentOrderIn
    return AgentOrderIn(customer_id=cust.id, items=[{"product_id": prod.id, "quantity": 2}], delivery=False)


def test_agent_order_goes_to_agent_branch_main_not_returns(db, mk):
    from app.models.sale import Sale
    from app.routers.mobile.agent import create_order
    c, b1, b2, w1, ret1, w2, raw2, agent, cust, prod = _agent_env(db, mk)
    out = create_order(_order_in(cust, prod), db=db, current_user=agent, idempotency_key=None)
    assert db.query(Sale).filter(Sale.id == out["id"]).one().warehouse_id == w1.id


def test_agent_order_goes_to_customer_branch_when_agent_may_serve_it(db, mk):
    """Mijozning filiali bo'lsa — mijoz filiali ombori (agent shu filialga ruxsatli bo'lsa)."""
    from app.models.sale import Sale
    from app.models.user_branch import UserBranch
    from app.routers.mobile.agent import create_order
    c, b1, b2, w1, ret1, w2, raw2, agent, cust, prod = _agent_env(db, mk)
    db.add(UserBranch(user_id=agent.id, company_id=c.id, branch_id=b2.id))
    cust.branch_id = b2.id
    db.flush()
    out = create_order(_order_in(cust, prod), db=db, current_user=agent, idempotency_key=None)
    assert db.query(Sale).filter(Sale.id == out["id"]).one().warehouse_id == w2.id


def test_agent_order_branch_without_warehouse_409(db, mk):
    from app.routers.mobile.agent import create_order
    c, b1, b2, w1, ret1, w2, raw2, agent, cust, prod = _agent_env(db, mk)
    w1.type = WarehouseType.transit          # agent filialida savdo ombori qolmadi
    db.flush()
    with pytest.raises(HTTPException) as e:
        create_order(_order_in(cust, prod), db=db, current_user=agent, idempotency_key=None)
    assert e.value.status_code == 409


def test_agent_catalog_only_main_shop_warehouses(db, mk):
    """Mezon 6: katalog qoldig'i faqat agent filialining faol main/shop omborlari yig'indisi."""
    from app.routers.mobile.agent import catalog
    c, b1, b2, w1, ret1, w2, raw2, agent, cust, prod = _agent_env(db, mk)
    shop = mk.warehouse(c, b1, type=WarehouseType.shop)
    _stock(db, prod, w1, 3)
    _stock(db, prod, shop, 4)
    _stock(db, prod, ret1, 20)       # returns — kirmaydi
    _stock(db, prod, w2, 40)         # boshqa filial — kirmaydi
    _stock(db, prod, raw2, 5)
    row = next(r for r in catalog(db=db, current_user=agent) if r["id"] == prod.id)
    assert row["stock"] == 7.0


def test_agent_created_customer_gets_agent_branch(db, mk):
    from app.routers.mobile.agent import NewCustomerIn, add_customer
    c, b1, b2, w1, ret1, w2, raw2, agent, cust, prod = _agent_env(db, mk)
    out = add_customer(NewCustomerIn(name="Yangi mijoz", phone="998900001599"), db=db,
                       current_user=agent, idempotency_key=None)
    from app.models.customer import Customer
    assert db.query(Customer).filter(Customer.id == out["id"]).one().branch_id == b1.id


# ───────────────────────── field_staff / receivable_wallets ─────────────────────────

def test_field_staff_assign_customers_branch_match(db, mk, client):
    from app.models.customer import Customer
    c = mk.company(distribution_enabled=True)
    b1, b2 = mk.branch(c), mk.branch(c)
    agent = mk.user(c, role=UserRole.agent, branch=b1)
    admin = mk.user(c, role=UserRole.admin)
    ok = Customer(name="Mos", phone="998900001601", company_id=c.id, branch_id=b1.id)
    free = Customer(name="Filialsiz", phone="998900001602", company_id=c.id, branch_id=None)
    bad = Customer(name="Boshqa", phone="998900001603", company_id=c.id, branch_id=b2.id)
    db.add_all([ok, free, bad])
    db.flush()
    cl = client.login(admin)
    r = cl.post(f"/api/field-staff/agents/{agent.id}/customers", json={"add": [bad.id]})
    assert r.status_code == 400, r.text
    db.refresh(bad)
    assert bad.agent_id is None
    r = cl.post(f"/api/field-staff/agents/{agent.id}/customers", json={"add": [ok.id, free.id]})
    assert r.status_code == 200 and r.json()["added"] == 2


def test_field_staff_staff_filtered_by_branch(db, mk):
    from app.core.branch_context import build_branch_context
    from app.routers.field_staff import _staff
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    a1 = mk.user(c, role=UserRole.agent, branch=b1)
    a2 = mk.user(c, role=UserRole.courier, branch=b2)
    admin = mk.user(c, role=UserRole.admin)
    mgr = mk.user(c, role=UserRole.manager, branch=b1)
    assert {u.id for u in _staff(db, c.id, build_branch_context(db, admin))} == {a1.id, a2.id}
    assert {u.id for u in _staff(db, c.id, build_branch_context(db, admin, b2.id))} == {a2.id}
    assert {u.id for u in _staff(db, c.id, build_branch_context(db, mgr))} == {a1.id}


def test_receivable_wallets_agent_branch_or_branchless(db, mk):
    from app.models.moliya import Wallet
    from app.services.mobile_service import receivable_wallets
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    agent = mk.user(c, role=UserRole.agent, branch=b1)
    w1 = Wallet(name="A kassa", type="cash", company_id=c.id, branch_id=b1.id, is_active=True)
    w2 = Wallet(name="B kassa", type="cash", company_id=c.id, branch_id=b2.id, is_active=True)
    w0 = Wallet(name="Umumiy", type="cash", company_id=c.id, branch_id=None, is_active=True)
    db.add_all([w1, w2, w0])
    db.flush()
    # T3.14: boshqa filial kassasi ham qaytadi (topshirish tasdiq talab qiladi), lekin tartib:
    # xodim filiali -> filialsiz -> qolgan filiallar
    ids = [w.id for w in receivable_wallets(db, agent)]
    assert ids == [w1.id, w0.id, w2.id]


# ───────────────────────── products / inventory / import ─────────────────────────

def _prod_body(**kw):
    n = next(_n)
    return {"name": f"Yangi T15 {n}", "barcode": f"NB15{n:08d}", "sale_price": 1000, "cost_price": 500, **kw}


def test_create_product_initial_stock_goes_to_branch_default(db, mk, client):
    """Mezon 7: initial_stock=20 -> kassir filialining default omborida 20."""
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    w_other = mk.warehouse(c, b1, type=WarehouseType.returns)    # eng kichik id, lekin returns
    w1 = mk.warehouse(c, b1, type=WarehouseType.main)
    w2 = mk.warehouse(c, b2, type=WarehouseType.main)
    wh_user = mk.user(c, role=UserRole.warehouse, branch=b1)
    r = client.login(wh_user).post("/api/products/", json=_prod_body(initial_stock=20))
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert db.query(StockLevel).filter_by(product_id=pid, warehouse_id=w1.id).one().quantity == Decimal("20")
    assert db.query(StockLevel).filter_by(product_id=pid).count() == 1
    # berilgan ombor (8-mezon): aynan o'sha omborga; boshqa filial ombori kassir/omborchi uchun 403
    r = client.login(wh_user).post("/api/products/", json=_prod_body(initial_stock=5, initial_warehouse_id=w_other.id))
    assert r.status_code == 201, r.text
    assert _qty(db, db.get(Product, r.json()["id"]), w_other) == Decimal("5")
    assert client.login(wh_user).post("/api/products/", json=_prod_body(initial_stock=5, initial_warehouse_id=w2.id)).status_code == 403


def test_create_product_foreign_warehouse_404_and_no_warehouse_409(db, mk, client):
    c, b, w, admin = mk.tenant(UserRole.admin)
    other_c = mk.company()
    foreign = mk.warehouse(other_c, mk.branch(other_c))
    cl = client.login(admin)
    assert cl.post("/api/products/", json=_prod_body(initial_stock=3, initial_warehouse_id=foreign.id)).status_code == 404
    # qoldiqsiz mahsulot ombor talab qilmaydi
    c2 = mk.company()
    mk.branch(c2)
    admin2 = mk.user(c2, role=UserRole.admin)
    cl2 = client.login(admin2)
    assert cl2.post("/api/products/", json=_prod_body()).status_code == 201
    r = cl2.post("/api/products/", json=_prod_body(initial_stock=3))
    assert r.status_code == 409, r.text


def test_inventory_receive_branch_default_and_choose_warehouse(db, mk, client):
    """Mezon 9: /inventory/receive ombor berilmasa filial default ombori; 2+ filialda filial aniq emas -> 400."""
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    w_first = mk.warehouse(c, b2, type=WarehouseType.main)      # korxonaning eng kichik id li ombori
    w1 = mk.warehouse(c, b1, type=WarehouseType.main)
    wh_user = mk.user(c, role=UserRole.warehouse, branch=b1)
    admin = mk.user(c, role=UserRole.admin)
    prod = _product(db, c)
    body = {"items": [{"product_id": prod.id, "quantity": 5}]}
    r = client.login(wh_user).post("/api/inventory/receive", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["warehouse_id"] == w1.id
    assert _qty(db, prod, w1) == Decimal("5") and _qty(db, prod, w_first) is None
    r = client.login(admin).post("/api/inventory/receive", json=body)
    assert r.status_code == 400 and r.json()["detail"] == "Omborni tanlang"
    r = client.login(admin).post("/api/inventory/receive", json=body, headers={"X-Branch-Id": str(b2.id)})
    assert r.status_code == 200 and r.json()["warehouse_id"] == w_first.id


def test_bulk_import_uses_chosen_or_branch_default_warehouse(db, mk, client):
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    w_first = mk.warehouse(c, b2, type=WarehouseType.main)
    w1 = mk.warehouse(c, b1, type=WarehouseType.main)
    w1b = mk.warehouse(c, b1, type=WarehouseType.shop)
    user = mk.user(c, role=UserRole.warehouse, branch=b1)

    def row():
        n = next(_n)
        return {"Nomi": f"Import T15 {n}", "Barkod": f"IM15{n:08d}", "Chakana narxi": 1000, "Qoldiq": 7}

    cl = client.login(user)
    r = cl.post("/api/products/bulk-import", json=[row()])
    assert r.status_code == 200, r.text
    assert r.json()["warehouse_id"] == w1b.id          # filial default ombori (shop > main), w_first emas
    r = cl.post(f"/api/products/bulk-import?warehouse_id={w1.id}", json=[row()])
    assert r.status_code == 200 and r.json()["warehouse_id"] == w1.id
    assert db.query(StockLevel).filter(StockLevel.warehouse_id == w_first.id).count() == 0
    # boshqa filial ombori -> 403
    assert cl.post(f"/api/products/bulk-import?warehouse_id={w_first.id}", json=[row()]).status_code == 403


# ───────────────────────── korxonalararo izolyatsiya ─────────────────────────

def test_cross_company_isolation_for_sale_warehouse(db, mk):
    ca, ba, wa, ua = mk.tenant(UserRole.cashier)
    cb, bb, wb, ub = mk.tenant(UserRole.cashier)
    prod = _product(db, ca)
    _stock(db, prod, wa, 5)
    # A kassiri B omborini so'ray olmaydi
    assert _status(create_sale, db, _sd(prod, warehouse_id=wb.id), ua) == 404
    assert _status(create_pending_sale, db, _sd(prod, warehouse_id=wb.id), ua) == 404
    # o'z resursi ishlaydi
    assert create_sale(db, _sd(prod, warehouse_id=wa.id), ua).warehouse_id == wa.id
    # A korxonasi uchun B filiali/ombori resolverda ko'rinmaydi
    assert _status(resolve_warehouse, db, ca.id, branch_id=bb.id) == 404
