"""T0.5 — Kassa va moliya routerlarida rol/huquq majburlash.

/kassa/* — admin/director/accountant (+ permissions.kassa == False -> 403);
withdraw/invest/wallet create-update-delete/expense update-delete — faqat admin/director.
/finance/{expense-categories, expenses, transactions}, POST /wallets, GET /cash-balance —
FINANCE_ROLES (+ permissions.finance == False -> 403). GET /finance/wallets hamma xodimga
ochiq, lekin FINANCE_ROLES da bo'lmaganlar balanssiz oladi. Mijoz qarzini kassir to'lay oladi.
"""
from decimal import Decimal

import pytest

from app.models.customer import Customer
from app.models.moliya import Wallet
from app.models.user import UserRole, UserWallet

R = UserRole


def _wallet(db, company, branch=None, balance=500, name=None, is_active=True):
    w = Wallet(name=name or f"Kassa {company.id}", type="cash", balance=Decimal(balance),
               company_id=company.id, branch_id=branch.id if branch else None,
               is_active=is_active, is_open=True)
    db.add(w)
    db.flush()
    return w


def _user(mk, company, branch, role, **kw):
    return mk.user(company, role=role, branch=branch, **kw)


# (usul, yo'l shabloni, tana) — {w} kassa id
KASSA_ADMIN_ONLY = [
    ("post", "/api/kassa/{w}/withdraw", {"amount": 10}),
    ("post", "/api/kassa/{w}/invest", {"amount": 10}),
    ("delete", "/api/kassa/{w}", None),
    ("patch", "/api/kassa/{w}", {"name": "Yangi"}),
    ("post", "/api/kassa", {"name": "Yangi kassa"}),
    ("put", "/api/kassa/expense/1", {"amount": 5}),
    ("delete", "/api/kassa/expense/1", None),
]
KASSA_ACCOUNTANT_OK = [
    ("get", "/api/kassa", None),
    ("get", "/api/kassa/{w}", None),
    ("get", "/api/kassa/{w}/history", None),
    ("get", "/api/kassa/{w}/x-report", None),
    ("get", "/api/kassa/categories", None),
    ("post", "/api/kassa/categories", {"name": "Ijara"}),
    ("post", "/api/kassa/do-expense", {}),
    ("post", "/api/kassa/{w}/open", {}),
    ("post", "/api/kassa/{w}/close", {"actual_amounts": {}}),
    ("post", "/api/kassa/{w}/transfer/out", {}),
    ("post", "/api/kassa/transfer/in", {}),
    ("post", "/api/kassa/transfer/reject", {}),
]
FINANCE_GUARDED = [
    ("get", "/api/finance/expense-categories", None),
    ("post", "/api/finance/expense-categories", {"name": "Boshqa"}),
    ("delete", "/api/finance/expense-categories/1", None),
    ("get", "/api/finance/expenses", None),
    ("post", "/api/finance/expenses", {}),
    ("delete", "/api/finance/expenses/1", None),
    ("get", "/api/finance/transactions", None),
    ("post", "/api/finance/transactions", {}),
    ("post", "/api/finance/wallets", {"name": "X"}),
    ("get", "/api/finance/cash-balance", None),
]


def _call(c, method, path, body, w):
    url = path.format(w=w.id)
    fn = getattr(c, method)
    return fn(url, json=body) if body is not None else fn(url)


@pytest.fixture
def env(mk, db):
    comp, branch, _wh, admin = mk.tenant()
    w = _wallet(db, comp, branch)
    users = {r: _user(mk, comp, branch, r) for r in (R.cashier, R.warehouse, R.manager, R.accountant, R.director)}
    users[R.admin] = admin
    return comp, branch, w, users


# ─── Rol jadvali ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", [R.cashier, R.warehouse, R.manager])
@pytest.mark.parametrize("method,path,body", KASSA_ADMIN_ONLY + KASSA_ACCOUNTANT_OK)
def test_kassa_yopiq_rollar(client, env, role, method, path, body):
    _, _, w, users = env
    c = client.login(users[role])
    assert _call(c, method, path, body, w).status_code == 403


@pytest.mark.parametrize("method,path,body", KASSA_ADMIN_ONLY)
def test_kassa_buxgalter_yozuvchi_amallarga_kirmaydi(client, env, method, path, body):
    _, _, w, users = env
    c = client.login(users[R.accountant])
    r = _call(c, method, path, body, w)
    assert r.status_code == 403
    assert "Kerakli rol" in r.json()["detail"]


