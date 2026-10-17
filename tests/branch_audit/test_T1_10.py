"""T1.10 — Kassa (wallet) ni filialga bog'lash va tanlash qoidasi.

Qamrov: `resolve_wallet` tartibi (so'ralgan -> kassirning kassasi -> filial kassasi -> filialning ochiq kassasi ->
umumiy kassa), shaxsiy (qo'l) kassa va boshqa filial kassasi hech qachon fallback emas, nofaol default o'tkaziladi,
>=2 filialli korxonada 400; sotuvda `wallet_id` saqlanishi va tekshiruvi; qaytarish (asl kassa, asl kassa nofaol,
manfiy balans ogohlantirishi); `/kassa` va `/finance/wallets` ro'yxati (filial, nofaol, shaxsiy, is_default_for_me);
PATCH branch_id (begona korxona 404); kassani o'chirish `user_wallets` ni tozalaydi; xarajat filiali = kassa filiali;
kassa biriktirish ogohlantirishi; smena yopishda boshqa filial kassasi; receivable_wallets; migratsiya fayli.
Har joyda ikki korxona izolyatsiyasi va ijobiy yo'l.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T1_10.py -q -p no:cacheprovider
"""
import itertools
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.inventory import StockLevel
from app.models.moliya import Expense, ExpenseCategory, KassaMovement, Wallet
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole, UserWallet
from app.services.wallet_resolver import (
    NO_BRANCH_WALLET, assert_wallet_access, resolve_wallet,
)

_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _wallet(db, company, branch=None, *, active=True, is_open=True, personal=False, balance=0, name=None):
    w = Wallet(name=name or f"Kassa {next(_seq)}", type="cash", balance=Decimal(balance), company_id=company.id,
               branch_id=branch.id if branch else None, is_active=active, is_open=is_open, is_personal=personal)
    db.add(w)
    db.flush()
    return w


def _attach(db, user, wallet, default=True):
    db.add(UserWallet(user_id=user.id, wallet_id=wallet.id, is_default=default, company_id=wallet.company_id))
    db.flush()


def _product(db, company, wh, qty=100):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T110-{n}", barcode=f"B110-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
    db.flush()
    return p


def _body(p, wh, qty=1, **extra):
    amt = 1000 * qty
    body = {"items": [{"product_id": p.id, "quantity": qty, "unit_price": 1000}], "payment_type": "cash",
            "paid_amount": amt, "paid_cash": amt, "payments": [{"type": "cash", "amount": amt}],
            "warehouse_id": wh.id}
    body.update(extra)
    return body


def _bal(db, wallet):
    db.expire(wallet)
    return Decimal(str(wallet.balance or 0))


@pytest.fixture
def w(db, mk):
    """Korxona A: 2 filial (Yunusobod=ba1, Chilonzor=ba2), har birida ombor va kassir; admin. Korxona B."""
    ca = mk.company()
    ba1 = mk.branch(ca, name="Yunusobod")
    ba2 = mk.branch(ca, name="Chilonzor")
    wh1 = mk.warehouse(ca, ba1)
    wh2 = mk.warehouse(ca, ba2)
    cash1 = mk.user(ca, role=UserRole.cashier, branch=ba1)
    cash2 = mk.user(ca, role=UserRole.cashier, branch=ba2)
    admin = mk.user(ca, role=UserRole.admin, branch=ba1)
    # Tuzoqlar: eng kichik id'li ochiq kassalar boshqa filialda / shaxsiy
    courier = mk.user(ca, role=UserRole.courier, branch=ba1)
    hand = _wallet(db, ca, ba1, personal=True, name="Kuryer — qo'l kassasi")
    _attach(db, courier, hand)
    chil = _wallet(db, ca, ba2, name="Chilonzor kassa")
    yun = _wallet(db, ca, ba1, name="Yunusobod kassa")
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    wallet_b = _wallet(db, cb, bb, name="B kassa")
    prod = _product(db, ca, wh1)
    prod2 = _product(db, ca, wh2)
    return SimpleNamespace(ca=ca, ba1=ba1, ba2=ba2, wh1=wh1, wh2=wh2, cash1=cash1, cash2=cash2, admin=admin,
                           courier=courier, hand=hand, chil=chil, yun=yun, cb=cb, bb=bb, admin_b=admin_b,
                           wallet_b=wallet_b, prod=prod, prod2=prod2)


