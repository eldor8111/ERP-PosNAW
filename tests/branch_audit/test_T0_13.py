"""T0.13 — Sotuvda warehouse_id ni korxona/filial/faollik bo'yicha tekshirish.

Qamrov: create (sarlavha va qator ombori), pending, return, update (teskari ta'sirdan oldin),
begona korxona/nofaol ombor, boshqa filial (kassir 403, admin ruxsat), avto-tanlash korxona filtri,
resolve_branch_id, ijobiy yo'l.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T0_13.py -q -p no:cacheprovider
"""
import itertools
from decimal import Decimal

import pytest

from app.models.inventory import StockLevel
from app.models.moliya import KassaSession, Wallet
from app.models.product import Product
from app.models.sale import Sale
from app.models.user import UserRole, UserWallet
from app.schemas.sale import SaleCreate
from app.services.sale_create import create_sale
from app.services.sale_helpers import resolve_branch_id, validate_sale_warehouse, validate_sale_warehouses

_seq = itertools.count(1)


def _wallet(db, company, branch):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal("0"), company_id=company.id,
               branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


def _product(db, company, wh=None, qty=100):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T013-{n}", barcode=f"B013-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    if wh is not None:
        db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
        db.flush()
    return p


def _body(p, wh_id=None, item_wh_id=None, qty=1):
    item = {"product_id": p.id, "quantity": qty, "unit_price": 1000}
    if item_wh_id is not None:
        item["warehouse_id"] = item_wh_id
    body = {"items": [item], "payment_type": "cash", "paid_amount": 1000 * qty,
            "paid_cash": 1000 * qty, "payments": [{"type": "cash", "amount": 1000 * qty}]}
    if wh_id is not None:
        body["warehouse_id"] = wh_id
    return body


def _stock_rows(db, p):
    return db.query(StockLevel).filter(StockLevel.product_id == p.id).count()


def _qty(db, p, wh):
    row = db.query(StockLevel).filter(StockLevel.product_id == p.id, StockLevel.warehouse_id == wh.id).first()
    return Decimal(str(row.quantity)) if row else None


@pytest.fixture
def w(db, mk):
    """Korxona A: 2 filial (A1, A2), omborlar, admin, A1 kassiri, nofaol ombor; korxona B."""
    ca = mk.company()
    ba1, ba2 = mk.branch(ca), mk.branch(ca)
    wa1 = mk.warehouse(ca, ba1)
    wa2 = mk.warehouse(ca, ba2)
    wa_off = mk.warehouse(ca, ba1, is_active=False)
    admin = mk.user(ca, role=UserRole.admin, branch=ba1)
    cashier = mk.user(ca, role=UserRole.cashier, branch=ba1)
    cashier_nb = mk.user(ca, role=UserRole.cashier, branch=None)
    wallet = _wallet(db, ca, ba1)
    db.add(UserWallet(user_id=cashier.id, wallet_id=wallet.id, is_default=True, company_id=ca.id))
    db.flush()
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    return dict(ca=ca, ba1=ba1, ba2=ba2, wa1=wa1, wa2=wa2, wa_off=wa_off, admin=admin, cashier=cashier,
                cashier_nb=cashier_nb, wallet=wallet, cb=cb, bb=bb, whb=whb, admin_b=admin_b)


# ── Validator (birlik) ───────────────────────────────────────────────────────

def test_validator_rules(db, w):
    assert validate_sale_warehouse(db, w["cashier"], w["wa1"].id).id == w["wa1"].id
    for bad in (w["whb"].id, w["wa_off"].id, 999999, None, 0):
        with pytest.raises(Exception) as ei:
            validate_sale_warehouse(db, w["cashier"], bad)
        assert ei.value.status_code == 404 and "Ombor topilmadi" in ei.value.detail
    with pytest.raises(Exception) as ei:
        validate_sale_warehouse(db, w["cashier"], w["wa2"].id)
    assert ei.value.status_code == 403
    # admin va filialsiz kassir: boshqa filial ombori ruxsat
    assert validate_sale_warehouse(db, w["admin"], w["wa2"].id).id == w["wa2"].id
    assert validate_sale_warehouse(db, w["cashier_nb"], w["wa2"].id).id == w["wa2"].id
    # ammo begona korxona — hech kimga
    with pytest.raises(Exception) as ei:
        validate_sale_warehouse(db, w["admin"], w["whb"].id)
    assert ei.value.status_code == 404
    # company_id uzatilsa (super_admin oqimi) shu korxona omborlari tekshiriladi
    assert validate_sale_warehouses(db, w["admin_b"], [w["wa1"].id, w["wa2"].id], company_id=w["ca"].id)


