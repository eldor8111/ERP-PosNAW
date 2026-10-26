"""T1.1 — Yagona joriy filial konteksti (X-Branch-Id header, get_branch_context, rol qoidasi).

Qabul mezonlari 1-7 va korxonalararo izolyatsiya.
"""
from decimal import Decimal

import pytest

from app.core.branch_context import (
    BRANCH_BYPASS_ROLES, BranchContext, build_branch_context, effective_branch_id,
)
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.sale import PaymentType, Sale
from app.models.shift import Shift
from app.models.user import UserRole

H = "X-Branch-Id"


# ───────────────────────── yordamchilar ─────────────────────────

def _sale(db, company, cashier, warehouse, number):
    s = Sale(number=number, cashier_id=cashier.id, total_amount=Decimal("10"), paid_amount=Decimal("10"),
             payment_type=PaymentType.cash, company_id=company.id,
             warehouse_id=warehouse.id if warehouse else None)
    db.add(s)
    db.flush()
    return s


def _shift(db, company, cashier, branch):
    s = Shift(cashier_id=cashier.id, branch_id=branch.id if branch else None,
              company_id=company.id, status="closed")
    db.add(s)
    db.flush()
    return s


def _product(db, company, name):
    p = Product(name=name, sku=f"SKU-{name}", barcode=f"BC-{name}", company_id=company.id)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty):
    db.add(StockLevel(product_id=product.id, warehouse_id=warehouse.id, quantity=Decimal(qty)))
    db.flush()


@pytest.fixture
def two(mk, db):
    """A korxona: 2 faol filial (a1, a2) + har birida ombor + biriktirilmagan ombor;
    B korxona: 1 filial + ombor. Rollar bo'yicha foydalanuvchilar."""
    a = mk.company("A")
    a1 = mk.branch(a, "A-1")
    a2 = mk.branch(a, "A-2")
    wa1 = mk.warehouse(a, a1, "WA1")
    wa2 = mk.warehouse(a, a2, "WA2")
    wa0 = mk.warehouse(a, None, "WA0")
    b = mk.company("B")
    b1 = mk.branch(b, "B-1")
    wb1 = mk.warehouse(b, b1, "WB1")
    users = dict(
        admin_a=mk.user(a, role=UserRole.admin, branch=a1),
        cashier_a1=mk.user(a, role=UserRole.cashier, branch=a1),
        cashier_a_none=mk.user(a, role=UserRole.cashier, branch=None),
        manager_a_none=mk.user(a, role=UserRole.manager, branch=None),
        admin_b=mk.user(b, role=UserRole.admin, branch=b1),
        cashier_b_none=mk.user(b, role=UserRole.cashier, branch=None),
        sa=mk.user(None, role=UserRole.super_admin),
    )
    # Sotuvlar: A da har filialdan bittadan, B da bitta
    _sale(db, a, users["cashier_a1"], wa1, "S-A1")
    _sale(db, a, users["admin_a"], wa2, "S-A2")
    _sale(db, b, users["admin_b"], wb1, "S-B1")
    # Smenalar
    _shift(db, a, users["cashier_a1"], a1)
    _shift(db, a, users["admin_a"], a2)
    _shift(db, b, users["admin_b"], b1)
    return dict(a=a, a1=a1, a2=a2, wa1=wa1, wa2=wa2, wa0=wa0, b=b, b1=b1, wb1=wb1, **users)


def _ids(resp):
    data = resp.json()
    items = data["items"] if isinstance(data, dict) else data
    return sorted(i["id"] for i in items)


# ───────────────────────── 1-2: admin /warehouses ─────────────────────────

def test_admin_without_header_sees_all_company_warehouses(client, two):
    r = client.login(two["admin_a"]).get("/api/warehouses")
    assert r.status_code == 200
    assert _ids(r) == sorted([two["wa1"].id, two["wa2"].id, two["wa0"].id])
    # /inventory/warehouses ham xuddi shunday
    r2 = client.login(two["admin_a"]).get("/api/inventory/warehouses")
    assert r2.status_code == 200
    assert _ids(r2) == _ids(r)


