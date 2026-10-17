"""C2.1 — 2-bosqich tozalash: backend qoldiqlari.

Qamrov: P&L xarajat UZS ekvivalentida; dashboard/summary va ai_scope kam qoldiq = stock_report; REPORT_ROLES yagona;
reports.all_branches huquqli menejer (BranchContext) butun korxonani ko'radi; 1C eksport cheklangan menejerda bitta
filial; begona filial P&L 404; model indekslari; create_company asosiy filial/ombor/kassa; AI /confirm "❌" -> ERROR;
Shift korxona filtri; production ombor filiali; inventory BranchContext.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_C2_1.py -q -p no:cacheprovider
"""
import itertools
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.ai_audit import AIAuditLog
from app.models.batch import Batch
from app.models.bom import BOM, BOMItem
from app.models.branch import Branch
from app.models.inventory import StockLevel
from app.models.moliya import Expense, ExpenseCategory, Wallet
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.shift import Shift
from app.models.user import UserRole
from app.models.warehouse import Warehouse
from app.utils.report_utils import _date_range, local_day_start, local_today

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
D = Decimal


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _now():
    """Bugungi kun ichidagi vaqt (Toshkent kuni boshlanishidan 1 soat keyin) — kun chegarasidan xavfsiz."""
    return local_day_start(local_today()) + timedelta(hours=1)


def _product(db, company, min_stock=0, **kw):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"C21-{n}", barcode=f"BC21-{n}", company_id=company.id,
                cost_price=D("500"), sale_price=D("1000"), min_stock=min_stock, **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty):
    sl = StockLevel(product_id=product.id, warehouse_id=warehouse.id, quantity=D(qty))
    db.add(sl)
    db.flush()
    return sl


def _sale(db, user, company, warehouse, branch, amount=1000):
    n = next(_seq)
    s = Sale(number=f"SC21-{n}", cashier_id=user.id, company_id=company.id, warehouse_id=warehouse.id,
             branch_id=branch.id, total_amount=D(amount), paid_amount=D(amount), paid_cash=D(amount),
             payment_type=PaymentType.cash, status=SaleStatus.completed, created_at=_now())
    db.add(s)
    db.flush()
    return s


def _cat(db, company, name=None):
    c = ExpenseCategory(name=name or f"Kat {next(_seq)}", company_id=company.id)
    db.add(c)
    db.flush()
    return c


def _expense(db, company, branch, amount, **kw):
    cat = kw.pop('cat', None) or _cat(db, company)
    e = Expense(company_id=company.id, branch_id=branch.id, category_id=cat.id, amount=D(amount),
                created_at=_now(), **kw)
    db.add(e)
    db.flush()
    return e


@pytest.fixture
def w(db, mk):
    """A korxona: a1 (wh1), a2 (wh2), admin; B korxona alohida tenant."""
    ca, a1, wh1, admin = mk.tenant(UserRole.admin)
    a2 = mk.branch(ca, "Yunusobod")
    wh2 = mk.warehouse(ca, a2, name="Ombor Yunusobod")
    cb, b1, whb, admin_b = mk.tenant(UserRole.admin)
    return dict(ca=ca, a1=a1, a2=a2, wh1=wh1, wh2=wh2, admin=admin, cb=cb, b1=b1, whb=whb, admin_b=admin_b)


# ── 1. Xarajat UZS da ────────────────────────────────────────────────────────

def test_pnl_expense_uses_uzs_equivalent(db, w):
    from app.services.pnl_service import compute_pnl
    cat = _cat(db, w['ca'], "Ijara")
    _expense(db, w['ca'], w['a1'], 100, cat=cat, currency="USD", exchange_rate=D("12700"), amount_uzs=D("1270000"))
    _expense(db, w['ca'], w['a1'], 5000, cat=cat)                      # eski yozuv: amount_uzs NULL -> amount
    start, end = _date_range(local_today(), local_today())
    p = compute_pnl(db, w['ca'].id, start, end, None)
    assert p['expenses']['total'] == 1_275_000
    assert p['expenses']['by_category'] == [{"name": "Ijara", "total": 1_275_000.0}]
    assert compute_pnl(db, w['ca'].id, start, end, w['a2'].id)['expenses']['total'] == 0


