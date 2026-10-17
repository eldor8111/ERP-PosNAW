"""T2.1 — hisobot/dashboard/moliya uchun rol bo'yicha filial izolyatsiyasi.

Qamrov: `user_has_all_branches` (permissions / custom_role / aniq False), `resolve_report_scope`
(cheklangan menejer, all_branches, filialsiz menejer, accountant/director, begona filial),
`resolve_company_id`, `/reports/scope`, `/reports/profit-loss` va boshqa hisobotlarda majburiy filial,
`/finance/cash-balance` (rol, obuna tugagan admin, super_admin company_id, korxona izolyatsiyasi),
`/finance/expenses` va `/finance/transactions`, rol konstantalari yagonaligi, frontend fayllari.
"""
import itertools
import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.core.branch_context import BranchContext
from app.core.report_scope import (
    ReportScope, effective_ctx, resolve_company_id, resolve_report_scope, user_has_all_branches,
)
from app.core.roles import DASHBOARD_ROLES, FINANCE_ROLES, REPORT_ROLES
from app.core.security import create_access_token
from app.models.moliya import Expense, ExpenseCategory, Transaction
from app.models.product import Product
from app.models.role import Role
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
PERIOD = {'date_from': '2020-01-01', 'date_to': '2099-12-31'}


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _product(db, company):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T21-{n}", barcode=f"B21-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    return p


def _sale(db, user, company, product, warehouse, branch, amount=1000, cost=400):
    n = next(_seq)
    s = Sale(number=f"ST21-{n}", cashier_id=user.id, company_id=company.id, warehouse_id=warehouse.id,
             branch_id=branch.id, total_amount=Decimal(amount), paid_amount=Decimal(amount),
             payment_type=PaymentType.cash, status=SaleStatus.completed)
    db.add(s)
    db.flush()
    db.add(SaleItem(sale_id=s.id, product_id=product.id, quantity=Decimal(1), unit_price=Decimal(amount),
                    cost_price=Decimal(cost), subtotal=Decimal(amount), currency_code="UZS", exchange_rate=1))
    db.flush()
    return s


def _expense(db, company, branch, amount):
    cat = db.query(ExpenseCategory).filter(ExpenseCategory.company_id == company.id).first()
    if cat is None:
        cat = ExpenseCategory(name="Ijara", company_id=company.id)
        db.add(cat)
        db.flush()
    e = Expense(company_id=company.id, branch_id=branch.id, category_id=cat.id, amount=Decimal(amount))
    db.add(e)
    db.flush()
    return e


def _tx(db, company, branch, amount, tx_type="income"):
    t = Transaction(company_id=company.id, branch_id=branch.id, type=tx_type, amount=Decimal(amount),
                    reference_type="other_income" if tx_type == "income" else "other_expense",
                    currency_code="UZS", payment_type="cash")
    db.add(t)
    db.flush()
    return t


@pytest.fixture
def w(db, mk):
    """A korxona: a1 (wh1), a2 (wh2); admin, director, accountant, filial-1 menejeri, kassir, omborchi.
    B korxona: alohida tenant (admin_b, b1)."""
    ca, a1, wh1, admin = mk.tenant(UserRole.admin)
    a2 = mk.branch(ca, "Yunusobod")
    wh2 = mk.warehouse(ca, a2, name="Ombor Yunusobod")
    director = mk.user(ca, role=UserRole.director)
    acc = mk.user(ca, role=UserRole.accountant)
    mgr = mk.user(ca, role=UserRole.manager, branch=a1)
    mgr_free = mk.user(ca, role=UserRole.manager)                    # filialsiz menejer
    cashier = mk.user(ca, role=UserRole.cashier, branch=a1)
    keeper = mk.user(ca, role=UserRole.warehouse, branch=a1)
    prod = _product(db, ca)
    cb, b1, whb, admin_b = mk.tenant(UserRole.admin)
    prod_b = _product(db, cb)
    return dict(ca=ca, a1=a1, a2=a2, wh1=wh1, wh2=wh2, admin=admin, director=director, acc=acc, mgr=mgr,
                mgr_free=mgr_free, cashier=cashier, keeper=keeper, prod=prod,
                cb=cb, b1=b1, whb=whb, admin_b=admin_b, prod_b=prod_b)