def test_admin_header_filters_to_branch_and_foreign_branch_404(client, two):
    cl = client.login(two["admin_a"])
    r = cl.get("/api/warehouses", headers={H: str(two["a2"].id)})
    assert r.status_code == 200
    assert _ids(r) == [two["wa2"].id]
    r = cl.get("/api/inventory/warehouses", headers={H: str(two["a2"].id)})
    assert _ids(r) == [two["wa2"].id]
    # Boshqa korxona filiali → 404
    r = cl.get("/api/warehouses", headers={H: str(two["b1"].id)})
    assert r.status_code == 404
    assert r.json()["detail"] == "Filial topilmadi"
    # Son emas → 400
    assert cl.get("/api/warehouses", headers={H: "abc"}).status_code == 400
    # Bo'sh header = header yo'q
    assert _ids(cl.get("/api/warehouses", headers={H: ""})) == _ids(cl.get("/api/warehouses"))


def test_admin_header_inactive_branch_404(client, two, mk):
    off = mk.branch(two["a"], "Yopiq", is_active=False)
    r = client.login(two["admin_a"]).get("/api/warehouses", headers={H: str(off.id)})
    assert r.status_code == 404


# ───────────────────────── 3: cashier header ─────────────────────────

def test_cashier_assigned_other_branch_header_403(client, two):
    cl = client.login(two["cashier_a1"])
    r = cl.get("/api/warehouses", headers={H: str(two["a2"].id)})
    assert r.status_code == 403
    assert r.json()["detail"] == "Bu filialga ruxsat yo'q"
    # Boshqa korxona filiali ham 403 (mavjudligi oshkor qilinmaydi)
    assert cl.get("/api/warehouses", headers={H: str(two["b1"].id)}).status_code == 403
    # O'z filiali — ishlaydi, faqat o'z ombori
    r = cl.get("/api/warehouses", headers={H: str(two["a1"].id)})
    assert r.status_code == 200 and _ids(r) == [two["wa1"].id]
    # Header'siz ham faqat o'z filiali
    assert _ids(cl.get("/api/warehouses")) == [two["wa1"].id]
    assert _ids(cl.get("/api/sales/")) == _ids(client.login(two["cashier_a1"]).get("/api/sales/"))
    sales = cl.get("/api/sales/").json()
    assert [s["number"] for s in sales] == ["S-A1"]
    shifts = cl.get("/api/shifts").json()
    assert {s["branch_id"] for s in shifts} == {two["a1"].id}


# ───────────────────────── 4: filialsiz cashier ─────────────────────────

def test_unassigned_cashier_two_branches_sees_nothing_and_needs_assignment(client, two):
    cl = client.login(two["cashier_a_none"])
    assert cl.get("/api/sales/").json() == []
    assert cl.get("/api/sales/", params={"with_total": "true"}).json() == {
        "items": [], "total": 0, "sum_total": 0, "sum_paid": 0, "sum_debt": 0}
    assert cl.get("/api/shifts").json() == []
    assert cl.get("/api/warehouses").json() == []
    ctx = cl.get("/api/branches/my-context")
    assert ctx.status_code == 200
    d = ctx.json()
    assert d["needs_branch_assignment"] is True
    assert d["branches"] == [] and d["current_branch_id"] is None and d["assigned_branch_id"] is None
    assert d["can_switch"] is False and d["can_select_all"] is False
    # Header bilan ham ruxsat yo'q
    assert cl.get("/api/warehouses", headers={H: str(two["a1"].id)}).status_code == 403


def test_unassigned_cashier_single_branch_company_auto_detects(client, two):
    cl = client.login(two["cashier_b_none"])
    d = cl.get("/api/branches/my-context").json()
    assert d["needs_branch_assignment"] is False
    assert d["current_branch_id"] == two["b1"].id
    assert d["assigned_branch_id"] is None
    assert [b["id"] for b in d["branches"]] == [two["b1"].id]
    assert _ids(cl.get("/api/warehouses")) == [two["wb1"].id]
    assert [s["number"] for s in cl.get("/api/sales/").json()] == ["S-B1"]
    # T1.11: kassir faqat o'z smenalarini ko'radi (bu kassirning smenasi yo'q)
    assert cl.get("/api/shifts").json() == []
    # Boshqa filial header'i → 403
    assert cl.get("/api/warehouses", headers={H: str(two["a1"].id)}).status_code == 403