# ── 1. resolve_wallet tartibi ────────────────────────────────────────────────

def test_resolver_branch_wallet_not_other_branch_not_personal(db, w):
    """Kassa biriktirilmagan kassir: o'z filial kassasi (Yunusobod); Chilonzor va qo'l kassasi emas."""
    got = resolve_wallet(db, w.cash1, branch_id=w.ba1.id, purpose="sale")
    assert got.id == w.yun.id
    got2 = resolve_wallet(db, w.cash2, branch_id=w.ba2.id, purpose="sale")
    assert got2.id == w.chil.id


def test_resolver_user_default_before_branch(db, w):
    other = _wallet(db, w.ca, w.ba1, name="Ikkinchi")
    _attach(db, w.cash1, other)
    assert resolve_wallet(db, w.cash1, branch_id=w.ba1.id).id == other.id


def test_resolver_inactive_default_skipped(db, w):
    dead = _wallet(db, w.ca, w.ba1, active=False)
    _attach(db, w.cash1, dead)
    assert resolve_wallet(db, w.cash1, branch_id=w.ba1.id).id == w.yun.id


def test_resolver_common_wallet_when_branch_has_none(db, mk):
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    u = mk.user(c, role=UserRole.cashier, branch=b1)
    common = _wallet(db, c, None, name="Umumiy")
    _wallet(db, c, b2, name="Boshqa")
    assert resolve_wallet(db, u, branch_id=b1.id).id == common.id


def test_resolver_multi_branch_without_wallet_400(db, mk):
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    u = mk.user(c, role=UserRole.cashier, branch=b1)
    _wallet(db, c, b2)
    with pytest.raises(HTTPException) as e:
        resolve_wallet(db, u, branch_id=b1.id)
    assert e.value.status_code == 400 and e.value.detail == NO_BRANCH_WALLET


def test_resolver_single_branch_or_no_wallets_keeps_old_behavior(db, mk):
    c = mk.company()
    b = mk.branch(c)
    u = mk.user(c, role=UserRole.cashier, branch=b)
    assert resolve_wallet(db, u, branch_id=b.id) is None            # kassa umuman yo'q
    c2 = mk.company()
    b21, b22 = mk.branch(c2), mk.branch(c2)
    u2 = mk.user(c2, role=UserRole.cashier, branch=b21)
    assert resolve_wallet(db, u2, branch_id=b21.id) is None         # ko'p filial, lekin kassa umuman yo'q


def test_resolver_personal_never_fallback(db, mk):
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    u = mk.user(c, role=UserRole.cashier, branch=b1)
    _wallet(db, c, b1, personal=True, name="Qo'l")
    _wallet(db, c, None, personal=True, name="Qo'l 2")
    _wallet(db, c, b2, name="Boshqa filial")
    with pytest.raises(HTTPException) as e:
        resolve_wallet(db, u, branch_id=b1.id)
    assert e.value.status_code == 400


def test_resolver_own_personal_wallet_is_default_for_owner(db, w):
    assert resolve_wallet(db, w.courier, branch_id=w.ba1.id).id == w.hand.id


