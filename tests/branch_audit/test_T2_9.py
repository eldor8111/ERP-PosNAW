"""T2.9 — AI tahlil va Copilot'da filial konteksti.

Qamrov: resolve_ai_scope (filialli foydalanuvchi / admin / begona filial), /ai/insights importi (NameError yo'q),
/ai/daily-summary scope (manager 403, admin filial va butun korxona), Copilot vositalari `branch` parametri
(get_sales_summary, get_low_stock, draft_purchase_order, get_debtors_list), noaniq filial nomi, POST
/ai/actions/purchase-order (ombor kesimida alohida PO, begona/doiradan tashqari ombor), /ai/recommendations
(NULL customer_id, o'chirilgan mahsulot), daily-insight keshi filial bo'yicha, /ai/status matni, i18n pending fayli.
LLM chaqiruvlari mock qilinadi (OpenRouter kaliti shart emas).
"""
import itertools
import json
import os
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

import app.services.ai_tools_actions  # noqa: F401 — vositalar ro'yxatdan o'tadi
import app.services.ai_tools_products  # noqa: F401
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services.ai_scope import (
    AIScope, low_stock_count, resolve_ai_scope, resolve_branch_by_name, resolve_tool_scope, scope_cache_part,
)
from app.services.ai_tools_registry import AIToolRegistry
from app.utils.report_utils import day_sales_summary, local_day_start, local_today, sales_summary

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _now():
    return local_day_start(local_today()) + timedelta(hours=1)


def _product(db, company, **kw):
    n = next(_seq)
    p = Product(name=kw.pop('name', f"Tovar {n}"), sku=f"T29-{n}", barcode=f"B29-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"), **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty):
    sl = StockLevel(product_id=product.id, warehouse_id=warehouse.id, quantity=Decimal(qty))
    db.add(sl)
    db.flush()
    return sl


def _sale(db, user, company, warehouse, amount=1000, product=None, qty=1, customer=None, created_at=None):
    n = next(_seq)
    s = Sale(number=f"ST29-{n}", cashier_id=user.id, company_id=company.id, warehouse_id=warehouse.id,
             customer_id=customer.id if customer else None, total_amount=Decimal(amount),
             paid_amount=Decimal(amount), paid_cash=Decimal(amount), paid_card=Decimal(0), exchange_rate=1,
             payment_type=PaymentType.cash, status=SaleStatus.completed, created_at=created_at or _now())
    db.add(s)
    db.flush()
    if product is not None:
        db.add(SaleItem(sale_id=s.id, product_id=product.id, quantity=Decimal(qty), unit_price=Decimal(amount),
                        cost_price=Decimal(0), subtotal=Decimal(amount), currency_code="UZS", exchange_rate=1,
                        warehouse_id=warehouse.id))
        db.flush()
    return s


@pytest.fixture
def t(mk):
    """Korxona A: ikki filial (Yunusobod, Asosiy) + omborlar, admin, filialli manager; korxona B."""
    c = mk.company()
    yun = mk.branch(c, name="Yunusobod")
    main = mk.branch(c, name="Asosiy")
    w_yun = mk.warehouse(c, yun, name="Yunusobod ombori")
    w_main = mk.warehouse(c, main, name="Asosiy ombor")
    admin = mk.user(c, role=UserRole.admin)
    mgr = mk.user(c, role=UserRole.manager, branch=yun)
    cb, bb, wb, ub = mk.tenant()
    return dict(c=c, yun=yun, main=main, w_yun=w_yun, w_main=w_main, admin=admin, mgr=mgr, cb=cb, bb=bb, wb=wb, ub=ub)


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    """LLM chaqiruvlari tarmoqqa chiqmasin."""
    import app.routers.ai_analytics as ana
    import app.routers.ai_reports as rep
    monkeypatch.setattr(ana, 'call_copilot_ai', lambda *a, **k: {"intent": "query", "reply": "AI xulosa"})
    monkeypatch.setattr(rep, 'generate_daily_insight', lambda **k: f"AI-{k['company_name']}")
    rep.cache.clear()
    yield
    rep.cache.clear()


def _tool(name, db, user, **kwargs):
    return AIToolRegistry.get_tool(name)().execute(db, user.company_id, user, **kwargs)


# ── resolve_ai_scope ─────────────────────────────────────────────────────────