def test_resolve_branch_id_ignores_foreign_warehouse(db, w, mk):
    nobranch = mk.user(w["ca"], role=UserRole.cashier, branch=None)
    assert resolve_branch_id(db, nobranch, w["whb"].id, prefer_warehouse=True) != w["bb"].id
    assert resolve_branch_id(db, nobranch, w["wa2"].id, prefer_warehouse=True) == w["ba2"].id


# ── POST /sales/ ─────────────────────────────────────────────────────────────

def test_create_foreign_company_warehouse_404(client, db, w):
    p = _product(db, w["ca"], w["wa1"])
    before_rows, before_sales = _stock_rows(db, p), db.query(Sale).count()
    r = client.login(w["cashier"]).post("/api/sales/", json=_body(p, wh_id=w["whb"].id))
    assert r.status_code == 404 and "Ombor topilmadi" in r.json()["detail"]
    assert _stock_rows(db, p) == before_rows and db.query(Sale).count() == before_sales
    assert db.query(StockLevel).filter(StockLevel.warehouse_id == w["whb"].id).count() == 0


def test_create_foreign_company_item_warehouse_404(client, db, w):
    p = _product(db, w["ca"], w["wa1"])
    r = client.login(w["cashier"]).post("/api/sales/", json=_body(p, wh_id=w["wa1"].id, item_wh_id=w["whb"].id))
    assert r.status_code == 404
    assert db.query(StockLevel).filter(StockLevel.warehouse_id == w["whb"].id).count() == 0
    assert db.query(Sale).count() == 0
    # sarlavhasiz, faqat qator ombori
    r = client.login(w["cashier"]).post("/api/sales/", json=_body(p, item_wh_id=w["whb"].id))
    assert r.status_code == 404
    assert db.query(StockLevel).filter(StockLevel.warehouse_id == w["whb"].id).count() == 0


def test_create_other_branch_cashier_403_admin_ok(client, db, w):
    p = _product(db, w["ca"], w["wa2"], qty=10)
    r = client.login(w["cashier"]).post("/api/sales/", json=_body(p, wh_id=w["wa2"].id))
    assert r.status_code == 403
    assert _qty(db, p, w["wa2"]) == Decimal("10") and db.query(Sale).count() == 0
    r = client.login(w["cashier"]).post("/api/sales/", json=_body(p, wh_id=w["wa1"].id, item_wh_id=w["wa2"].id))
    assert r.status_code == 403
    r = client.login(w["admin"]).post("/api/sales/", json=_body(p, wh_id=w["wa2"].id))
    assert r.status_code == 200, r.text
    assert _qty(db, p, w["wa2"]) == Decimal("9")


def test_create_inactive_warehouse_404(client, db, w):
    p = _product(db, w["ca"], w["wa_off"], qty=10)
    r = client.login(w["cashier"]).post("/api/sales/", json=_body(p, wh_id=w["wa_off"].id))
    assert r.status_code == 404
    assert _qty(db, p, w["wa_off"]) == Decimal("10") and db.query(Sale).count() == 0


def test_create_own_warehouse_works(client, db, w):
    p = _product(db, w["ca"], w["wa1"], qty=10)
    r = client.login(w["cashier"]).post("/api/sales/", json=_body(p, wh_id=w["wa1"].id, item_wh_id=w["wa1"].id, qty=2))
    assert r.status_code == 200, r.text
    assert _qty(db, p, w["wa1"]) == Decimal("8")
    assert db.query(Sale).one().warehouse_id == w["wa1"].id


def test_create_autoselect_still_works_and_stays_in_company(client, db, w):
    p = _product(db, w["ca"], w["wa1"], qty=10)
    r = client.login(w["cashier"]).post("/api/sales/", json=_body(p))
    assert r.status_code == 200, r.text
    assert db.query(Sale).one().warehouse_id == w["wa1"].id
    assert _qty(db, p, w["wa1"]) == Decimal("9")


def test_autoselect_branchless_user_ignores_foreign_company_stock(db, w):
    """Filialsiz foydalanuvchi: begona korxona omboridagi qoldiq hisobga olinmaydi (T1.5: "eng ko'p
    qoldiqli ombor" evristikasi olib tashlandi — 2+ filialli korxonada ombor/filialsiz sotuv 400)."""
    from fastapi import HTTPException
    p = _product(db, w["ca"], w["wa2"], qty=5)
    db.add(StockLevel(product_id=p.id, warehouse_id=w["whb"].id, quantity=Decimal("999")))
    db.flush()
    data = SaleCreate(**_body(p))
    with pytest.raises(HTTPException) as e:
        create_sale(db, data, w["cashier_nb"])
    assert e.value.status_code == 400
    assert _qty(db, p, w["whb"]) == Decimal("999")