def test_resolver_requested_rules(db, w):
    # o'z filiali kassasi
    assert resolve_wallet(db, w.cash1, branch_id=w.ba1.id, requested_wallet_id=w.yun.id).id == w.yun.id
    # boshqa korxona -> 404
    with pytest.raises(HTTPException) as e:
        resolve_wallet(db, w.cash1, branch_id=w.ba1.id, requested_wallet_id=w.wallet_b.id)
    assert e.value.status_code == 404
    # boshqa filial -> 403
    with pytest.raises(HTTPException) as e:
        resolve_wallet(db, w.cash1, branch_id=w.ba1.id, requested_wallet_id=w.chil.id)
    assert e.value.status_code == 403
    # nofaol -> 404
    dead = _wallet(db, w.ca, w.ba1, active=False)
    with pytest.raises(HTTPException) as e:
        resolve_wallet(db, w.cash1, branch_id=w.ba1.id, requested_wallet_id=dead.id)
    assert e.value.status_code == 404
    # shaxsiy (begona) -> 403
    with pytest.raises(HTTPException) as e:
        resolve_wallet(db, w.cash1, branch_id=w.ba1.id, requested_wallet_id=w.hand.id)
    assert e.value.status_code == 403


def test_assert_wallet_access_roles(db, w):
    assert_wallet_access(w.admin, w.chil, db)                       # admin hammasini
    assert_wallet_access(w.cash1, w.yun, db)
    with pytest.raises(HTTPException) as e:
        assert_wallet_access(w.cash1, w.chil, db)
    assert e.value.status_code == 403
    _attach(db, w.cash1, w.chil, default=False)                      # biriktirilgan bo'lsa ruxsat
    assert_wallet_access(w.cash1, w.chil, db)
    with pytest.raises(HTTPException) as e:
        assert_wallet_access(w.admin_b, w.chil, db)                  # begona korxona
    assert e.value.status_code == 404


# ── 2. Sotuv: kassa tanlash va sales.wallet_id ───────────────────────────────

def test_sale_goes_to_branch_wallet_and_saves_wallet_id(client, db, w):
    r = client.login(w.cash1).post("/api/sales/", json=_body(w.prod, w.wh1))
    assert r.status_code == 200, r.text
    sale = db.get(Sale, r.json()["id"])
    assert sale.wallet_id == w.yun.id
    assert _bal(db, w.yun) == Decimal("1000")
    assert _bal(db, w.chil) == Decimal("0") and _bal(db, w.hand) == Decimal("0")
    assert db.query(KassaMovement).filter(KassaMovement.reference_id == sale.id,
                                          KassaMovement.reference_type == "sale").one().wallet_id == w.yun.id


def test_sale_without_branch_wallet_400(client, db, mk):
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    wh1 = mk.warehouse(c, b1)
    cashier = mk.user(c, role=UserRole.cashier, branch=b1)
    _wallet(db, c, b2, name="Faqat boshqa filialda")
    p = _product(db, c, wh1)
    r = client.login(cashier).post("/api/sales/", json=_body(p, wh1))
    assert r.status_code == 400 and r.json()["detail"] == NO_BRANCH_WALLET
    assert db.query(Sale).count() == 0


def test_sale_requested_wallet_respected_and_saved(client, db, w):
    other = _wallet(db, w.ca, w.ba1, name="Qo'shimcha")
    r = client.login(w.cash1).post("/api/sales/", json=_body(w.prod, w.wh1, wallet_id=other.id))
    assert r.status_code == 200, r.text
    assert db.get(Sale, r.json()["id"]).wallet_id == other.id
    assert _bal(db, other) == Decimal("1000")


def test_sale_requested_wallet_foreign_company_inactive_other_branch(client, db, w):
    for wid, codes in ((w.wallet_b.id, (404,)), (w.chil.id, (403,))):
        r = client.login(w.cash1).post("/api/sales/", json=_body(w.prod, w.wh1, wallet_id=wid))
        assert r.status_code in codes, r.text
    dead = _wallet(db, w.ca, w.ba1, active=False)
    r = client.login(w.cash1).post("/api/sales/", json=_body(w.prod, w.wh1, wallet_id=dead.id))
    assert r.status_code == 404, r.text
    assert db.query(Sale).count() == 0
    assert _bal(db, w.chil) == Decimal("0") and _bal(db, w.wallet_b) == Decimal("0")