def _seed(db, w):
    """a1: tushum 10000, xarajat 2000, kirim 300; a2: tushum 6000, xarajat 500, kirim 200; B: boshqa korxona."""
    admin, ca = w['admin'], w['ca']
    _sale(db, admin, ca, w['prod'], w['wh1'], w['a1'], 10000, 4000)
    _sale(db, admin, ca, w['prod'], w['wh2'], w['a2'], 6000, 2000)
    _expense(db, ca, w['a1'], 2000)
    _expense(db, ca, w['a2'], 500)
    _tx(db, ca, w['a1'], 300)
    _tx(db, ca, w['a2'], 200)
    _sale(db, w['admin_b'], w['cb'], w['prod_b'], w['whb'], w['b1'], 99000, 1000)
    _expense(db, w['cb'], w['b1'], 7777)
    _tx(db, w['cb'], w['b1'], 5555)


def _grant(db, user, value=True):
    user.permissions = {"reports": {"all_branches": value}}
    db.flush()


# ── 1. user_has_all_branches ─────────────────────────────────────────────────

def test_has_all_branches_via_user_permissions(db, w):
    assert user_has_all_branches(w['mgr']) is False
    _grant(db, w['mgr'])
    assert user_has_all_branches(w['mgr']) is True


def test_has_all_branches_via_custom_role(db, w):
    role = Role(name="Hudud menejeri", company_id=w['ca'].id, permissions={"reports": {"all_branches": True}})
    db.add(role)
    db.flush()
    w['mgr'].custom_role = role
    db.flush()
    assert user_has_all_branches(w['mgr']) is True


def test_user_level_false_overrides_custom_role(db, w):
    role = Role(name="Hudud", company_id=w['ca'].id, permissions={"reports": {"all_branches": True}})
    db.add(role)
    db.flush()
    w['mgr'].custom_role = role
    _grant(db, w['mgr'], False)
    assert user_has_all_branches(w['mgr']) is False


@pytest.mark.parametrize("perms", [None, {}, {"reports": True}, {"reports": {"view": True}},
                                   {"reports": {"all_branches": "yes"}}])
def test_has_all_branches_defaults_false(db, w, perms):
    w['mgr'].permissions = perms
    assert user_has_all_branches(w['mgr']) is False


# ── 2. resolve_report_scope ──────────────────────────────────────────────────

def test_scope_manager_forced_to_own_branch(db, w):
    s = resolve_report_scope(db, w['mgr'], None)
    assert s == ReportScope(True, w['a1'].id, (w['a1'].id,))
    assert resolve_report_scope(db, w['mgr'], w['a1'].id).branch_id == w['a1'].id


def test_scope_manager_other_branch_403(db, w):
    with pytest.raises(HTTPException) as ei:
        resolve_report_scope(db, w['mgr'], w['a2'].id)
    assert ei.value.status_code == 403 and ei.value.detail == "Bu filial hisobotiga ruxsat yo'q"
    with pytest.raises(HTTPException) as ei2:
        resolve_report_scope(db, w['mgr'], w['b1'].id)         # begona korxona filiali ham 403
    assert ei2.value.status_code == 403
    with pytest.raises(HTTPException):
        resolve_report_scope(db, w['mgr'], -1)                 # filialsiz guruh cheklanganga yopiq


def test_scope_manager_with_all_branches_unrestricted(db, w):
    _grant(db, w['mgr'])
    assert resolve_report_scope(db, w['mgr'], None) == ReportScope(False, None)
    assert resolve_report_scope(db, w['mgr'], w['a2'].id) == ReportScope(False, w['a2'].id)


def test_scope_manager_custom_role_all_branches(db, w):
    role = Role(name="Hudud", company_id=w['ca'].id, permissions={"reports": {"all_branches": True}})
    db.add(role)
    db.flush()
    w['mgr'].custom_role = role
    db.flush()
    assert resolve_report_scope(db, w['mgr'], w['a2'].id) == ReportScope(False, w['a2'].id)