def test_scope_branch_user_only_own_branch(db, t):
    sc = resolve_ai_scope(db, t['mgr'])
    assert sc.branch_id == t['yun'].id and sc.warehouse_ids == [t['w_yun'].id]
    assert "Yunusobod" in sc.label and sc.restricted


def test_scope_branch_user_other_branch_403(db, t):
    with pytest.raises(HTTPException) as e:
        resolve_ai_scope(db, t['mgr'], t['main'].id)
    assert e.value.status_code == 403
    # o'z filialini aniq so'rasa ruxsat
    assert resolve_ai_scope(db, t['mgr'], t['yun'].id).branch_id == t['yun'].id


def test_scope_foreign_branch_404(db, t):
    for u in (t['admin'], t['mgr']):
        with pytest.raises(HTTPException) as e:
            resolve_ai_scope(db, u, t['bb'].id)
        assert e.value.status_code == 404


def test_scope_admin_none_and_branch(db, t):
    assert resolve_ai_scope(db, t['admin']) is None
    sc = resolve_ai_scope(db, t['admin'], t['main'].id)
    assert sc.branch_id == t['main'].id and sc.warehouse_ids == [t['w_main'].id] and not sc.restricted


def test_resolve_branch_by_name(db, t, mk):
    c = t['c']
    b, err = resolve_branch_by_name(db, c.id, "yunusobod")
    assert b.id == t['yun'].id and err is None
    b, err = resolve_branch_by_name(db, c.id, "Yunusobod filiali")
    assert b.id == t['yun'].id
    b, err = resolve_branch_by_name(db, c.id, "Chilonzor")
    assert b is None and "Yunusobod" in err and "Asosiy" in err
    mk.branch(c, name="Yunusobod-2")
    b, err = resolve_branch_by_name(db, c.id, "Yunus")
    assert b is None and "Bir nechta" in err
    # to'liq moslik noaniqlikni yengadi
    b, err = resolve_branch_by_name(db, c.id, "Yunusobod")
    assert b.id == t['yun'].id


# ── sales_summary / day_sales_summary ────────────────────────────────────────

def test_sales_summary_warehouse_filter(db, t):
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000)
    _sale(db, t['admin'], t['c'], t['w_main'], 5000)
    today = local_today()
    assert day_sales_summary(db, t['c'].id, today)['gross'] == 6000
    assert day_sales_summary(db, t['c'].id, today, wh_ids=[t['w_yun'].id])['gross'] == 1000
    flt = AIScope(t['yun'].id, "Yunusobod", [t['w_yun'].id], "Yunusobod filiali", t['c'].id, (t['yun'].id,)).sale_filter()
    assert day_sales_summary(db, t['c'].id, today, sale_filter=flt)['gross'] == 1000
    start, end = local_day_start(today), local_day_start(today + timedelta(days=1))
    assert sales_summary(db, t['c'].id, start, end, wh_ids=[t['w_main'].id])['count'] == 1


# ── /ai/insights, /ai/status ────────────────────────────────────────────────

def test_insights_endpoint_ok(client, db, t):
    r = client.login(t['admin']).get('/api/ai/insights')
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data['insights']) == 3
    assert data['scope']['label'] == "Butun korxona"
    assert "Yuklashda xatolik" not in json.dumps(data, ensure_ascii=False)


def test_insights_branch_scope(client, db, t):
    r = client.login(t['admin']).get('/api/ai/insights', params={'branch_id': t['yun'].id})
    assert r.status_code == 200
    assert r.json()['scope'] == {'branch_id': t['yun'].id, 'label': 'Yunusobod filiali'}
    assert 'Yunusobod filiali' in r.json()['insights'][0]['body']


def test_ai_status_time_text(client, t):
    r = client.login(t['admin']).get('/api/ai/status')
    feats = " ".join(r.json()['features'])
    assert "17:30" not in feats and "20:00" in feats


# ── /ai/daily-summary ────────────────────────────────────────────────────────