def test_sale_debt_only_does_not_need_wallet(client, db, mk):
    """Faqat qarzga sotuvda pul tushmaydi — kassasiz ko'p filialli korxonada ham 400 emas."""
    c = mk.company()
    b1, _b2 = mk.branch(c), mk.branch(c)
    wh1 = mk.warehouse(c, b1)
    cashier = mk.user(c, role=UserRole.cashier, branch=b1)
    _wallet(db, c, _b2)
    from app.models.customer import Customer
    cust = Customer(name="Mijoz", phone="998900000001", company_id=c.id, debt_limit=Decimal("100000"))
    db.add(cust)
    db.flush()
    p = _product(db, c, wh1)
    body = {"items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], "payment_type": "debt",
            "paid_amount": 0, "warehouse_id": wh1.id, "customer_id": cust.id}
    r = client.login(cashier).post("/api/sales/", json=body)
    assert r.status_code == 200, r.text
    assert db.get(Sale, r.json()["id"]).wallet_id is None


# ── 3. Qaytarish ─────────────────────────────────────────────────────────────

def _completed_sale(db, w, cashier, wh, product, wallet, qty=3):
    sub = Decimal(qty) * Decimal(1000)
    s = Sale(number=f"S11{next(_seq):06d}", cashier_id=cashier.id, company_id=w.ca.id, warehouse_id=wh.id,
             wallet_id=wallet.id if wallet else None, total_amount=sub, paid_amount=sub, paid_cash=sub,
             payment_type=PaymentType.cash, status=SaleStatus.completed)
    db.add(s)
    db.flush()
    db.add(SaleItem(sale_id=s.id, product_id=product.id, warehouse_id=wh.id, quantity=Decimal(qty),
                    unit_price=Decimal(1000), cost_price=product.cost_price, discount=Decimal(0), subtotal=sub,
                    returned_quantity=Decimal(0), currency_code="UZS", exchange_rate=Decimal(1)))
    db.flush()
    db.refresh(s)
    return s


def _partial(client, user, sale, qty, **extra):
    item = sale.items[0]
    body = {"items": [{"sale_item_id": item.id, "quantity": qty}], "payment_type": "cash"}
    body.update(extra)
    return client.login(user).post(f"/api/sales/{sale.id}/return-items", json=body)


def test_partial_return_from_original_sale_wallet(client, db, w):
    other = _wallet(db, w.ca, w.ba1, balance=5000, name="Asl kassa")
    sale = _completed_sale(db, w, w.cash1, w.wh1, w.prod, other)
    r = _partial(client, w.cash1, sale, 1)
    assert r.status_code == 200, r.text
    assert _bal(db, other) == Decimal("4000")
    assert _bal(db, w.yun) == Decimal("0") and _bal(db, w.chil) == Decimal("0")
    ret = db.query(Sale).filter(Sale.original_sale_id == sale.id).one()
    assert ret.wallet_id == other.id


def test_partial_return_inactive_original_wallet_falls_back_to_branch_wallet(client, db, w):
    dead = _wallet(db, w.ca, w.ba1, balance=5000, active=False)
    sale = _completed_sale(db, w, w.cash1, w.wh1, w.prod, dead)
    w.yun.balance = Decimal("10000")
    db.flush()
    r = _partial(client, w.cash1, sale, 1)
    assert r.status_code == 200, r.text
    assert _bal(db, w.yun) == Decimal("9000")
    assert _bal(db, dead) == Decimal("5000") and _bal(db, w.chil) == Decimal("0")