# ── POST /sales/pending ──────────────────────────────────────────────────────

def test_pending_warehouse_validation(client, db, w):
    p = _product(db, w["ca"], w["wa1"])
    body = {"items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], "payment_type": "cash", "paid_amount": 0}
    c = client.login(w["cashier"])
    assert c.post("/api/sales/pending", json={**body, "warehouse_id": w["whb"].id}).status_code == 404
    assert c.post("/api/sales/pending", json={**body, "warehouse_id": w["wa_off"].id}).status_code == 404
    assert c.post("/api/sales/pending", json={**body, "warehouse_id": w["wa2"].id}).status_code == 403
    assert db.query(Sale).count() == 0
    r = c.post("/api/sales/pending", json={**body, "warehouse_id": w["wa1"].id})
    assert r.status_code == 200, r.text
    assert db.query(Sale).one().warehouse_id == w["wa1"].id


# ── POST /sales/return ───────────────────────────────────────────────────────

def test_return_warehouse_validation(client, db, w):
    p = _product(db, w["ca"], w["wa1"], qty=5)

    def body(wh):
        return {"items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], "payment_type": "cash",
                "paid_amount": 1000, "paid_cash": 1000, "warehouse_id": wh.id}

    c = client.login(w["cashier"])
    assert c.post("/api/sales/return", json=body(w["whb"])).status_code == 404
    assert c.post("/api/sales/return", json=body(w["wa_off"])).status_code == 404
    assert c.post("/api/sales/return", json=body(w["wa2"])).status_code == 403
    assert db.query(StockLevel).filter(StockLevel.warehouse_id == w["whb"].id).count() == 0
    assert _qty(db, p, w["wa1"]) == Decimal("5")
    r = c.post("/api/sales/return", json=body(w["wa1"]))
    assert r.status_code == 200, r.text


# ── PUT /sales/{id} ──────────────────────────────────────────────────────────

def _make_sale(db, w, p, qty=2):
    return create_sale(db, SaleCreate(**_body(p, wh_id=w["wa1"].id, qty=qty)), w["admin"])


def test_update_foreign_warehouse_404_and_nothing_changes(client, db, w):
    p = _product(db, w["ca"], w["wa1"], qty=10)
    sale = _make_sale(db, w, p)
    assert _qty(db, p, w["wa1"]) == Decimal("8")
    wallet_before = Decimal(str(db.get(Wallet, w["wallet"].id).balance))

    def put(**extra):
        body = {"items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], "payment_type": "cash",
                "paid_amount": 1000, "payments": [{"type": "cash", "amount": 1000}]}
        body.update(extra)
        return client.login(w["admin"]).put(f"/api/sales/{sale.id}", json=body)

    r = put(warehouse_id=w["whb"].id)
    assert r.status_code == 404
    r = put(warehouse_id=w["wa1"].id, items=[{"product_id": p.id, "quantity": 1, "unit_price": 1000,
                                               "warehouse_id": w["whb"].id}])
    assert r.status_code == 404
    r = put(warehouse_id=w["wa_off"].id)
    assert r.status_code == 404
    # Qoldiq va kassa o'zgarmagan (teskari ta'sir yozilmagan)
    db.expire_all()
    assert _qty(db, p, w["wa1"]) == Decimal("8")
    assert Decimal(str(db.get(Wallet, w["wallet"].id).balance)) == wallet_before
    assert db.query(StockLevel).filter(StockLevel.warehouse_id == w["whb"].id).count() == 0
    # Ijobiy yo'l
    r = put(warehouse_id=w["wa1"].id)
    assert r.status_code == 200, r.text
    assert _qty(db, p, w["wa1"]) == Decimal("9")


def test_update_other_branch_cashier_403(client, db, w):
    p = _product(db, w["ca"], w["wa1"], qty=10)
    sale = create_sale(db, SaleCreate(**_body(p, wh_id=w["wa1"].id)), w["cashier"])
    body = {"items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], "payment_type": "cash",
            "paid_amount": 1000, "payments": [{"type": "cash", "amount": 1000}], "warehouse_id": w["wa2"].id}
    r = client.login(w["cashier"]).put(f"/api/sales/{sale.id}", json=body)
    assert r.status_code == 403
    assert _qty(db, p, w["wa1"]) == Decimal("9")