def test_daily_summary_manager_only_own_branch(client, db, t):
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000)
    _sale(db, t['admin'], t['c'], t['w_main'], 5000)
    r = client.login(t['mgr']).get('/api/ai/daily-summary')
    assert r.status_code == 200, r.text
    assert r.json()['stats']['total_sales'] == 1000
    assert r.json()['scope']['label'] == 'Yunusobod filiali'
    r = client.login(t['mgr']).get('/api/ai/daily-summary', params={'branch_id': t['main'].id})
    assert r.status_code == 403
    r = client.login(t['mgr']).get('/api/ai/daily-summary', params={'branch_id': t['bb'].id})
    assert r.status_code == 404


def test_daily_summary_admin_branch_and_all(client, db, t):
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000)
    _sale(db, t['admin'], t['c'], t['w_main'], 5000)
    r = client.login(t['admin']).get('/api/ai/daily-summary', params={'branch_id': t['main'].id})
    assert r.json()['stats']['total_sales'] == 5000 and r.json()['scope']['label'] == 'Asosiy filiali'
    r = client.login(t['admin']).get('/api/ai/daily-summary')
    assert r.json()['stats']['total_sales'] == 6000 and r.json()['scope'] == {'branch_id': None, 'label': 'Butun korxona'}


def test_daily_summary_company_isolation(client, db, t):
    _sale(db, t['ub'], t['cb'], t['wb'], 7777)
    r = client.login(t['admin']).get('/api/ai/daily-summary')
    assert r.json()['stats']['total_sales'] == 0
    r = client.login(t['ub']).get('/api/ai/daily-summary', params={'branch_id': t['yun'].id})
    assert r.status_code == 404


def test_weekly_chart_and_other_endpoints_scope(client, db, t):
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000)
    _sale(db, t['admin'], t['c'], t['w_main'], 5000)
    r = client.login(t['mgr']).get('/api/ai/weekly-chart')
    assert r.status_code == 200
    assert sum(d['amount'] for d in r.json()['chart']) == 1000
    r = client.login(t['mgr']).get('/api/ai/weekly-chart', params={'branch_id': t['main'].id})
    assert r.status_code == 403
    r = client.login(t['admin']).get('/api/ai/debt-analytics', params={'branch_id': t['yun'].id})
    assert r.status_code == 200 and r.json()['scope']['label'] == 'Butun korxona'
    r = client.login(t['mgr']).get('/api/ai/debt-analytics', params={'branch_id': t['main'].id})
    assert r.status_code == 403
    r = client.login(t['admin']).get('/api/ai/daily-report', params={'branch_id': t['yun'].id})
    assert r.status_code == 200
    assert 'Hudud: Yunusobod filiali' in r.json()['report'] and 'holatiga' in r.json()['report']
    r = client.login(t['admin']).get('/api/ai/daily-report')
    assert 'Hudud: Butun korxona' in r.json()['report']


# ── Copilot vositalari ───────────────────────────────────────────────────────

def test_tool_sales_summary_branch_label(db, t):
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000)
    _sale(db, t['admin'], t['c'], t['w_main'], 45000)
    r = _tool('get_sales_summary', db, t['admin'], period='today', branch='Yunusobod')
    assert 'Yunusobod filiali' in r['reply'] and '1 000' in r['reply'] and '46 000' not in r['reply']
    r = _tool('get_sales_summary', db, t['admin'], period='today')
    assert 'Butun korxona' in r['reply'] and '46 000' in r['reply']


def test_tool_unknown_or_ambiguous_branch_clarifies(db, t, mk):
    r = _tool('get_sales_summary', db, t['admin'], branch='Chilonzor')
    assert 'topilmadi' in r['reply'] and 'Yunusobod' in r['reply']
    mk.branch(t['c'], name="Yunusobod-2")
    r = _tool('get_sales_summary', db, t['admin'], branch='Yunus')
    assert 'Bir nechta' in r['reply']


def test_tool_branch_user_param_ignored(db, t):
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000)
    _sale(db, t['admin'], t['c'], t['w_main'], 5000)
    r = _tool('get_sales_summary', db, t['mgr'], branch='Asosiy')
    assert 'Yunusobod filiali' in r['reply'] and 'ruxsatingizdan tashqarida' in r['reply']
    assert '5 000' not in r['reply'] and '6 000' not in r['reply']
    r = _tool('get_sales_summary', db, t['mgr'])
    assert 'Yunusobod filiali' in r['reply'] and '1 000' in r['reply']


