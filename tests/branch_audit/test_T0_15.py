"""T0.15 — Sotuv detali/tahrir/o'chirish/chek uchun filial izolyatsiyasi.

Tekshiriladi: boshqa filial sotuvi (non-admin) -> 404, admin/director cheklanmaydi,
boshqa korxona -> 404, kassir bekor qila olmaydi (403) va faqat o'z ochiq smenasidagi
sotuvni tahrirlaydi, mobil rollar 403, cost_price kassirdan yashiriladi.
"""
from decimal import Decimal

import pytest
from sqlalchemy import func

from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.shift import Shift
from app.models.user import UserRole

_n = [0]


def _sale(db, company, cashier, warehouse, shift=None, status=SaleStatus.completed, product=None):
    _n[0] += 1
    s = Sale(number=f"T015{_n[0]:06d}", cashier_id=cashier.id, total_amount=Decimal("100"),
             paid_amount=Decimal("100"), payment_type=PaymentType.cash, status=status,
             company_id=company.id, warehouse_id=warehouse.id if warehouse else None,
             shift_id=shift.id if shift else None)
    db.add(s)
    db.flush()
    if product:
        db.add(SaleItem(sale_id=s.id, product_id=product.id, quantity=Decimal("2"),
                        unit_price=Decimal("50"), cost_price=Decimal("30"), subtotal=Decimal("100")))
        db.flush()
    return s


def _shift(db, company, branch, cashier, status="open"):
    sh = Shift(cashier_id=cashier.id, branch_id=branch.id, company_id=company.id, status=status)
    db.add(sh)
    db.flush()
    return sh


class W:
    pass


@pytest.fixture
def w(db, mk):
    o = W()
    o.c = mk.company()
    o.ba, o.bb = mk.branch(o.c), mk.branch(o.c)
    o.wa, o.wb = mk.warehouse(o.c, o.ba), mk.warehouse(o.c, o.bb)
    o.cash_a = mk.user(o.c, role=UserRole.cashier, branch=o.ba)
    o.cash_a2 = mk.user(o.c, role=UserRole.cashier, branch=o.ba)
    o.cash_b = mk.user(o.c, role=UserRole.cashier, branch=o.bb)
    o.mgr_a = mk.user(o.c, role=UserRole.manager, branch=o.ba)
    o.admin = mk.user(o.c, role=UserRole.admin, branch=o.ba)
    o.director = mk.user(o.c, role=UserRole.director)
    o.courier = mk.user(o.c, role=UserRole.courier, branch=o.ba)
    o.nobranch_mgr = mk.user(o.c, role=UserRole.manager)
    prod = Product(name="Tovar", sku="S1", barcode="B1", company_id=o.c.id)
    db.add(prod)
    db.flush()
    o.sh_a = _shift(db, o.c, o.ba, o.cash_a)
    o.sh_b = _shift(db, o.c, o.bb, o.cash_b)
    o.sale_a = _sale(db, o.c, o.cash_a, o.wa, o.sh_a, product=prod)
    o.sale_b = _sale(db, o.c, o.cash_b, o.wb, o.sh_b, product=prod)
    o.prod = prod
    # boshqa korxona
    o.c2, o.b2, o.w2, o.admin2 = mk.tenant()
    o.cash2 = mk.user(o.c2, role=UserRole.cashier, branch=o.b2)
    o.sale_2 = _sale(db, o.c2, o.cash2, o.w2)
    return o


def _call(client, user, method, path, **kw):
    return getattr(client.login(user), method)(path, **kw)


# (method, path-shablon, json)
ENDPOINTS = [
    ("get", "/api/sales/{id}", None),
    ("get", "/api/sales/{id}/receipt", None),
    ("put", "/api/sales/{id}", {"note": "x"}),
    ("patch", "/api/sales/{id}/fiscal", {"fiscal_sign": "ABC"}),
    ("post", "/api/sales/{id}/return-items", {"items": [{"sale_item_id": 1, "quantity": 1}]}),
    ("delete", "/api/sales/{id}", None),
]


def _req(client, user, ep, sale_id):
    method, path, body = ep
    kw = {"json": body} if body is not None else {}
    return _call(client, user, method, path.format(id=sale_id), **kw)


# ---------- boshqa filial -> 404 ----------