def test_profit_loss_endpoint_expense_uzs(client, db, w):
    _expense(db, w['ca'], w['a1'], 10, currency="USD", exchange_rate=D("12700"), amount_uzs=D("127000"))
    r = client.login(w['admin']).get('/api/reports/profit-loss')
    assert r.status_code == 200, r.text
    assert r.json()['expenses']['total'] == 127_000


# ── 2. Kam qoldiq yagona ta'rifi ─────────────────────────────────────────────

def test_dashboard_low_stock_equals_stock_report(client, db, w):
    from app.services import stock_report
    p = _product(db, w['ca'], min_stock=10)                            # ikki omborda 3+4 = 7 < 10 -> 1 mahsulot
    _stock(db, p, w['wh1'], 3)
    _stock(db, p, w['wh2'], 4)
    ok = _product(db, w['ca'], min_stock=5)
    _stock(db, ok, w['wh1'], 50)
    expected = stock_report.low_stock_count(db, w['ca'].id, None)
    assert expected == 1
    r = client.login(w['admin']).get('/api/dashboard/summary')
    assert r.status_code == 200, r.text
    assert r.json()['low_stock_count'] == expected                     # eski formula: 2 (qator) edi
    # filial doirasi ham yagona funksiya bilan
    r = client.login(w['admin']).get('/api/dashboard/summary', params={'branch_id': w['a1'].id})
    assert r.json()['low_stock_count'] == stock_report.low_stock_count(db, w['ca'].id, [w['wh1'].id])


def test_ai_reports_use_unified_low_stock(db, w):
    """AI/Telegram hisobotlari yagona ta'rifdan (`low_stock_count_for_scope`) foydalanadi (T2.3)."""
    from app.services import stock_report
    from app.services.ai_scope import resolve_ai_scope
    p = _product(db, w['ca'], min_stock=10)
    _stock(db, p, w['wh1'], 3)
    _stock(db, p, w['wh2'], 4)
    assert stock_report.low_stock_count_for_scope(db, w['ca'].id, None) == stock_report.low_stock_count(
        db, w['ca'].id, None) == 1
    scope = resolve_ai_scope(db, w['admin'], w['a1'].id)
    assert stock_report.low_stock_count_for_scope(db, w['ca'].id, scope) == stock_report.low_stock_count(
        db, w['ca'].id, [w['wh1'].id]) == 1
    for rel in ('app/routers/ai_analytics.py', 'app/routers/ai_reports.py', 'app/services/ai_service.py'):
        with open(os.path.join(ROOT, *rel.split('/')), encoding='utf-8') as f:
            assert 'low_stock_count_for_scope' in f.read()


# ── 3. REPORT_ROLES yagona ───────────────────────────────────────────────────

def test_report_roles_single_definition():
    hits = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, 'app')):
        for f in files:
            if f.endswith('.py'):
                with open(os.path.join(base, f), encoding='utf-8') as fh:
                    for line in fh:
                        if re.match(r'\s*REPORT_ROLES\s*=', line):
                            hits.append(f)
    assert hits == ['roles.py']
    from app.core.roles import REPORT_ROLES
    from app.routers import branch_reports
    assert branch_reports.REPORT_ROLES is REPORT_ROLES


# ── 4. all_branches huquqli menejer cheklanmaydi ─────────────────────────────

def test_build_branch_context_privileged_manager_unrestricted(db, mk, w):
    from app.core.branch_context import build_branch_context
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    ctx = build_branch_context(db, mgr)
    assert ctx.allowed_branch_ids == frozenset({w['a1'].id})            # huquqsiz — cheklangan
    mgr.permissions = {"reports": {"all_branches": True}}
    db.flush()
    ctx = build_branch_context(db, mgr)
    assert ctx.allowed_branch_ids is None and ctx.branch_id is None and ctx.unrestricted
    # header: o'z korxonasi filiali — ok, begona — 404
    assert build_branch_context(db, mgr, w['a2'].id).branch_id == w['a2'].id
    with pytest.raises(HTTPException) as e:
        build_branch_context(db, mgr, w['b1'].id)
    assert e.value.status_code == 404