@pytest.mark.parametrize("method,path,body", KASSA_ACCOUNTANT_OK)
@pytest.mark.parametrize("role", [R.accountant, R.admin, R.director])
def test_kassa_ruxsat_etilgan_rollar_403_olmaydi(client, env, role, method, path, body):
    _, _, w, users = env
    c = client.login(users[role])
    assert _call(c, method, path, body, w).status_code != 403


@pytest.mark.parametrize("method,path,body", KASSA_ADMIN_ONLY)
@pytest.mark.parametrize("role", [R.admin, R.director])
def test_kassa_admin_director_yozuvchi_amallar_403_emas(client, env, role, method, path, body):
    _, _, w, users = env
    c = client.login(users[role])
    assert _call(c, method, path, body, w).status_code != 403


def test_kassa_super_admin_hammasida_otadi(client, mk, env):
    comp, _, w, _ = env
    sa = mk.user(comp, role=R.super_admin)
    c = client.login(sa)
    for method, path, body in KASSA_ADMIN_ONLY + KASSA_ACCOUNTANT_OK:
        assert _call(c, method, path, body, w).status_code != 403, path


# ─── permissions deny-override ───────────────────────────────────────────────

@pytest.mark.parametrize("role", [R.admin, R.accountant])
def test_kassa_permissions_false_403(client, mk, env, role):
    comp, branch, w, _ = env
    u = _user(mk, comp, branch, role, permissions={"kassa": False})
    c = client.login(u)
    for path in ("/api/kassa", f"/api/kassa/{w.id}", f"/api/kassa/{w.id}/history"):
        r = c.get(path)
        assert r.status_code == 403, path
        assert "maxsus cheklov" in r.json()["detail"]


def test_kassa_permissions_boshqa_modul_false_otkazadi(client, mk, env):
    comp, branch, w, _ = env
    u = _user(mk, comp, branch, R.accountant, permissions={"finance": False, "kassa": True})
    assert client.login(u).get("/api/kassa").status_code == 200


def test_kassa_super_admin_permissions_false_bilan_ham_otadi(client, mk, env):
    comp = env[0]
    sa = mk.user(comp, role=R.super_admin, permissions={"kassa": False})
    assert client.login(sa).get("/api/kassa").status_code != 403


@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/finance/expenses", None),
    ("post", "/api/finance/expenses", {}),
    ("get", "/api/finance/transactions", None),
    ("get", "/api/finance/expense-categories", None),
])
def test_finance_permissions_false_403(client, mk, env, method, path, body):
    comp, branch, w, _ = env
    u = _user(mk, comp, branch, R.accountant, permissions={"finance": False})
    r = _call(client.login(u), method, path, body, w)
    assert r.status_code == 403
    assert "maxsus cheklov" in r.json()["detail"]


# ─── finance.py ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", [R.cashier, R.warehouse])
@pytest.mark.parametrize("method,path,body", FINANCE_GUARDED)
def test_finance_kassir_va_omborchi_403(client, env, role, method, path, body):
    _, _, w, users = env
    assert _call(client.login(users[role]), method, path, body, w).status_code == 403


@pytest.mark.parametrize("role", [R.admin, R.director, R.accountant, R.manager])
@pytest.mark.parametrize("method,path,body", FINANCE_GUARDED)
def test_finance_finance_roles_403_olmaydi(client, env, role, method, path, body):
    _, _, w, users = env
    assert _call(client.login(users[role]), method, path, body, w).status_code != 403


def test_cash_balance_ijobiy_va_kassir_403(client, env):
    _, _, _, users = env
    r = client.login(users[R.accountant]).get("/api/finance/cash-balance")
    assert r.status_code == 200
    assert "balance_by_currency" in r.json()
    assert client.login(users[R.cashier]).get("/api/finance/cash-balance").status_code == 403


# ─── GET /finance/wallets: kassir balanssiz oladi ────────────────────────────

def test_wallets_kassir_balanssiz(client, mk, db, env):
    comp, branch, w, users = env
    w2 = _wallet(db, comp, branch, balance=900, name="Ikkinchi")
    _wallet(db, comp, branch, balance=1, name="Nofaol", is_active=False)
    r = client.login(users[R.cashier]).get("/api/finance/wallets")
    assert r.status_code == 200
    rows = r.json()
    assert {x["id"] for x in rows} == {w.id, w2.id}
    for row in rows:
        assert "balance" not in row and "detailed_balances" not in row
        assert row["name"]


def test_wallets_kassir_biriktirilgan_kassa_bilan(client, mk, db, env):
    comp, branch, w, users = env
    w2 = _wallet(db, comp, branch, name="Ikkinchi")
    cashier = users[R.cashier]
    db.add(UserWallet(user_id=cashier.id, wallet_id=w2.id, is_default=True, company_id=comp.id))
    db.flush()
    rows = client.login(cashier).get("/api/finance/wallets").json()
    assert [x["id"] for x in rows] == [w2.id]
    assert "balance" not in rows[0]