def test_tool_scope_helper_branch_id_kwarg(db, t):
    sc, note, err = resolve_tool_scope(db, t['admin'], {'branch_id': t['main'].id})
    assert sc.branch_id == t['main'].id and err is None
    sc, note, err = resolve_tool_scope(db, t['admin'], {'branch_id': t['bb'].id})
    assert sc is None and err is not None  # begona filial - aniqlashtiruvchi javob


def test_tool_low_stock_branch_scope(db, t):
    p = _product(db, t['c'], name="Cola", min_stock=10)
    _stock(db, p, t['w_main'], 200)
    _stock(db, p, t['w_yun'], 0)
    deleted = _product(db, t['c'], name="Eski tovar", is_deleted=True, min_stock=10)
    _stock(db, deleted, t['w_yun'], 0)
    r = _tool('get_low_stock', db, t['admin'], branch='Yunusobod')
    assert 'Cola' in r['reply'] and 'Yunusobod filiali' in r['reply'] and 'Eski tovar' not in r['reply']
    r = _tool('get_low_stock', db, t['admin'])
    assert 'Cola' not in r['reply'] and 'Butun korxona' in r['reply']  # jami 200 - yetarli
    r = _tool('get_low_stock', db, t['admin'], branch='Asosiy')
    assert 'Cola' not in r['reply']
    # filialli manager o'z filialini ko'radi
    assert 'Cola' in _tool('get_low_stock', db, t['mgr'])['reply']


def test_low_stock_count_counts_products_not_rows(db, t):
    p = _product(db, t['c'])
    _stock(db, p, t['w_yun'], 1)
    _stock(db, p, t['w_main'], 2)
    assert low_stock_count(db, t['c'].id, None) == 1      # ikki qator, bitta mahsulot (jami 3 < 10)
    p2 = _product(db, t['c'], min_stock=50)
    _stock(db, p2, t['w_main'], 30)                       # min_stock=50 dan kam
    assert low_stock_count(db, t['c'].id, None) == 2
    assert low_stock_count(db, t['c'].id, resolve_ai_scope(db, t['admin'], t['yun'].id)) == 1


def test_tool_top_products_and_profit_scope(db, t):
    p = _product(db, t['c'], name="Fanta")
    q = _product(db, t['c'], name="Pepsi")
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000, product=p)
    _sale(db, t['admin'], t['c'], t['w_main'], 5000, product=q)
    r = _tool('get_top_products', db, t['admin'], branch='Yunusobod')
    assert 'Fanta' in r['reply'] and 'Pepsi' not in r['reply'] and 'Yunusobod filiali' in r['reply']
    r = _tool('get_profit_today', db, t['admin'], branch='Asosiy')
    assert 'Asosiy filiali' in r['reply'] and '5 000' in r['reply']
    r = _tool('get_profit_today', db, t['mgr'])
    assert 'Yunusobod filiali' in r['reply'] and '1 000' in r['reply']


def test_tool_debtors_labelled_whole_company(db, t):
    db.add(Customer(name="Qarzdor", company_id=t['c'].id, debt_balance=Decimal("5000"), debt_balances={"UZS": 5000}))
    db.flush()
    r = _tool('get_debtors_list', db, t['admin'], branch='Yunusobod')
    assert 'Butun korxona qarzi' in r['reply'] and 'Qarzdor' in r['reply']


def test_tool_predict_depletion_scope(db, t):
    p = _product(db, t['c'], name="Suv")
    _stock(db, p, t['w_main'], 500)
    _stock(db, p, t['w_yun'], 1)
    for _ in range(14):
        _sale(db, t['admin'], t['c'], t['w_yun'], 1000, product=p, qty=1)
    r = _tool('predict_stock_depletion', db, t['admin'], branch='Yunusobod', days_ahead=7)
    assert isinstance(r['reply'], dict) and r['reply']['scope'] == 'Yunusobod filiali'
    assert [x['name'] for x in r['reply']['depletion_prediction']] == ['Suv']
    r = _tool('predict_stock_depletion', db, t['admin'], days_ahead=7)   # jami 501 - tugamaydi
    assert isinstance(r['reply'], str) and 'Butun korxona' in r['reply']


def test_tool_schemas_have_branch_param():
    for name in ('get_sales_summary', 'get_top_products', 'get_low_stock', 'get_profit_today',
                 'get_debtors_list', 'predict_stock_depletion', 'draft_purchase_order'):
        props = AIToolRegistry.get_tool(name).parameters['properties']
        assert props['branch']['type'] == 'string', name