# ───────────────────────── 5: filialsiz manager ─────────────────────────

def test_unassigned_manager_sees_all_branches(client, two):
    cl = client.login(two["manager_a_none"])
    assert sorted(s["number"] for s in cl.get("/api/sales/").json()) == ["S-A1", "S-A2"]
    # T1.11: filiali bo'lmagan manager smenalarda faqat o'zinikini ko'radi (bunda smenasi yo'q)
    assert cl.get("/api/shifts").json() == []
    d = cl.get("/api/branches/my-context").json()
    assert d["can_select_all"] is True and d["can_switch"] is True
    assert d["needs_branch_assignment"] is False
    assert [b["id"] for b in d["branches"]] == sorted([two["a1"].id, two["a2"].id])
    # Header bilan bitta filialga torayadi; boshqa korxona filiali 404
    assert [s["number"] for s in cl.get("/api/sales/", headers={H: str(two["a2"].id)}).json()] == ["S-A2"]
    assert cl.get("/api/sales/", headers={H: str(two["b1"].id)}).status_code == 404


# ───────────────────────── 6: super_admin ─────────────────────────

def test_super_admin_shifts_branch_param_works_and_header_ignored(client, two):
    cl = client.login(two["sa"])
    all_ids = {s["branch_id"] for s in cl.get("/api/shifts").json()}
    assert {two["a1"].id, two["a2"].id, two["b1"].id} <= all_ids
    r = cl.get("/api/shifts", params={"branch_id": two["a2"].id})
    assert {s["branch_id"] for s in r.json()} == {two["a2"].id}
    # Header e'tiborsiz — xato ham bermaydi, filtr ham qo'llanmaydi
    r = cl.get("/api/shifts", headers={H: "999999"})
    assert r.status_code == 200 and {s["branch_id"] for s in r.json()} == all_ids
    d = cl.get("/api/branches/my-context").json()
    assert d["can_switch"] is False and d["can_select_all"] is True


def test_admin_shifts_and_sales_header_vs_explicit_param(client, two):
    cl = client.login(two["admin_a"])
    # Header'siz hammasi (admin endi o'z filialiga qamalmagan)
    assert {s["branch_id"] for s in cl.get("/api/shifts").json()} == {two["a1"].id, two["a2"].id}
    assert sorted(s["number"] for s in cl.get("/api/sales/").json()) == ["S-A1", "S-A2"]
    # Header
    assert {s["branch_id"] for s in cl.get("/api/shifts", headers={H: str(two["a1"].id)}).json()} == {two["a1"].id}
    assert [s["number"] for s in cl.get("/api/sales/", headers={H: str(two["a1"].id)}).json()] == ["S-A1"]
    # Aniq parametr header'dan ustun
    r = cl.get("/api/shifts", params={"branch_id": two["a2"].id}, headers={H: str(two["a1"].id)})
    assert {s["branch_id"] for s in r.json()} == {two["a2"].id}
    r = cl.get("/api/sales/", params={"branch_id": two["a2"].id}, headers={H: str(two["a1"].id)})
    assert [s["number"] for s in r.json()] == ["S-A2"]
    # Non-bypass uchun ruxsat doirasidan tashqari `?branch_id=` e'tiborsiz (eski xatti-harakat)
    r = client.login(two["cashier_a1"]).get("/api/shifts", params={"branch_id": two["a2"].id})
    assert {s["branch_id"] for s in r.json()} == {two["a1"].id}


# ───────────────────────── 7: omborsiz filial, /products/paginated ─────────────────────────