def test_scope_branchless_manager_unrestricted(db, w):
    assert resolve_report_scope(db, w['mgr_free'], None) == ReportScope(False, None)
    assert resolve_report_scope(db, w['mgr_free'], w['a2'].id).branch_id == w['a2'].id


@pytest.mark.parametrize("who", ["acc", "director", "admin"])
def test_scope_company_wide_roles_unrestricted(db, w, who):
    u = w[who]
    assert resolve_report_scope(db, u, None) == ReportScope(False, None)
    assert resolve_report_scope(db, u, w['a2'].id) == ReportScope(False, w['a2'].id)
    assert resolve_report_scope(db, u, -1).branch_id == -1


def test_accountant_with_assigned_branch_still_unrestricted(db, mk, w):
    acc1 = mk.user(w['ca'], role=UserRole.accountant, branch=w['a1'])
    assert resolve_report_scope(db, acc1, None) == ReportScope(False, None)
    assert resolve_report_scope(db, acc1, w['a2'].id).branch_id == w['a2'].id


def test_scope_foreign_company_branch_404_for_unrestricted(db, w):
    for who in ("admin", "acc", "director", "mgr_free"):
        with pytest.raises(HTTPException) as ei:
            resolve_report_scope(db, w[who], w['b1'].id)
        assert ei.value.status_code == 404


def test_scope_multi_branch_manager_primary_and_allowed(db, mk, w):
    from app.models.user_branch import UserBranch
    for b in (w['a1'], w['a2']):
        db.add(UserBranch(user_id=w['mgr'].id, company_id=w['ca'].id, branch_id=b.id))
    db.flush()
    s = resolve_report_scope(db, w['mgr'], None)
    assert s.restricted and set(s.allowed_branch_ids) == {w['a1'].id, w['a2'].id}
    assert s.branch_id in s.allowed_branch_ids
    assert resolve_report_scope(db, w['mgr'], w['a2'].id).branch_id == w['a2'].id


# ── 3. resolve_company_id / effective_ctx / konstantalar ─────────────────────

def test_resolve_company_id(db, mk, w):
    assert resolve_company_id(w['admin'], None) == w['ca'].id
    assert resolve_company_id(w['admin'], w['cb'].id) == w['ca'].id          # boshqa rollar parametrni e'tiborsiz
    sa = mk.user(None, role=UserRole.super_admin)
    with pytest.raises(HTTPException) as ei:
        resolve_company_id(sa, None)
    assert ei.value.status_code == 400
    assert resolve_company_id(sa, w['cb'].id) == w['cb'].id
    sa2 = mk.user(w['ca'], role=UserRole.super_admin)
    assert resolve_company_id(sa2, None) == w['ca'].id
    assert resolve_company_id(sa2, w['cb'].id) == w['cb'].id


def test_effective_ctx_lifts_only_for_all_branches(db, w):
    restricted = BranchContext(w['a1'].id, frozenset({w['a1'].id}), False, False, w['mgr'].id)
    assert effective_ctx(w['mgr'], restricted) is restricted
    _grant(db, w['mgr'])
    lifted = effective_ctx(w['mgr'], restricted)
    assert lifted.allowed_branch_ids is None and lifted.branch_id is None
    bypass = BranchContext(None, None, True, False, 1)
    assert effective_ctx(w['mgr'], bypass) is bypass
    assert effective_ctx(w['mgr'], None) is None


def test_role_constants():
    assert set(REPORT_ROLES) == {UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant,
                                 UserRole.super_admin}
    assert set(FINANCE_ROLES) == {UserRole.admin, UserRole.director, UserRole.accountant, UserRole.manager}
    assert set(DASHBOARD_ROLES) == {UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant}


def test_role_constants_defined_once():
    base = os.path.join(ROOT, 'app', 'routers')
    for fname in ('reports.py', 'sales_report.py', 'finance_report.py', 'finance.py', 'dashboard.py'):
        src = open(os.path.join(base, fname), encoding='utf-8').read()
        assert not re.search(r'^(REPORT_ROLES|FINANCE_ROLES|MGMT_ROLES)\s*=', src, re.M), fname
        assert 'app.core.roles' in src, fname