@pytest.mark.parametrize("ep", ENDPOINTS[:5], ids=lambda e: f"{e[0]} {e[1]}")
def test_cashier_other_branch_404(client, db, w, ep):
    r = _req(client, w.cash_a, ep, w.sale_b.id)
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Sotuv topilmadi"


def test_cashier_other_branch_data_unchanged(client, db, w):
    r = _call(client, w.cash_a, "put", f"/api/sales/{w.sale_b.id}", json={"note": "buzildi", "status": "cancelled"})
    assert r.status_code in (403, 404)
    db.refresh(w.sale_b)
    assert w.sale_b.note is None and w.sale_b.status == SaleStatus.completed


def test_assign_customer_other_branch_404(client, db, w):
    r = _call(client, w.cash_a, "put", f"/api/sales/{w.sale_b.id}/assign-customer", json={"customer_id": 1})
    assert r.status_code == 404


def test_manager_delete_other_branch_404(client, db, w):
    r = _call(client, w.mgr_a, "delete", f"/api/sales/{w.sale_b.id}")
    assert r.status_code == 404
    db.refresh(w.sale_b)
    assert w.sale_b.status == SaleStatus.completed


def test_manager_without_branch_cannot_see_others(client, w):
    r = _call(client, w.nobranch_mgr, "get", f"/api/sales/{w.sale_b.id}")
    assert r.status_code == 404


def test_legacy_sale_without_warehouse_only_own_cashier(client, db, w):
    legacy = _sale(db, w.c, w.cash_a, None)
    assert _call(client, w.cash_a, "get", f"/api/sales/{legacy.id}").status_code == 200
    assert _call(client, w.cash_a2, "get", f"/api/sales/{legacy.id}").status_code == 404
    assert _call(client, w.admin, "get", f"/api/sales/{legacy.id}").status_code == 200


# ---------- ijobiy yo'l ----------

def test_cashier_own_branch_get_and_receipt(client, w):
    assert _call(client, w.cash_a, "get", f"/api/sales/{w.sale_a.id}").status_code == 200
    assert _call(client, w.cash_a, "get", f"/api/sales/{w.sale_a.id}/receipt").status_code == 200


def test_manager_sees_branch_sale_of_other_cashier(client, w):
    r = _call(client, w.mgr_a, "get", f"/api/sales/{w.sale_a.id}")
    assert r.status_code == 200
    assert r.json()["items"][0]["cost_price"] is not None


@pytest.mark.parametrize("who", ["admin", "director"])
def test_admin_director_any_branch(client, w, who):
    u = getattr(w, who)
    for ep in ENDPOINTS[:2]:
        assert _req(client, u, ep, w.sale_b.id).status_code == 200
    r = _call(client, u, "put", f"/api/sales/{w.sale_b.id}", json={"note": "admin izohi"})
    assert r.status_code == 200, r.text
    assert r.json()["note"] == "admin izohi"


def test_manager_deletes_own_branch_sale(client, db, w):
    sid = w.sale_a.id
    r = _call(client, w.mgr_a, "delete", f"/api/sales/{sid}")
    assert r.status_code == 200, r.text
    # delete_sale sotuvni to'liq o'chiradi
    assert db.query(Sale).filter(Sale.id == sid).first() is None


# ---------- boshqa korxona ----------

@pytest.mark.parametrize("who", ["admin", "cash_a"])
def test_other_company_404(client, w, who):
    for ep in ENDPOINTS[:2]:
        assert _req(client, getattr(w, who), ep, w.sale_2.id).status_code == 404
    assert _call(client, w.admin, "put", f"/api/sales/{w.sale_2.id}", json={"note": "x"}).status_code == 404
    assert _call(client, w.admin, "delete", f"/api/sales/{w.sale_2.id}").status_code == 404


# ---------- kassir cheklovlari ----------

@pytest.mark.parametrize("st", ["cancelled", "refunded"])
def test_cashier_cannot_cancel(client, db, w, st):
    r = _call(client, w.cash_a, "put", f"/api/sales/{w.sale_a.id}", json={"status": st})
    assert r.status_code == 403
    assert "menejer" in r.json()["detail"]
    db.refresh(w.sale_a)
    assert w.sale_a.status == SaleStatus.completed