def test_products_paginated_empty_branch_warehouse_set_filters_consistently(client, two, db, mk):
    a3 = mk.branch(two["a"], "A-3 (omborsiz)")
    cashier = mk.user(two["a"], role=UserRole.cashier, branch=a3)
    p_stock = _product(db, two["a"], "bor")
    p_zero = _product(db, two["a"], "yoq")
    _stock(db, p_stock, two["wa1"], 5)
    cl = client.login(cashier)
    r = cl.get("/api/products/paginated", params={"stock_status": "qolmagan", "limit": 100})
    assert r.status_code == 200
    names = sorted(i["name"] for i in r.json()["items"])
    # Ko'rsatiladigan qoldiq 0 — ikkalasi ham "qolmagan" ro'yxatida (MODEL-22)
    assert names == ["bor", "yoq"]
    for i in r.json()["items"]:
        assert i["warehouse_stocks"] == []
    # Admin uchun esa "bor" qolmagan emas
    r = client.login(two["admin_a"]).get("/api/products/paginated", params={"stock_status": "qolmagan", "limit": 100})
    assert sorted(i["name"] for i in r.json()["items"]) == ["yoq"]


def test_products_list_admin_header_limits_visible_stocks(client, two, db):
    p = _product(db, two["a"], "ikki-ombor")
    _stock(db, p, two["wa1"], 3)
    _stock(db, p, two["wa2"], 7)
    cl = client.login(two["admin_a"])
    r = cl.get("/api/products/", params={"limit": 100})
    item = next(i for i in r.json() if i["name"] == "ikki-ombor")
    assert sorted(s["warehouse_id"] for s in item["warehouse_stocks"]) == sorted([two["wa1"].id, two["wa2"].id])
    r = cl.get("/api/products/", params={"limit": 100}, headers={H: str(two["a2"].id)})
    item = next(i for i in r.json() if i["name"] == "ikki-ombor")
    assert [s["warehouse_id"] for s in item["warehouse_stocks"]] == [two["wa2"].id]
    # B korxona admini A tovarini umuman ko'rmaydi
    r = client.login(two["admin_b"]).get("/api/products/", params={"limit": 100})
    assert all(i["name"] != "ikki-ombor" for i in r.json())


# ───────────────────────── /branches/my-context ─────────────────────────

def test_my_context_admin_and_assigned_cashier(client, two):
    d = client.login(two["admin_a"]).get("/api/branches/my-context").json()
    assert d["current_branch_id"] is None and d["assigned_branch_id"] == two["a1"].id
    assert d["can_select_all"] is True and d["can_switch"] is True
    assert [b["id"] for b in d["branches"]] == sorted([two["a1"].id, two["a2"].id])
    d = client.login(two["admin_a"]).get("/api/branches/my-context", headers={H: str(two["a2"].id)}).json()
    assert d["current_branch_id"] == two["a2"].id
    d = client.login(two["cashier_a1"]).get("/api/branches/my-context").json()
    assert d["current_branch_id"] == two["a1"].id and d["assigned_branch_id"] == two["a1"].id
    assert d["can_switch"] is False and d["can_select_all"] is False
    assert [b["id"] for b in d["branches"]] == [two["a1"].id]


def test_my_context_is_not_shadowed_by_branch_id_route(client, two):
    # "my-context" int ga tushmasligi kerak (422 emas)
    r = client.login(two["admin_a"]).get("/api/branches/my-context")
    assert r.status_code == 200
    # /{branch_id} hali ham ishlaydi
    assert client.login(two["admin_a"]).get(f"/api/branches/{two['a1'].id}").status_code == 200


# ───────────────────────── izolyatsiya ─────────────────────────

def test_company_isolation_header_and_lists(client, two):
    a = client.login(two["admin_a"])
    assert a.get("/api/warehouses", headers={H: str(two["b1"].id)}).status_code == 404
    assert a.get("/api/shifts", headers={H: str(two["b1"].id)}).status_code == 404
    assert a.get("/api/sales/", headers={H: str(two["b1"].id)}).status_code == 404
    b = client.login(two["admin_b"])
    assert [s["number"] for s in b.get("/api/sales/").json()] == ["S-B1"]
    assert _ids(b.get("/api/warehouses")) == [two["wb1"].id]
    assert [x["id"] for x in b.get("/api/branches/my-context").json()["branches"]] == [two["b1"].id]
    # A korxona filialidagi `?branch_id=` B admin uchun bo'sh (korxona filtri)
    assert b.get("/api/shifts", params={"branch_id": two["a1"].id}).json() == []