# ── 4. /reports/scope ────────────────────────────────────────────────────────

def test_reports_scope_endpoint(client, db, w):
    r = client.login(w['mgr']).get('/api/reports/scope')
    assert r.status_code == 200
    assert r.json()['restricted'] is True and r.json()['branch_id'] == w['a1'].id
    assert r.json()['can_select_all'] is False
    _grant(db, w['mgr'])
    j = client.login(w['mgr']).get('/api/reports/scope').json()
    assert j == {"restricted": False, "branch_id": None, "can_select_all": True, "allowed_branch_ids": None}
    for who in ("acc", "director", "admin", "mgr_free"):
        j = client.login(w[who]).get('/api/reports/scope').json()
        assert j['restricted'] is False and j['can_select_all'] is True
    assert client.login(w['cashier']).get('/api/reports/scope').status_code == 403


# ── 5. /reports/profit-loss (qabul mezonlari 1-4) ────────────────────────────

def _pl(client, user, **params):
    return client.login(user).get('/api/reports/profit-loss', params={**PERIOD, **params})


def test_manager_profit_loss_only_own_branch(client, db, w):
    _seed(db, w)
    r = _pl(client, w['mgr'])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['gross_revenue'] == 10000          # faqat a1 omborlari/sotuvlari
    assert d['expenses']['total'] == 2000       # faqat a1 xarajatlari
    assert d['other_income'] == 300             # faqat a1 kirimi
    assert _pl(client, w['mgr'], branch_id=w['a1'].id).json()['gross_revenue'] == 10000


def test_manager_profit_loss_other_branch_403(client, db, w):
    _seed(db, w)
    assert _pl(client, w['mgr'], branch_id=w['a2'].id).status_code == 403
    assert _pl(client, w['mgr'], branch_id=w['b1'].id).status_code == 403


def test_manager_all_branches_permission_sees_other_branch(client, db, w):
    _seed(db, w)
    _grant(db, w['mgr'])
    assert _pl(client, w['mgr'], branch_id=w['a2'].id).json()['gross_revenue'] == 6000
    assert _pl(client, w['mgr']).json()['gross_revenue'] == 16000


def test_manager_custom_role_all_branches(client, db, w):
    _seed(db, w)
    role = Role(name="Hudud", company_id=w['ca'].id, permissions={"reports": {"all_branches": True}})
    db.add(role)
    db.flush()
    w['mgr'].custom_role = role
    db.flush()
    assert _pl(client, w['mgr'], branch_id=w['a2'].id).json()['gross_revenue'] == 6000


@pytest.mark.parametrize("who", ["acc", "director", "admin", "mgr_free"])
def test_company_wide_roles_profit_loss(client, db, w, who):
    _seed(db, w)
    assert _pl(client, w[who]).json()['gross_revenue'] == 16000
    assert _pl(client, w[who], branch_id=w['a2'].id).json()['gross_revenue'] == 6000
    assert _pl(client, w[who], branch_id=w['b1'].id).status_code == 404     # begona korxona filiali


def test_profit_loss_cashier_and_keeper_forbidden(client, db, w):
    assert _pl(client, w['cashier']).status_code == 403
    assert _pl(client, w['keeper']).status_code == 403


def test_finance_profit_loss_manager_restricted(client, db, w):
    _seed(db, w)
    c = client.login(w['mgr'])
    d = c.get('/api/finance/profit-loss', params=PERIOD).json()
    assert d['gross_revenue'] == 10000
    assert c.get('/api/finance/profit-loss', params={**PERIOD, 'branch_id': w['a2'].id}).status_code == 403


def test_pnl_compare_manager_restricted(client, db, w):
    _seed(db, w)
    cmp_q = {'p1_from': '2020-01-01', 'p1_to': '2099-12-31', 'p2_from': '2020-01-01', 'p2_to': '2099-12-31'}
    c = client.login(w['mgr'])
    assert c.get('/api/reports/pnl-compare', params={**cmp_q, 'branch_id': w['a2'].id}).status_code == 403