@pytest.mark.parametrize("role", [R.admin, R.director, R.accountant, R.manager])
def test_wallets_finance_roles_balans_bilan(client, env, role):
    _, _, w, users = env
    rows = client.login(users[role]).get("/api/finance/wallets").json()
    row = next(x for x in rows if x["id"] == w.id)
    assert row["balance"] == 500.0
    assert "detailed_balances" not in row     # T2.8: WalletBalance bo'yicha taqsimot olib tashlandi (N+1)


# ─── Mijoz qarzi to'lovi ─────────────────────────────────────────────────────

def _customer(db, company, debt=1000):
    cu = Customer(name="Mijoz", phone="998901112233", company_id=company.id,
                  debt_balance=Decimal(debt), debt_balances={"UZS": debt})
    db.add(cu)
    db.flush()
    return cu


@pytest.mark.parametrize("role", [R.cashier, R.accountant, R.manager, R.admin, R.director])
def test_qarz_tolash_ruxsat_etilgan_rollar(client, db, env, role):
    comp, _, w, users = env
    cu = _customer(db, comp)
    r = client.login(users[role]).post(
        f"/api/finance/customer-debts/{cu.id}/pay", json={"amount": 100, "wallet_id": w.id})
    assert r.status_code != 403, r.text


def test_qarz_tolash_omborchi_403(client, db, env):
    comp, _, w, users = env
    cu = _customer(db, comp)
    r = client.login(users[R.warehouse]).post(
        f"/api/finance/customer-debts/{cu.id}/pay", json={"amount": 100, "wallet_id": w.id})
    assert r.status_code == 403


def test_customers_pay_debt_kassir_otadi_omborchi_yopiq(client, db, env):
    comp, _, w, users = env
    cu = _customer(db, comp)
    body = {"amount": 100}
    assert client.login(users[R.cashier]).post(f"/api/customers/{cu.id}/pay-debt", json=body).status_code != 403
    assert client.login(users[R.warehouse]).post(f"/api/customers/{cu.id}/pay-debt", json=body).status_code == 403


# ─── Korxonalararo izolyatsiya ───────────────────────────────────────────────

def test_ikki_korxona_izolyatsiyasi(client, mk, db, env):
    _, _, w_a, users = env
    comp_b, branch_b, _wh, admin_b = mk.tenant()
    w_b = _wallet(db, comp_b, branch_b, name="B kassa")
    # A buxgalteri B kassasiga kira olmaydi
    ca = client.login(users[R.accountant])
    assert ca.get(f"/api/kassa/{w_b.id}").status_code == 404
    assert ca.get(f"/api/kassa/{w_b.id}/history").status_code == 404
    # A admini B kassasini o'chira/o'zgartira olmaydi
    cadm = client.login(users[R.admin])
    assert cadm.delete(f"/api/kassa/{w_b.id}").status_code == 404
    assert cadm.post(f"/api/kassa/{w_b.id}/withdraw", json={"amount": 10}).status_code == 404
    # ro'yxatda faqat o'z kassasi
    ids = {x["id"] for x in ca.get("/api/kassa").json()}
    assert w_a.id in ids and w_b.id not in ids
    ids = {x["id"] for x in ca.get("/api/finance/wallets").json()}
    assert w_a.id in ids and w_b.id not in ids
    # ijobiy: o'z resursi
    assert ca.get(f"/api/kassa/{w_a.id}").status_code == 200
    assert client.login(admin_b).get(f"/api/kassa/{w_b.id}").status_code == 200


# ─── Router-level qoplama ────────────────────────────────────────────────────

def test_kassa_router_darajasida_dependency():
    from app.routers import kassa
    assert kassa.router.dependencies, "router darajasida require_module_roles bo'lishi kerak"


def test_require_module_roles_deny_override(mk, env):
    from fastapi import HTTPException
    from app.core.dependencies import require_module_roles
    comp, branch, _, users = env
    chk = require_module_roles("kassa", R.admin)
    # rol tekshiruvi Depends(require_roles) orqali (endpoint testlarida qoplangan);
    # bu yerda checker ichidagi deny-override to'g'ridan-to'g'ri tekshiriladi
    assert chk(users[R.admin]) is users[R.admin]
    denied = _user(mk, comp, branch, R.admin, permissions={"kassa": False})
    with pytest.raises(HTTPException) as e:
        chk(denied)
    assert e.value.status_code == 403 and "maxsus cheklov" in e.value.detail
    sa = _user(mk, comp, branch, R.super_admin, permissions={"kassa": False})
    assert chk(sa) is sa