def test_cancel_keeps_sale_in_shift_expected_cash(client, db, w):
    def shift_total():
        return db.query(func.coalesce(func.sum(Sale.paid_amount), 0)).filter(
            Sale.shift_id == w.sh_a.id, Sale.status != SaleStatus.cancelled).scalar()
    before = shift_total()
    _call(client, w.cash_a, "put", f"/api/sales/{w.sale_a.id}", json={"status": "cancelled"})
    assert Decimal(str(shift_total())) == Decimal(str(before)) == Decimal("100")


def test_cashier_edits_own_open_shift_sale(client, db, w):
    r = _call(client, w.cash_a, "put", f"/api/sales/{w.sale_a.id}", json={"note": "oz izohi"})
    assert r.status_code == 200, r.text
    assert r.json()["note"] == "oz izohi"


def test_cashier_cannot_edit_other_cashier_sale_same_branch(client, db, w):
    r = _call(client, w.cash_a2, "put", f"/api/sales/{w.sale_a.id}", json={"note": "begona"})
    assert r.status_code == 403
    assert "ochiq smenangizdagi" in r.json()["detail"]
    db.refresh(w.sale_a)
    assert w.sale_a.note is None


def test_cashier_cannot_edit_closed_shift_sale(client, db, w):
    w.sh_a.status = "closed"
    db.flush()
    r = _call(client, w.cash_a, "put", f"/api/sales/{w.sale_a.id}", json={"note": "kech"})
    assert r.status_code == 403
    db.refresh(w.sale_a)
    assert w.sale_a.note is None


def test_cashier_cannot_edit_sale_without_shift(client, db, w):
    s = _sale(db, w.c, w.cash_a, w.wa, None)
    assert _call(client, w.cash_a, "put", f"/api/sales/{s.id}", json={"note": "x"}).status_code == 403


def test_cashier_edits_own_pending_any_shift(client, db, w):
    s = _sale(db, w.c, w.cash_a, w.wa, None, status=SaleStatus.pending)
    r = _call(client, w.cash_a, "put", f"/api/sales/{s.id}", json={"note": "ulgurji"})
    assert r.status_code == 200, r.text


def test_cashier_cannot_edit_other_cashier_pending(client, db, w):
    s = _sale(db, w.c, w.cash_a, w.wa, None, status=SaleStatus.pending)
    assert _call(client, w.cash_a2, "put", f"/api/sales/{s.id}", json={"note": "x"}).status_code == 403


def test_manager_can_cancel_in_branch(client, db, w):
    r = _call(client, w.mgr_a, "put", f"/api/sales/{w.sale_a.id}", json={"status": "cancelled"})
    assert r.status_code == 200, r.text


# ---------- mobil rollar ----------

def test_courier_forbidden(client, w):
    for ep in ENDPOINTS[:2]:
        assert _req(client, w.courier, ep, w.sale_a.id).status_code == 403
    assert _call(client, w.courier, "get", "/api/sales/").status_code == 403


# ---------- cost_price ----------

def test_cost_price_hidden_for_cashier(client, w):
    r = _call(client, w.cash_a, "get", f"/api/sales/{w.sale_a.id}")
    assert r.status_code == 200
    assert all(i["cost_price"] is None for i in r.json()["items"])
    # PUT javobida ham yashirin
    r = _call(client, w.cash_a, "put", f"/api/sales/{w.sale_a.id}", json={"note": "n"})
    assert all(i["cost_price"] is None for i in r.json()["items"])


@pytest.mark.parametrize("who", ["admin", "mgr_a"])
def test_cost_price_visible_for_admin_manager(client, w, who):
    r = _call(client, getattr(w, who), "get", f"/api/sales/{w.sale_a.id}")
    assert Decimal(str(r.json()["items"][0]["cost_price"])) == Decimal("30")


# ---------- list_sales regressiya ----------

def test_list_sales_branch_scope_unchanged(client, w):
    ids = {s["id"] for s in _call(client, w.cash_a, "get", "/api/sales/").json()}
    assert w.sale_a.id in ids and w.sale_b.id not in ids
    ids = {s["id"] for s in _call(client, w.admin, "get", "/api/sales/").json()}
    assert {w.sale_a.id, w.sale_b.id} <= ids and w.sale_2.id not in ids