# ── 6. Boshqa hisobotlar ─────────────────────────────────────────────────────

def test_reports_expenses_manager_restricted(client, db, w):
    _seed(db, w)
    c = client.login(w['mgr'])
    d = c.get('/api/reports/expenses', params=PERIOD).json()
    assert d['total'] == 2000
    assert c.get('/api/reports/expenses', params={**PERIOD, 'branch_id': w['a2'].id}).status_code == 403
    assert client.login(w['acc']).get('/api/reports/expenses', params=PERIOD).json()['total'] == 2500


@pytest.fixture
def sqlite_dates(monkeypatch):
    """SQLite `CAST(x AS DATE)` sana emas son qaytaradi; kunlik hisobotlar uchun `date()` bilan almashtiriladi."""
    import app.routers.reports as reports_mod
    import app.routers.sales_report as sales_report_mod
    from sqlalchemy import func
    for mod in (reports_mod, sales_report_mod):
        monkeypatch.setattr(mod, 'cast', lambda expr, _type: func.date(expr))


def test_reports_sales_returns_purchases_product_sales_restricted(client, db, w, sqlite_dates):
    _seed(db, w)
    c = client.login(w['mgr'])
    for path in ('sales', 'returns', 'purchases', 'product-sales', 'daily-sales', 'top-products',
                 'cashier-report', 'abc-xyz', 'profit', 'batches'):
        r = c.get(f'/api/reports/{path}', params={**PERIOD, 'branch_id': w['a2'].id})
        assert r.status_code == 403, (path, r.status_code)
        ok = c.get(f'/api/reports/{path}', params=PERIOD)
        assert ok.status_code == 200, (path, ok.status_code, ok.text[:200])


def test_reports_sales_list_forced_branch(client, db, w):
    _seed(db, w)
    d = client.login(w['mgr']).get('/api/reports/sales', params=PERIOD).json()
    assert d['total_count'] == 1 and [i['total_amount'] for i in d['items']] == [10000.0]
    full = client.login(w['acc']).get('/api/reports/sales', params=PERIOD).json()
    assert full['total_count'] == 2
    assert client.login(w['acc']).get('/api/reports/sales', params={**PERIOD, 'branch_id': w['a2'].id}).json()['total_count'] == 1


def test_product_sales_forced_branch(client, db, w, sqlite_dates):
    _seed(db, w)
    d = client.login(w['mgr']).get('/api/reports/product-sales', params=PERIOD).json()
    assert round(sum(r['total_revenue'] for r in d), 2) == 10000.0
    d2 = client.login(w['acc']).get('/api/reports/product-sales', params=PERIOD).json()
    assert round(sum(r['total_revenue'] for r in d2), 2) == 16000.0


def test_1c_export_manager_forced_branch(client, db, w):
    """1C eksport JWT bilan (haqiqiy token): cheklangan menejer boshqa filialni so'ray olmaydi."""
    from app.main import app
    from app.core.dependencies import get_current_user, get_current_user_allow_expired
    _seed(db, w)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_allow_expired, None)
    tok = create_access_token({"sub": str(w['mgr'].id), "company_id": w['ca'].id, "role": "manager"})
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get('/api/reports/1c-export', params={**PERIOD, 'branch_id': w['a2'].id}, headers=h).status_code == 403
    r = client.get('/api/reports/1c-export', params=PERIOD, headers=h)
    assert r.status_code == 200, r.text
    tok2 = create_access_token({"sub": str(w['acc'].id), "company_id": w['ca'].id, "role": "accountant"})
    r2 = client.get('/api/reports/1c-export', params={**PERIOD, 'branch_id': w['a2'].id},
                    headers={"Authorization": f"Bearer {tok2}"})
    assert r2.status_code == 200