def test_partial_return_negative_balance_saved_with_warning(db, w):
    from app.schemas.sale import SaleReturnRequest
    from app.services.sale_partial_return import process_partial_return
    sale = _completed_sale(db, w, w.cash1, w.wh1, w.prod, w.yun)
    assert _bal(db, w.yun) == Decimal("0")
    data = SaleReturnRequest(items=[{"sale_item_id": sale.items[0].id, "quantity": 1}], payment_type="cash")
    out = process_partial_return(db=db, sale_id=sale.id, data=data, current_user=w.cash1, ip=None)
    assert _bal(db, w.yun) == Decimal("-1000")                       # yozuv saqlandi
    assert getattr(out, "warning", None)                              # ogohlantirish bor
    assert db.query(Sale).filter(Sale.original_sale_id == sale.id).count() == 1


def test_full_return_respects_requested_wallet_and_isolation(client, db, w):
    p = w.prod
    body = {"items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], "payment_type": "cash",
            "paid_amount": 1000, "paid_cash": 1000, "warehouse_id": w.wh1.id}
    r = client.login(w.cash1).post("/api/sales/return", json={**body, "wallet_id": w.wallet_b.id})
    assert r.status_code == 404, r.text
    r = client.login(w.cash1).post("/api/sales/return", json={**body, "wallet_id": w.chil.id})
    assert r.status_code == 403, r.text
    r = client.login(w.cash1).post("/api/sales/return", json={**body, "wallet_id": w.yun.id})
    assert r.status_code == 200, r.text
    assert db.get(Sale, r.json()["id"]).wallet_id == w.yun.id
    assert _bal(db, w.yun) == Decimal("-1000")


# ── 4. Shaxsiy kassa: mobil ──────────────────────────────────────────────────

def test_ensure_personal_wallet_is_personal_and_receivable_excludes_it(db, mk):
    from app.services.mobile_service import ensure_personal_wallet, receivable_wallets
    c = mk.company()
    b = mk.branch(c)
    courier = mk.user(c, role=UserRole.courier, branch=b)
    shared = _wallet(db, c, b, name="Asosiy")
    hand = ensure_personal_wallet(db, courier)
    assert hand.is_personal is True and hand.company_id == c.id
    ids = {x.id for x in receivable_wallets(db, courier)}
    assert shared.id in ids and hand.id not in ids
    # begona korxona kassasi ko'rinmaydi
    c2 = mk.company()
    other = _wallet(db, c2, None)
    assert other.id not in {x.id for x in receivable_wallets(db, courier)}


# ── 5. /kassa va /finance/wallets ro'yxatlari ────────────────────────────────

def test_kassa_list_branch_filter_inactive_personal_and_flags(client, db, w):
    dead = _wallet(db, w.ca, w.ba1, active=False, name="O'chgan")
    _attach(db, w.admin, w.yun, default=True)
    cl = client.login(w.admin)
    r = cl.get("/api/kassa")
    ids = {x["id"] for x in r.json()}
    assert r.status_code == 200
    assert {w.yun.id, w.chil.id} <= ids and dead.id not in ids and w.hand.id not in ids
    assert w.wallet_b.id not in ids                                    # begona korxona
    r = cl.get("/api/kassa", params={"branch_id": w.ba1.id})
    assert {x["id"] for x in r.json()} == {w.yun.id}
    row = r.json()[0]
    assert row["branch_name"] == "Yunusobod" and row["is_personal"] is False and row["is_default_for_me"] is True
    r = cl.get("/api/kassa", params={"include_inactive": "true"})
    assert dead.id in {x["id"] for x in r.json()}


def test_finance_wallets_same_set_as_kassa_and_active_default(client, db, w):
    dead = _wallet(db, w.ca, w.ba1, active=False)
    cl = client.login(w.admin)
    fin = {x["id"] for x in cl.get("/api/finance/wallets").json()}
    kas = {x["id"] for x in cl.get("/api/kassa").json()}
    assert fin == kas and dead.id not in fin and w.hand.id not in fin
    r = cl.get("/api/finance/wallets", params={"include_inactive": "true"})
    assert dead.id in {x["id"] for x in r.json()}