def test_mobile_dashboard_privileged_manager_sees_company(client, db, mk, w):
    _sale(db, w['admin'], w['ca'], w['wh1'], w['a1'], 1000)
    _sale(db, w['admin'], w['ca'], w['wh2'], w['a2'], 2000)
    _sale(db, w['admin_b'], w['cb'], w['whb'], w['b1'], 99000)
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    r = client.login(mgr).get('/api/mobile/dashboard/summary')
    assert r.status_code == 200, r.text
    assert r.json()['gross'] == 1000 and r.json()['branch_id'] == w['a1'].id   # huquqsiz: faqat o'z filiali
    mgr.permissions = {"reports": {"all_branches": True}}
    db.flush()
    r = client.login(mgr).get('/api/mobile/dashboard/summary')
    assert r.status_code == 200, r.text
    assert r.json()['gross'] == 3000 and r.json()['branch_id'] is None         # butun korxona, B korxona kirmaydi
    assert client.login(mgr).get('/api/mobile/dashboard/top-products').status_code == 200


def test_reports_inventory_privileged_manager(client, db, mk, w):
    p = _product(db, w['ca'])
    _stock(db, p, w['wh1'], 1)
    _stock(db, p, w['wh2'], 2)
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    rows = client.login(mgr).get('/api/reports/inventory').json()
    assert {r['warehouse_id'] for r in rows} == {w['wh1'].id}
    assert client.login(mgr).get('/api/reports/stock-alert').status_code == 200
    mgr.permissions = {"reports": {"all_branches": True}}
    db.flush()
    rows = client.login(mgr).get('/api/reports/inventory').json()
    assert {r['warehouse_id'] for r in rows} == {w['wh1'].id, w['wh2'].id}
    summary = client.login(mgr).get('/api/reports/inventory/summary')
    assert summary.status_code == 200
    assert client.login(mgr).get('/api/reports/stock-alert').status_code == 200


# ── 5. 1C eksport doirasi ────────────────────────────────────────────────────

def _jwt(user):
    from app.core.security import create_access_token
    return {'Authorization': 'Bearer ' + create_access_token(
        {'sub': str(user.id), 'company_id': user.company_id, 'role': user.role.value})}


def _csv_numbers(resp):
    lines = resp.content.decode('utf-8-sig').strip().splitlines()
    return {ln.split(',')[0] for ln in lines[1:]}


def test_export_1c_restricted_manager_gets_own_branch_only(client, db, mk, w):
    s1 = _sale(db, w['admin'], w['ca'], w['wh1'], w['a1'], 1000)
    s2 = _sale(db, w['admin'], w['ca'], w['wh2'], w['a2'], 2000)
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    r = client.get('/api/reports/1c-export', headers=_jwt(mgr))
    assert r.status_code == 200, r.text
    assert _csv_numbers(r) == {s1.number}                              # branch_id berilmadi — baribir o'z filiali
    # ijobiy yo'l: admin butun korxona; begona korxona sotuvlari kirmaydi
    sb = _sale(db, w['admin_b'], w['cb'], w['whb'], w['b1'], 5000)
    r = client.get('/api/reports/1c-export', headers=_jwt(w['admin']))
    assert _csv_numbers(r) == {s1.number, s2.number} and sb.number not in _csv_numbers(r)


# ── 6. Begona filial P&L ─────────────────────────────────────────────────────

def test_pnl_foreign_or_missing_branch_404(client, w):
    cl = client.login(w['admin'])
    cmp_params = {'p1_from': '2020-01-01', 'p1_to': '2020-12-31', 'p2_from': '2021-01-01', 'p2_to': '2021-12-31'}
    for bad in (w['b1'].id, 999999):
        assert cl.get('/api/reports/profit-loss', params={'branch_id': bad}).status_code == 404
        assert cl.get('/api/reports/pnl-compare', params={**cmp_params, 'branch_id': bad}).status_code == 404
    # ijobiy yo'l: o'z filiali; filialsiz guruh (-1)
    for ok in (w['a1'].id, -1):
        assert cl.get('/api/reports/profit-loss', params={'branch_id': ok}).status_code == 200
        assert cl.get('/api/reports/pnl-compare', params={**cmp_params, 'branch_id': ok}).status_code == 200


def test_pnl_restricted_manager_cannot_reach_foreign_branch(client, mk, w):
    """Cheklangan menejer begona/o'zining bo'lmagan filialni ko'ra olmaydi (T2.1: 403), o'z filialini ko'radi."""
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    cl = client.login(mgr)
    for bad in (w['b1'].id, w['a2'].id):
        assert cl.get('/api/reports/profit-loss', params={'branch_id': bad}).status_code == 403
    assert cl.get('/api/reports/profit-loss', params={'branch_id': w['a1'].id}).status_code == 200