def test_reports_dashboard_accountant_allowed(client, db, w, monkeypatch):
    import app.routers.reports as reports_mod
    from sqlalchemy import func
    monkeypatch.setattr(reports_mod, 'cast', lambda expr, _type: func.date(expr))
    assert client.login(w['acc']).get('/api/reports/dashboard').status_code == 200
    assert client.login(w['cashier']).get('/api/reports/dashboard').status_code == 403
    assert client.login(w['mgr']).get('/api/reports/dashboard', params={'branch_id': w['a2'].id}).status_code == 403


def test_dashboard_summary_accountant_allowed(client, db, w):
    assert client.login(w['acc']).get('/api/dashboard/summary').status_code == 200
    assert client.login(w['cashier']).get('/api/dashboard/summary').status_code == 403


def test_all_branches_lifts_ctx_endpoints(client, db, w):
    """ctx asosidagi endpointlar (dead-stock) ham all_branches huquqini hisobga oladi."""
    c = client.login(w['mgr'])
    assert c.get('/api/reports/dead-stock', params={'branch_id': w['a2'].id}).status_code == 403
    _grant(db, w['mgr'])
    assert c.get('/api/reports/dead-stock', params={'branch_id': w['a2'].id}).status_code == 200


# ── 7. /finance/expenses, /finance/transactions ──────────────────────────────

def test_finance_expenses_manager_restricted(client, db, w):
    _seed(db, w)
    c = client.login(w['mgr'])
    rows = c.get('/api/finance/expenses').json()
    assert {r['branch_id'] for r in rows} == {w['a1'].id} and len(rows) == 1
    assert c.get('/api/finance/expenses', params={'branch_id': w['a2'].id}).status_code == 403
    assert len(client.login(w['acc']).get('/api/finance/expenses').json()) == 2
    assert len(client.login(w['acc']).get('/api/finance/expenses', params={'branch_id': w['a2'].id}).json()) == 1


def test_finance_transactions_manager_restricted(client, db, w):
    _seed(db, w)
    c = client.login(w['mgr'])
    rows = c.get('/api/finance/transactions').json()
    assert rows and {r['branch_id'] for r in rows} == {w['a1'].id}
    assert c.get('/api/finance/transactions', params={'branch_id': w['a2'].id}).status_code == 403
    _grant(db, w['mgr'])
    rows2 = c.get('/api/finance/transactions', params={'branch_id': w['a2'].id}).json()
    assert rows2 and {r['branch_id'] for r in rows2} == {w['a2'].id}


# ── 8. /finance/cash-balance (qabul mezonlari 5, 6, 8) ───────────────────────

def _cash(client, user, **params):
    return client.login(user).get('/api/finance/cash-balance', params=params)


def test_cash_balance_roles(client, db, w):
    _seed(db, w)
    assert _cash(client, w['cashier']).status_code == 403
    assert _cash(client, w['keeper']).status_code == 403
    for who in ("admin", "director", "acc", "mgr_free"):
        assert _cash(client, w[who]).status_code == 200, who


def test_cash_balance_manager_own_branch(client, db, w):
    _seed(db, w)
    r = _cash(client, w['mgr'])
    assert r.status_code == 200
    assert r.json()['total_income'] == 300
    assert _cash(client, w['mgr'], branch_id=w['a2'].id).status_code == 403
    _grant(db, w['mgr'])
    assert _cash(client, w['mgr'], branch_id=w['a2'].id).json()['total_income'] == 200


def test_cash_balance_company_isolation_and_keys(client, db, w):
    _seed(db, w)
    d = _cash(client, w['admin']).json()
    assert d['total_income'] == 500                      # B korxona kirimi (5555) aralashmaydi
    assert d['company_name'] == w['ca'].name and d['org_code'] == w['ca'].org_code
    for key in ("total_income", "total_expense", "total_income_uzs", "total_expense_uzs", "balance_uzs",
                "income_by_currency", "expense_by_currency", "balance_by_currency", "balance"):
        assert key in d
    assert _cash(client, w['admin'], branch_id=w['a2'].id).json()['total_income'] == 200
    assert _cash(client, w['admin'], branch_id=w['b1'].id).status_code == 404   # begona korxona filiali
    assert _cash(client, w['admin_b']).json()['total_income'] == 5555