def test_finance_wallets_cashier_sees_only_own_branch_and_common(client, db, w):
    common = _wallet(db, w.ca, None, name="Umumiy")
    r = client.login(w.cash1).get("/api/finance/wallets", params={"branch_id": w.ba1.id, "usable": "true"})
    assert r.status_code == 200, r.text
    ids = {x["id"] for x in r.json()}
    assert ids == {w.yun.id, common.id}
    assert all("balance" not in x for x in r.json())                  # kassir balansni ko'rmaydi (T0.5)
    r = client.login(w.cash1).get("/api/finance/wallets")
    assert w.chil.id not in {x["id"] for x in r.json()}


# ── 6. Kassa CRUD: branch_id ─────────────────────────────────────────────────

def test_patch_wallet_branch_set_and_clear(client, db, w):
    cl = client.login(w.admin)
    r = cl.patch(f"/api/kassa/{w.chil.id}", json={"branch_id": w.ba1.id})
    assert r.status_code == 200, r.text
    assert db.get(Wallet, w.chil.id).branch_id == w.ba1.id and r.json()["branch_id"] == w.ba1.id
    r = cl.patch(f"/api/kassa/{w.chil.id}", json={"name": "Yangi nom"})   # branch_id yuborilmasa o'zgarmaydi
    assert r.status_code == 200 and db.get(Wallet, w.chil.id).branch_id == w.ba1.id
    r = cl.patch(f"/api/kassa/{w.chil.id}", json={"branch_id": None})
    assert r.status_code == 200 and db.get(Wallet, w.chil.id).branch_id is None


def test_patch_wallet_foreign_branch_404_and_foreign_wallet_404(client, db, w):
    cl = client.login(w.admin)
    r = cl.patch(f"/api/kassa/{w.yun.id}", json={"branch_id": w.bb.id})
    assert r.status_code == 404 and r.json()["detail"] == "Filial topilmadi"
    assert db.get(Wallet, w.yun.id).branch_id == w.ba1.id
    r = cl.patch(f"/api/kassa/{w.wallet_b.id}", json={"branch_id": w.ba1.id})
    assert r.status_code == 404


def test_create_wallet_with_branch_validation(client, db, w):
    cl = client.login(w.admin)
    r = cl.post("/api/kassa", json={"name": "Yangi", "branch_id": w.bb.id})
    assert r.status_code == 400
    r = cl.post("/api/kassa", json={"name": "Yangi", "branch_id": w.ba2.id})
    assert r.status_code == 200 and r.json()["branch_id"] == w.ba2.id and r.json()["branch_name"] == "Chilonzor"
    r = cl.post("/api/finance/wallets", json={"name": "Moliya", "branch_id": w.ba2.id})
    assert r.status_code == 201, r.text


def test_delete_wallet_clears_user_wallets_both_endpoints(client, db, w):
    for path in ("kassa", "finance/wallets"):
        x = _wallet(db, w.ca, w.ba1)
        _attach(db, w.cash1, x, default=True)
        r = client.login(w.admin).delete(f"/api/{path}/{x.id}")
        assert r.status_code in (200, 204), r.text
        assert db.query(UserWallet).filter(UserWallet.wallet_id == x.id).count() == 0
        assert db.get(Wallet, x.id).is_active is False
    # boshqa korxona adminiga kassani o'chirib bo'lmaydi
    r = client.login(w.admin_b).delete(f"/api/kassa/{w.yun.id}")
    assert r.status_code == 404 and db.get(Wallet, w.yun.id).is_active is True


def test_kassa_scope_other_branch_forbidden_for_non_admin(client, db, mk, w):
    acc = mk.user(w.ca, role=UserRole.accountant, branch=w.ba1)
    w.chil.is_open = True
    db.flush()
    r = client.login(acc).get(f"/api/kassa/{w.chil.id}/x-report")
    assert r.status_code == 403, r.text
    r = client.login(acc).get(f"/api/kassa/{w.chil.id}/sessions")
    assert r.status_code == 403
    r = client.login(acc).get(f"/api/kassa/{w.yun.id}/sessions")      # o'z filiali — ijobiy yo'l
    assert r.status_code == 200, r.text
    r = client.login(w.admin).get(f"/api/kassa/{w.chil.id}/sessions")  # admin barcha filial
    assert r.status_code == 200