# ── draft_purchase_order: ombor kesimida ─────────────────────────────────────

def test_draft_po_per_warehouse(db, t):
    p = _product(db, t['c'], name="Sut")
    _stock(db, p, t['w_main'], 200)
    _stock(db, p, t['w_yun'], 0)
    for _ in range(14):                       # ikki omborda ham kuniga 1 dona
        _sale(db, t['admin'], t['c'], t['w_yun'], 1000, product=p, qty=1)
        _sale(db, t['admin'], t['c'], t['w_main'], 1000, product=p, qty=1)
    r = _tool('draft_purchase_order', db, t['admin'])
    items = r['action']['items']
    assert [(i['warehouse_id'], i['warehouse_name']) for i in items] == [(t['w_yun'].id, "Yunusobod ombori")]
    assert items[0]['product_id'] == p.id and items[0]['current_stock'] == 0
    assert r['action']['scope'] == 'Butun korxona'
    # filial bo'yicha: Yunusobod - qoralama bor, Asosiy - zaxira yetarli
    r = _tool('draft_purchase_order', db, t['admin'], branch='Yunusobod')
    assert len(r['action']['items']) == 1 and 'Yunusobod filiali' in r['reply']
    r = _tool('draft_purchase_order', db, t['admin'], branch='Asosiy')
    assert 'action' not in r and 'yetarli' in r['reply']
    # filialli manager faqat o'z ombori
    r = _tool('draft_purchase_order', db, t['mgr'])
    assert {i['warehouse_id'] for i in r['action']['items']} == {t['w_yun'].id}


def test_draft_po_two_warehouses_two_items(db, t):
    p = _product(db, t['c'], name="Non")
    _stock(db, p, t['w_main'], 0)
    _stock(db, p, t['w_yun'], 0)
    for _ in range(14):
        _sale(db, t['admin'], t['c'], t['w_yun'], 1000, product=p, qty=1)
        _sale(db, t['admin'], t['c'], t['w_main'], 1000, product=p, qty=1)
    items = _tool('draft_purchase_order', db, t['admin'])['action']['items']
    assert {i['warehouse_id'] for i in items} == {t['w_yun'].id, t['w_main'].id} and len(items) == 2


# ── POST /ai/actions/purchase-order ──────────────────────────────────────────

def _supplier(db, company):
    s = Supplier(name=f"Yetkazuvchi {next(_seq)}", company_id=company.id)
    db.add(s)
    db.flush()
    return s


def test_confirm_po_two_warehouses_two_pos(client, db, t):
    p = _product(db, t['c'])
    sup = _supplier(db, t['c'])
    body = {
        "warehouse_id": t['w_yun'].id,
        "items": [
            {"product_id": p.id, "quantity": 10, "unit_cost": 500, "supplier_id": sup.id, "warehouse_id": t['w_yun'].id},
            {"product_id": p.id, "quantity": 5, "unit_cost": 500, "supplier_id": sup.id, "warehouse_id": t['w_main'].id},
        ],
    }
    r = client.login(t['admin']).post('/api/ai/actions/purchase-order', json=body)
    assert r.status_code == 200, r.text
    assert len(r.json()['purchase_order_ids']) == 2
    from app.models.purchase_order import PurchaseOrder
    whs = {po.warehouse_id for po in db.query(PurchaseOrder).filter(PurchaseOrder.id.in_(r.json()['purchase_order_ids']))}
    assert whs == {t['w_yun'].id, t['w_main'].id}


def test_confirm_po_legacy_single_warehouse(client, db, t):
    p = _product(db, t['c'])
    sup = _supplier(db, t['c'])
    body = {"warehouse_id": t['w_main'].id,
            "items": [{"product_id": p.id, "quantity": 10, "unit_cost": 500, "supplier_id": sup.id}]}
    r = client.login(t['admin']).post('/api/ai/actions/purchase-order', json=body)
    assert r.status_code == 200, r.text
    assert len(r.json()['purchase_order_ids']) == 1