# ── 7. Model indekslari ──────────────────────────────────────────────────────

def test_model_indexes_match_migration():
    names = {ix.name for t in (Expense, ExpenseCategory) for ix in t.__table__.indexes}
    from app.models.moliya import Transaction
    names |= {ix.name for ix in Transaction.__table__.indexes}
    assert {"ix_expenses_company_branch_created", "ix_transactions_company_type_created",
            "uq_expense_cat_company_name", "uq_expense_cat_global_name"} <= names
    ix = {i.name: i for i in Expense.__table__.indexes}["ix_expenses_company_branch_created"]
    assert [c.name for c in ix.columns] == ["company_id", "branch_id", "created_at"]
    ix = {i.name: i for i in Transaction.__table__.indexes}["ix_transactions_company_type_created"]
    assert [c.name for c in ix.columns] == ["company_id", "type", "created_at"]
    # migratsiya fayli bilan bir xil nomlar
    with open(os.path.join(ROOT, 'alembic', 'versions', 't2_2_pnl_unify_expense_categories_and_indexes.py'),
              encoding='utf-8') as f:
        src = f.read()
    for n in names & {"ix_expenses_company_branch_created", "ix_transactions_company_type_created",
                      "uq_expense_cat_company_name", "uq_expense_cat_global_name"}:
        assert n in src


def test_category_unique_indexes_are_partial_on_postgres():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex
    ddl = {ix.name: str(CreateIndex(ix).compile(dialect=postgresql.dialect()))
           for ix in ExpenseCategory.__table__.indexes if ix.name.startswith("uq_expense_cat_")}
    assert "CREATE UNIQUE INDEX uq_expense_cat_company_name" in ddl["uq_expense_cat_company_name"]
    assert "(company_id, lower(trim(name))) WHERE company_id IS NOT NULL" in ddl["uq_expense_cat_company_name"]
    assert "(lower(trim(name))) WHERE company_id IS NULL" in ddl["uq_expense_cat_global_name"]


# ── 8. create_company ────────────────────────────────────────────────────────

def test_create_company_main_branch_with_warehouse_and_wallet(client, db, mk):
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).post('/api/companies', json={'name': 'Yangi Korxona'})
    assert r.status_code == 201, r.text
    cid = r.json()['id']
    branches = db.query(Branch).filter(Branch.company_id == cid).all()
    assert len(branches) == 1 and branches[0].is_main is True and branches[0].is_active
    whs = db.query(Warehouse).filter(Warehouse.company_id == cid).all()
    assert len(whs) == 1 and whs[0].branch_id == branches[0].id and whs[0].is_default is True
    wallets = db.query(Wallet).filter(Wallet.company_id == cid).all()
    assert len(wallets) == 1 and wallets[0].branch_id == branches[0].id


# ── 9. AI /confirm: "❌" javob -> ERROR ──────────────────────────────────────

def _register_tool(reply):
    from app.services.ai_tools_registry import AITool, AIToolRegistry

    class _Tool(AITool):
        name = f"c21_tool_{next(_seq)}"
        risk_level = "LOW"

        def execute(self, db, company_id, user, **kwargs):
            return {"reply": reply}

    AIToolRegistry.register(_Tool)
    return _Tool


def _pending(db, user, tool, cid):
    log = AIAuditLog(company_id=user.company_id, user_id=user.id, tool_name=tool.name, tool_arguments={},
                     status="PENDING_CONFIRMATION", confirmation_required=True, confirmation_id=cid)
    db.add(log)
    db.flush()
    return log


def test_ai_confirm_error_reply_sets_error_status(client, db, w):
    from app.services.ai_tools_registry import AIToolRegistry
    bad, good = _register_tool("❌ Mahsulot topilmadi"), _register_tool("✅ Bajarildi")
    try:
        l1, l2 = _pending(db, w['admin'], bad, "c21-bad"), _pending(db, w['admin'], good, "c21-good")
        cl = client.login(w['admin'])
        assert cl.post('/api/ai/confirm', json={'confirmation_id': 'c21-bad'}).status_code == 200
        assert cl.post('/api/ai/confirm', json={'confirmation_id': 'c21-good'}).status_code == 200
        db.refresh(l1)
        db.refresh(l2)
        assert l1.status == "ERROR" and "Mahsulot topilmadi" in l1.error
        assert l2.status == "SUCCESS" and not l2.error
    finally:
        AIToolRegistry._tools.pop(bad.name, None)
        AIToolRegistry._tools.pop(good.name, None)