def test_expense_branch_is_wallet_branch(client, db, w):
    cat = ExpenseCategory(name="Ijara", company_id=w.ca.id)
    db.add(cat)
    db.flush()
    # admin Yunusobodda, lekin kassa Chilonzorda -> xarajat filiali kassa filiali
    r = client.login(w.admin).post("/api/kassa/do-expense", json={
        "wallet_id": w.chil.id, "category_id": cat.id, "amount": 500, "payment_type": "cash"})
    assert r.status_code == 200, r.text
    exp = db.get(Expense, r.json()["expense_id"])
    assert exp.branch_id == w.ba2.id and exp.branch_id != 0
    # filialsiz (umumiy) kassa -> xodim filiali
    common = _wallet(db, w.ca, None)
    r = client.login(w.admin).post("/api/kassa/do-expense", json={
        "wallet_id": common.id, "category_id": cat.id, "amount": 100, "payment_type": "cash"})
    assert r.status_code == 200, r.text
    assert db.get(Expense, r.json()["expense_id"]).branch_id == w.ba1.id


# ── 7. Kassa biriktirish ogohlantirishi ──────────────────────────────────────

def test_assign_wallet_branch_mismatch_warning(client, db, w):
    cl = client.login(w.admin)
    r = cl.post(f"/api/users/{w.cash1.id}/wallets", json={"wallet_id": w.yun.id, "is_default": True})
    assert r.status_code == 200 and r.json() == {"ok": True}
    r = cl.post(f"/api/users/{w.cash1.id}/wallets", json={"wallet_id": w.chil.id, "is_default": False})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json().get("warning")
    r = cl.post(f"/api/users/{w.cash1.id}/wallets/{w.chil.id}/set-default")
    assert r.status_code == 200 and r.json().get("warning")
    # begona korxona kassasi / xodimi
    assert cl.post(f"/api/users/{w.cash1.id}/wallets", json={"wallet_id": w.wallet_b.id}).status_code == 404


# ── 8. Smena yopish ──────────────────────────────────────────────────────────

def test_shift_close_other_branch_wallet_forbidden(client, db, w):
    from app.models.shift import Shift
    sh = Shift(cashier_id=w.cash1.id, company_id=w.ca.id, branch_id=w.ba1.id, status="open",
               opening_cash=Decimal(0))
    db.add(sh)
    db.flush()
    r = client.login(w.cash1).post("/api/shifts/close", json={"wallet_id": w.chil.id, "closing_cash": 0})
    assert r.status_code in (400, 403), r.text
    assert db.get(Shift, sh.id).status == "open"
    r = client.login(w.cash1).post("/api/shifts/close", json={"wallet_id": w.wallet_b.id, "closing_cash": 0})
    assert r.status_code == 404, r.text
    assert db.get(Shift, sh.id).status == "open"
    r = client.login(w.cash1).post("/api/shifts/close", json={"wallet_id": w.yun.id, "closing_cash": 0})
    assert r.status_code == 200, r.text


# ── 9. Migratsiya fayli ──────────────────────────────────────────────────────

def test_migration_file_shape():
    import importlib.util
    import os
    from tests.branch_audit.conftest import ROOT
    path = os.path.join(ROOT, "alembic", "versions", "t1_10_wallets_branch_sales_wallet.py")
    spec = importlib.util.spec_from_file_location("t1_10_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "t1_10" and mod.down_revision == "t1_9"
    src = open(path, encoding="utf-8").read()
    for needle in ("is_personal", "sales ADD COLUMN IF NOT EXISTS wallet_id", "ix_sales_wallet_id",
                   "HAVING COUNT(*) = 1", "DELETE FROM user_wallets"):
        assert needle in src
    assert "DROP COLUMN" in src                                       # downgrade