def test_confirm_po_foreign_or_out_of_scope_warehouse(client, db, t):
    p = _product(db, t['c'])
    sup = _supplier(db, t['c'])
    item = {"product_id": p.id, "quantity": 10, "unit_cost": 500, "supplier_id": sup.id}
    # begona korxona ombori - 404
    r = client.login(t['admin']).post('/api/ai/actions/purchase-order', json={
        "warehouse_id": t['wb'].id, "items": [item]})
    assert r.status_code == 404
    r = client.login(t['admin']).post('/api/ai/actions/purchase-order', json={
        "warehouse_id": t['w_yun'].id, "items": [{**item, "warehouse_id": t['wb'].id}]})
    assert r.status_code == 404
    # filialli manager boshqa filial ombori - 403
    r = client.login(t['mgr']).post('/api/ai/actions/purchase-order', json={
        "warehouse_id": t['w_yun'].id, "items": [{**item, "warehouse_id": t['w_main'].id}]})
    assert r.status_code == 403
    # manager o'z ombori - ishlaydi
    r = client.login(t['mgr']).post('/api/ai/actions/purchase-order', json={
        "warehouse_id": t['w_yun'].id, "items": [item]})
    assert r.status_code == 200, r.text


# ── /ai/recommendations ──────────────────────────────────────────────────────

def test_recommendations_null_customer_and_deleted_products(client, db, t):
    for i in range(3):
        db.add(Customer(name=f"Mijoz {i}", company_id=t['c'].id))
    db.flush()
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000, customer=None)      # mijozsiz chek (customer_id NULL)
    p = _product(db, t['c'], name="Tirik", min_stock=10)
    _stock(db, p, t['w_yun'], 1)
    dead = _product(db, t['c'], name="O'chirilgan", is_deleted=True, min_stock=10)
    _stock(db, dead, t['w_yun'], 1)
    r = client.login(t['admin']).get('/api/ai/recommendations')
    assert r.status_code == 200, r.text
    recs = {x['type']: x for x in r.json()['recommendations']}
    assert 'inactive_customers' in recs and '3 ta mijoz' in recs['inactive_customers']['description']
    assert '1 ta mahsulot' in recs['low_stock']['description']        # o'chirilgani sanalmaydi
    assert r.json()['scope']['label'] == 'Butun korxona'


def test_recommendations_branch_stock_and_debtors(client, db, t):
    p = _product(db, t['c'], min_stock=10)
    _stock(db, p, t['w_main'], 200)
    _stock(db, p, t['w_yun'], 0)
    db.add(Customer(name="Q", company_id=t['c'].id, debt_balance=Decimal("0"), debt_balances={"USD": 10}))
    db.flush()
    r = client.login(t['admin']).get('/api/ai/recommendations', params={'branch_id': t['yun'].id})
    recs = {x['type']: x for x in r.json()['recommendations']}
    assert 'low_stock' in recs and 'Yunusobod filiali' in recs['low_stock']['description']
    assert 'debtors' in recs and 'Butun korxona' in recs['debtors']['description']   # ko'p valyutali qarz ham sanaladi
    r = client.login(t['admin']).get('/api/ai/recommendations')
    assert 'low_stock' not in {x['type'] for x in r.json()['recommendations']}
    r = client.login(t['mgr']).get('/api/ai/recommendations', params={'branch_id': t['main'].id})
    assert r.status_code == 403


# ── daily-insight keshi ──────────────────────────────────────────────────────

def test_daily_insight_cache_per_branch(client, db, t):
    c = client.login(t['admin'])
    r1 = c.get('/api/ai/reports/daily-insight', params={'branch_id': t['yun'].id}).json()
    assert r1['cached'] is False and 'Yunusobod filiali' in r1['report']
    r2 = c.get('/api/ai/reports/daily-insight', params={'branch_id': t['main'].id}).json()
    assert r2['cached'] is False and 'Asosiy filiali' in r2['report']          # A filial keshi B ga qaytmaydi
    assert c.get('/api/ai/reports/daily-insight', params={'branch_id': t['yun'].id}).json()['cached'] is True
    r3 = c.get('/api/ai/reports/daily-insight').json()
    assert r3['cached'] is False and r3['scope']['label'] == 'Butun korxona'
    assert c.get('/api/ai/reports/daily-insight').json()['cached'] is True
    assert client.login(t['mgr']).get('/api/ai/reports/daily-insight', params={'branch_id': t['main'].id}).status_code == 403