# ── 10. 1-bosqich qoldiqlari ─────────────────────────────────────────────────

def test_shift_queries_filtered_by_company(client, db, mk, w):
    """Ko'p korxonali xodimning boshqa korxonadagi ochiq smenasi joriy korxonada ko'rinmaydi / to'sqinlik qilmaydi."""
    from app.services.sale_create import SHIFT_REQUIRED, _assert_shift_if_required
    cashier = mk.user(w['ca'], role=UserRole.cashier, branch=w['a1'])
    db.add(Shift(cashier_id=cashier.id, company_id=w['cb'].id, branch_id=w['b1'].id, status="open",
                 opened_at=datetime.utcnow()))
    db.flush()
    assert client.login(cashier).get('/api/shifts/current').json() is None
    # sale_create: smena talab qilinadigan korxonada boshqa korxona smenasi hisobga olinmaydi
    w['ca'].pos_require_shift = True
    db.flush()
    with pytest.raises(HTTPException) as e:
        _assert_shift_if_required(db, cashier)
    assert e.value.status_code == 400 and e.value.detail == SHIFT_REQUIRED


def test_shift_own_company_found(client, db, mk, w):
    from app.services.sale_create import _assert_shift_if_required
    cashier = mk.user(w['ca'], role=UserRole.cashier, branch=w['a1'])
    sh = Shift(cashier_id=cashier.id, company_id=w['ca'].id, branch_id=w['a1'].id, status="open",
               opened_at=datetime.utcnow())
    db.add(sh)
    db.flush()
    r = client.login(cashier).get('/api/shifts/current')
    assert r.status_code == 200 and r.json()['id'] == sh.id
    w['ca'].pos_require_shift = True
    db.flush()
    _assert_shift_if_required(db, cashier)                              # o'z korxonasi smenasi bor — o'tadi


def test_inventory_has_no_user_branch_id_usage():
    with open(os.path.join(ROOT, 'app', 'routers', 'inventory.py'), encoding='utf-8') as f:
        src = f.read()
    assert 'current_user.branch_id' not in src


def test_expiring_batches_uses_branch_context(client, db, mk, w):
    from app.models.category import Category
    cat = Category(name="Sut", company_id=w['ca'].id, is_perishable=True)
    db.add(cat)
    db.flush()

    def _batch(wh):
        p = _product(db, w['ca'], category_id=cat.id)
        b = Batch(product_id=p.id, warehouse_id=wh.id, company_id=w['ca'].id, quantity=D(5), initial_quantity=D(5),
                  purchase_price=D(10), expiry_date=datetime.now() + timedelta(days=3))
        db.add(b)
        db.flush()
        return b
    b1, b2 = _batch(w['wh1']), _batch(w['wh2'])
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    got = {i['batch_id'] for i in client.login(mgr).get('/api/inventory/expiring-batches').json()}
    assert got == {b1.id}
    mgr.permissions = {"reports": {"all_branches": True}}
    db.flush()
    got = {i['batch_id'] for i in client.login(mgr).get('/api/inventory/expiring-batches').json()}
    assert got == {b1.id, b2.id}
    # begona korxona partiyasi hech qachon ko'rinmaydi
    assert client.login(w['admin_b']).get('/api/inventory/expiring-batches').json() == []


def test_write_off_expired_other_branch_403(client, db, mk, w):
    p = _product(db, w['ca'])
    b = Batch(product_id=p.id, warehouse_id=w['wh2'].id, company_id=w['ca'].id, quantity=D(5), initial_quantity=D(5),
              purchase_price=D(10), expiry_date=datetime.now() - timedelta(days=3))
    db.add(b)
    db.flush()
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    r = client.login(mgr).post('/api/inventory/write-off-expired', json={'batch_id': b.id})
    assert r.status_code == 403, r.text