def test_cash_balance_super_admin_requires_company(client, db, mk, w):
    _seed(db, w)
    sa = mk.user(None, role=UserRole.super_admin)
    assert _cash(client, sa).status_code == 400
    ra = _cash(client, sa, company_id=w['ca'].id).json()
    rb = _cash(client, sa, company_id=w['cb'].id).json()
    assert ra['total_income'] == 500 and ra['company_name'] == w['ca'].name
    assert rb['total_income'] == 5555 and rb['company_name'] == w['cb'].name


def test_cash_balance_expired_subscription_admin_ok(client, db, w):
    """Obuna muddati tugagan admin: cash-balance 200 (allow_expired), oddiy endpoint esa 402."""
    from app.main import app
    from app.core.dependencies import get_current_user, get_current_user_allow_expired
    _seed(db, w)
    w['ca'].subscription_ends_at = datetime.now(timezone.utc) - timedelta(days=3)
    db.flush()
    client.login(w['admin'])
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_allow_expired, None)
    tok = create_access_token({"sub": str(w['admin'].id), "company_id": w['ca'].id, "role": "admin"})
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get('/api/finance/cash-balance', headers=h).status_code == 200
    assert client.get('/api/finance/expenses', headers=h).status_code == 402
    tok_c = create_access_token({"sub": str(w['cashier'].id), "company_id": w['ca'].id, "role": "cashier"})
    assert client.get('/api/finance/cash-balance', headers={"Authorization": f"Bearer {tok_c}"}).status_code == 403


# ── 9. Frontend ──────────────────────────────────────────────────────────────

def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding='utf-8').read()


KEYS_T2_1 = ["reports.scopeRestricted", "reports.noAccessBranch", "roles.allBranches"]


def _merged_i18n(keys):
    """T2.x i18n kalitlari uz/ru/en lug'atlariga birlashtirilgan (pending fayl o'chirilgan):
    {til: {kalit: qiymat}}; kalit lug'atda yo'q bo'lsa KeyError."""
    import re as _re
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'i18n'))
    out = {}
    for lang in ('uz', 'ru', 'en'):
        with open(os.path.join(base, lang + '.js'), encoding='utf-8') as f:
            txt = f.read()
        found = {m.group(1): m.group(2) for m in _re.finditer(r"^\s*'([^']+)':\s*(.+?),?\s*$", txt, _re.M)}
        out[lang] = {k: found[k] for k in keys}
    return out


def test_pending_i18n_keys_same_in_all_languages():
    data = _merged_i18n(KEYS_T2_1)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    for key in ('reports.scopeRestricted', 'reports.noAccessBranch', 'roles.allBranches'):
        assert key in data['uz'] and data['uz'][key]


def test_frontend_files_present_and_wired():
    for rel in (('hooks', 'useReportScope.js'), ('components', 'BranchSelect.jsx')):
        assert os.path.isfile(os.path.join(ROOT, 'frontend', 'src', *rel)), rel
    assert 'reports/scope' in _read('frontend', 'src', 'hooks', 'useReportScope.js')
    for page in ('Reports.jsx', 'Purchases.jsx'):
        assert 'BranchSelect' in _read('frontend', 'src', 'pages', 'admin', page), page
    prof = _read('frontend', 'src', 'pages', 'admin', 'Profile.jsx')
    assert 'useReportScope' in prof
    layout = _read('frontend', 'src', 'components', 'AdminLayout.jsx')
    assert '/billing/my-company' in layout and "api.get('/finance/cash-balance'" not in layout
    axios_src = _read('frontend', 'src', 'api', 'axios.js')
    # T3.8: axios.js dagi o'lik SWR keshi (TTL ro'yxati) olib tashlandi — endi filial header'i tekshiriladi
    assert 'X-Branch-Id' in axios_src
    assert 'all_branches' in _read('frontend', 'src', 'pages', 'admin', 'Settings', 'Roles.jsx')
    assert 'useReportScope' in _read('frontend', 'src', 'pages', 'admin', 'Shifts.jsx')