def test_scope_cache_part():
    assert scope_cache_part(None) == 'all'
    assert scope_cache_part(AIScope(5, "X", [], "X filiali", 1, (5,))) == '5'
    assert scope_cache_part(AIScope(None, None, [], "Filiallar", 1, (3, 2))) == 'b2-3'


# ── Copilot chat ─────────────────────────────────────────────────────────────

def test_chat_branch_id_injected_and_label(client, db, t, monkeypatch):
    import app.routers.ai_analytics as ana
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000)
    _sale(db, t['admin'], t['c'], t['w_main'], 45000)
    captured = {}

    def fake(message, context, api_key, user=None, conversation_history=None):
        captured['context'] = context
        return {"intent": "execute_tool", "tool_name": "get_sales_summary", "tool_arguments": {"period": "today"}}

    monkeypatch.setattr(ana, 'call_copilot_ai', fake)
    r = client.login(t['admin']).post('/api/ai/chat', json={"message": "bugun qancha savdo?", "branch_id": t['yun'].id})
    assert r.status_code == 200, r.text
    assert 'Yunusobod filiali' in r.json()['reply'] and '46 000' not in r.json()['reply']
    assert 'Hudud: Yunusobod filiali' in captured['context']
    # branch_id yo'q - butun korxona, kontekstda filiallar ro'yxati
    r = client.login(t['admin']).post('/api/ai/chat', json={"message": "bugun qancha savdo?"})
    assert 'Butun korxona' in r.json()['reply'] and '46 000' in r.json()['reply']
    assert 'Hudud: Butun korxona' in captured['context'] and 'Filiallar: Yunusobod, Asosiy' in captured['context']


def test_chat_llm_branch_name_and_errors(client, db, t, monkeypatch):
    import app.routers.ai_analytics as ana
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000)
    _sale(db, t['admin'], t['c'], t['w_main'], 45000)
    monkeypatch.setattr(ana, 'call_copilot_ai', lambda *a, **k: {
        "intent": "execute_tool", "tool_name": "get_sales_summary",
        "tool_arguments": {"period": "today", "branch": "Yunusobod"}})
    r = client.login(t['admin']).post('/api/ai/chat', json={"message": "Yunusobod filialida bugun qancha savdo?"})
    assert 'Yunusobod filiali' in r.json()['reply'] and '1 000' in r.json()['reply']
    # begona filial - 404, boshqa filial (filialli manager) - 403
    assert client.login(t['admin']).post('/api/ai/chat', json={"message": "x", "branch_id": t['bb'].id}).status_code == 404
    assert client.login(t['mgr']).post('/api/ai/chat', json={"message": "x", "branch_id": t['main'].id}).status_code == 403


def test_chat_manager_context_is_own_branch(client, db, t, monkeypatch):
    import app.routers.ai_analytics as ana
    _sale(db, t['admin'], t['c'], t['w_yun'], 1000)
    _sale(db, t['admin'], t['c'], t['w_main'], 45000)
    captured = {}
    monkeypatch.setattr(ana, 'call_copilot_ai', lambda m, ctx, k, **kw: captured.setdefault('ctx', ctx) and {"intent": "query", "reply": "ok"})
    r = client.login(t['mgr']).post('/api/ai/copilot/chat', json={"message": "salom"})
    assert r.status_code == 200
    assert 'Hudud: Yunusobod filiali' in captured['ctx'] and '46 000' not in captured['ctx']
    assert '45 000' not in captured['ctx'] and 'Filiallar:' not in captured['ctx']


# ── Statik tekshiruvlar ──────────────────────────────────────────────────────

def test_system_prompt_mentions_branch_param():
    src = open(os.path.join(ROOT, 'app', 'services', 'openrouter_copilot_service.py'), encoding='utf-8').read()
    assert '`branch` parametrini' in src and "Butun korxona" in src


KEYS_T2_9 = ["aiCopilot.scopeAll", "aiCopilot.scopeBadge", "aiCopilot.scopeSelect", "aiCopilot.debtAllCompany", "aiCopilot.poWarehouse"]


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


def test_i18n_pending_file_consistent():
    data = _merged_i18n(KEYS_T2_9)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    jsx = open(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', 'AICopilot.jsx'), encoding='utf-8').read()
    for key in data['uz']:
        assert key in jsx, key
    assert 'branch_id' in jsx and 'warehouse_id' in jsx