def _bom(db, company, src_product, out_product):
    bom = BOM(product_id=out_product.id, name="Retsept", company_id=company.id, is_active=True)
    db.add(bom)
    db.flush()
    db.add(BOMItem(bom_id=bom.id, component_product_id=src_product.id, quantity_per_unit=D(1)))
    db.flush()
    return bom


def test_production_order_warehouse_branch_check(db, mk, w):
    from app.services.production_service import create_production_order
    raw, out = _product(db, w['ca']), _product(db, w['ca'])
    bom = _bom(db, w['ca'], raw, out)
    wh1b = mk.warehouse(w['ca'], w['a1'], name="Tayyor ombor A1")
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    ok = SimpleNamespace(bom_id=bom.id, planned_quantity=D(1), warehouse_id=w['wh1'].id,
                         target_warehouse_id=wh1b.id, note=None)
    order = create_production_order(db, ok, mgr.id, w['ca'].id)
    assert order.id
    bad = SimpleNamespace(bom_id=bom.id, planned_quantity=D(1), warehouse_id=w['wh2'].id,
                          target_warehouse_id=wh1b.id, note=None)
    with pytest.raises(HTTPException) as e:
        create_production_order(db, bad, mgr.id, w['ca'].id)
    assert e.value.status_code == 403
    # begona korxona ombori — 404 (oldingidek); admin istalgan filial omborini ishlata oladi
    foreign = SimpleNamespace(bom_id=bom.id, planned_quantity=D(1), warehouse_id=w['whb'].id,
                              target_warehouse_id=wh1b.id, note=None)
    with pytest.raises(HTTPException) as e:
        create_production_order(db, foreign, w['admin'].id, w['ca'].id)
    assert e.value.status_code == 404
    cross = SimpleNamespace(bom_id=bom.id, planned_quantity=D(1), warehouse_id=w['wh2'].id,
                            target_warehouse_id=wh1b.id, note=None)
    assert create_production_order(db, cross, w['admin'].id, w['ca'].id).id


def test_receive_without_warehouse_falls_back_to_branch_default(client, db, mk, w):
    p = _product(db, w['ca'])
    keeper = mk.user(w['ca'], role=UserRole.warehouse, branch=w['a2'])
    r = client.login(keeper).post('/api/inventory/receive',
                                  json={'items': [{'product_id': p.id, 'quantity': 3}]})
    assert r.status_code == 200, r.text
    sl = db.query(StockLevel).filter(StockLevel.product_id == p.id).one()
    assert sl.warehouse_id == w['wh2'].id                              # xodim filialining ombori, wh1 emas


# ── 11. Skriptlar ────────────────────────────────────────────────────────────

def test_scripts_exist_and_are_import_safe():
    import importlib.util
    for rel in ('deploy/recalc_wallet_balances.py', 'scripts/pnl_branch_audit.py'):
        path = os.path.join(ROOT, *rel.split('/'))
        assert os.path.isfile(path)
        spec = importlib.util.spec_from_file_location(f"c21_{os.path.basename(rel)[:-3]}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)                                   # import vaqtida hech narsa bajarilmaydi
        assert callable(mod.main)
    with open(os.path.join(ROOT, 'deploy', 'recalc_wallet_balances.py'), encoding='utf-8') as f:
        assert '"--apply" in sys.argv' in f.read()                      # sukut bo'yicha dry-run


def test_pnl_branch_audit_old_vs_new(db, w):
    import importlib.util
    spec = importlib.util.spec_from_file_location("c21_pnl_audit", os.path.join(ROOT, 'scripts', 'pnl_branch_audit.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from app.services.pnl_service import compute_pnl
    _expense(db, w['ca'], w['a1'], 10, currency="USD", exchange_rate=D("12700"), amount_uzs=D("127000"))
    start, end = _date_range(local_today(), local_today())
    old = mod.old_net_profit(db, w['ca'].id, start, end, w['a1'].id)
    new = compute_pnl(db, w['ca'].id, start, end, w['a1'].id)['net_profit']
    assert old == -10 and new == -127000                               # eski formula valyutani o'girmagan


def test_gitignore_allows_audit_script():
    with open(os.path.join(ROOT, '.gitignore'), encoding='utf-8') as f:
        lines = [ln.strip() for ln in f]
    assert '!scripts/pnl_branch_audit.py' in lines
    assert 'scripts/' not in lines                                     # papka ignore qilinsa `!` istisnolari ishlamaydi