def test_user_branch_from_other_company_is_ignored(client, two, mk):
    """Ko'p korxonali foydalanuvchi: users.branch_id boshqa korxona filialiga ishora qilsa —
    biriktirilmagan deb hisoblanadi (B korxonada 1 filial → avto-aniqlash)."""
    u = mk.user(two["b"], role=UserRole.cashier, branch=two["a1"])
    cl = client.login(u)
    d = cl.get("/api/branches/my-context").json()
    assert d["assigned_branch_id"] is None and d["current_branch_id"] == two["b1"].id
    assert _ids(cl.get("/api/warehouses")) == [two["wb1"].id]


# ───────────────────────── POST /shifts/open ─────────────────────────

def test_open_shift_non_bypass_forced_to_own_branch(client, two):
    cl = client.login(two["cashier_a1"])
    r = cl.post("/api/shifts/open", json={"opening_cash": 0, "branch_id": two["a2"].id})
    assert r.status_code == 403
    r = cl.post("/api/shifts/open", json={"opening_cash": 0})
    assert r.status_code == 201 and r.json()["branch_id"] == two["a1"].id


def test_open_shift_bypass_uses_header_and_validates_company(client, two):
    cl = client.login(two["admin_a"])
    r = cl.post("/api/shifts/open", json={"opening_cash": 0}, headers={H: str(two["a2"].id)})
    assert r.status_code == 201 and r.json()["branch_id"] == two["a2"].id
    cl2 = client.login(two["admin_b"])
    r = cl2.post("/api/shifts/open", json={"opening_cash": 0, "branch_id": two["a1"].id})
    assert r.status_code == 400
    # Bypass + boshqa korxona header'i → 404 (kontekst darajasida)
    assert cl2.post("/api/shifts/open", json={"opening_cash": 0}, headers={H: str(two["a1"].id)}).status_code == 404


# ───────────────────────── birlik: build_branch_context / effective_branch_id ─────────────────────────

def test_bypass_roles_constant_and_context_unit(db, two):
    assert set(BRANCH_BYPASS_ROLES) == {UserRole.admin, UserRole.director, UserRole.super_admin}
    ctx = build_branch_context(db, two["admin_a"])
    assert ctx == BranchContext(None, None, True, False, two["admin_a"].id)
    ctx = build_branch_context(db, two["cashier_a1"])
    assert ctx.branch_id == two["a1"].id and ctx.allowed_branch_ids == frozenset({two["a1"].id})
    assert ctx.bypass is False and ctx.needs_assignment is False
    ctx = build_branch_context(db, two["cashier_a_none"])
    assert ctx.allowed_branch_ids == frozenset() and ctx.needs_assignment is True
    ctx = build_branch_context(db, two["manager_a_none"])
    assert ctx.unrestricted and ctx.bypass is False
    # ORM user mutatsiya qilinmaydi
    assert two["admin_a"].branch_id == two["a1"].id


def test_effective_branch_id_prefers_request_context(client, db, two):
    # Kontekst yo'q → users.branch_id (faqat o'z korxonasiniki)
    assert effective_branch_id(db, two["admin_a"]) == two["a1"].id
    assert effective_branch_id(db, two["cashier_a_none"]) is None
    # So'rovdan keyin db.info["branch_ctx"] shu foydalanuvchi uchun ishlatiladi
    client.login(two["admin_a"]).get("/api/warehouses", headers={H: str(two["a2"].id)})
    assert isinstance(db.info.get("branch_ctx"), BranchContext)
    assert effective_branch_id(db, two["admin_a"]) == two["a2"].id
    # Boshqa foydalanuvchi uchun begona kontekst ishlatilmaydi
    assert effective_branch_id(db, two["cashier_a1"]) == two["a1"].id
