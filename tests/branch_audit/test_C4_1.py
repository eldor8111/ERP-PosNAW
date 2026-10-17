"""C4.1 — 3–4-bosqich backend qoldiqlari.

Qamrov (band bo'yicha):
 1. (T3.10) pos-list `skip` bilan sahifalaydi.
 2. (T3.18/T4.2) Z-report: HIPPO_SERVER_ENABLED o'chiq bo'lsa chaqirilmaydi; yoqiq bo'lsa chaqiriladi;
    qurilma smena filialiga ruxsat etilmagan bo'lsa chaqirilmaydi (ikkala yopish yo'lida).
 3. (T3.18) post_sale_payments SalePayment ga reference/terminal_id ni to'g'ridan-to'g'ri yozadi.
 4. (T4.2) Company.fiscal_default_vat + migratsiya; _vat_percent NULL turdagi mahsulot uchun shu qiymatni ishlatadi.
 5. (T4.3) companies: promotions_auto_apply (Out + PUT; null e'tiborsiz; begona korxona 404).
 6. (T4.3) SaleItemOut promotion_id / promotion_discount ni qaytaradi.
 7. (T4.4) stock_report kam qoldiq = stock_utils; inventory_rows.is_low ombor sozlamasini hisobga oladi.
 8. (T4.6) X-Approval-Id sarlavhasi (sotuv, qaytarish, qisman qaytarish, o'chirish) approval_id ga o'tadi.
 9. CORS expose_headers X-Total-Count; pos-list `_price` bir marta hisoblanadi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_C4_1.py -q -p no:cacheprovider
"""
import itertools
import os
import py_compile
import re
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.main import app
from app.models.fiscal_device import FiscalDevice
from app.models.inventory import StockLevel
from app.models.moliya import KassaSession, Wallet
from app.models.product import Product
from app.models.sale import Sale, SalePayment
from app.models.shift import Shift
from app.models.user import UserRole
from app.models.warehouse_stock_setting import WarehouseStockSetting
from app.routers import sales as sales_router
from app.routers import shifts as shifts_router
from app.services import hippo_fiscalize, stock_report
from app.services.sale_cash import build_sale_payment_entries
from app.utils import stock_utils

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
D = Decimal


def _src(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _product(db, company, price="1000", min_stock=0, **kw):
    n = next(_seq)
    p = Product(name=f"Tovar {n:03d}", sku=f"C41-{n}", barcode=f"BC41-{n}", company_id=company.id,
                cost_price=D("500"), sale_price=D(price), min_stock=min_stock, **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty=100):
    sl = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=D(qty))
    db.add(sl)
    db.flush()
    return sl


def _wallet(db, company, branch):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=D("0"),
               company_id=company.id, branch_id=branch.id if branch else None, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(sales_router, 'notify_new_sale', _noop)


@pytest.fixture
def w(db, mk):
    """A korxona: a1 (wh1), a2; admin, a1 kassiri. B korxona: admin."""
    ca, a1, wh1, admin = mk.tenant(UserRole.admin)
    a2 = mk.branch(ca, "Filial A-2")
    cash1 = mk.user(ca, role=UserRole.cashier, branch=a1)
    _wallet(db, ca, a1)
    p = _product(db, ca)
    _stock(db, p, wh1)
    cb, b1, whb, admin_b = mk.tenant(UserRole.admin)
    return dict(ca=ca, a1=a1, a2=a2, wh1=wh1, admin=admin, cash1=cash1, p=p,
                cb=cb, b1=b1, whb=whb, admin_b=admin_b)


def _sale_body(w, payments, price=1000):
    total = sum(x['amount'] for x in payments)
    return {'items': [{'product_id': w['p'].id, 'quantity': 1, 'unit_price': price}],
            'payment_type': payments[0]['type'], 'paid_amount': total, 'payments': payments,
            'warehouse_id': w['wh1'].id}


# ── 1. pos-list skip (T3.10) + 9. _price bir marta ───────────────────────────

def test_pos_list_skip_paginates_without_overlap(client, db, w):
    for i in range(4):
        p = _product(db, w['ca'])
        _stock(db, p, w['wh1'])
    cl = client.login(w['admin'])
    full = [x['id'] for x in cl.get('/api/products/pos-list?limit=50').json()]
    assert len(full) == 5
    page1 = [x['id'] for x in cl.get('/api/products/pos-list?limit=2&skip=0').json()]
    page2 = [x['id'] for x in cl.get('/api/products/pos-list?limit=2&skip=2').json()]
    page3 = [x['id'] for x in cl.get('/api/products/pos-list?limit=2&skip=4').json()]
    assert page1 + page2 + page3 == full
    assert cl.get('/api/products/pos-list?skip=-1').status_code == 422


def test_pos_list_isolation_and_price_computed_once(client, db, w):
    # begona korxona mahsuloti A foydalanuvchisiga ko'rinmaydi
    pb = _product(db, w['cb'], price="777")
    _stock(db, pb, w['whb'])
    rows = client.login(w['admin']).get('/api/products/pos-list?limit=50').json()
    assert pb.id not in {r['id'] for r in rows} and w['p'].id in {r['id'] for r in rows}
    assert rows[0]['sale_price'] == 1000.0 and rows[0]['price_source'] == 'product'
    src = _src('app/routers/product_search.py')
    assert '_price(p)[' not in src and 'prices = {p.id: _price(p)' in src


# ── 2. Z-report (T3.18 / T4.2) ───────────────────────────────────────────────

def _open_shift(db, user, branch):
    sh = Shift(cashier_id=user.id, company_id=user.company_id, branch_id=branch.id, status="open",
               opened_at=datetime.utcnow())
    db.add(sh)
    db.flush()
    return sh


def _device(db, company, factory_id, branch=None):
    d = FiscalDevice(company_id=company.id, branch_id=branch.id if branch else None,
                     factory_id=factory_id, label=factory_id, is_active=True)
    db.add(d)
    db.flush()
    return d


@pytest.fixture
def z_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(shifts_router, '_hippo_z_close', lambda fid: calls.append(fid))
    return calls


def test_z_close_not_called_when_flag_off(client, db, w, z_calls, monkeypatch):
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', False)
    _open_shift(db, w['cash1'], w['a1'])
    r = client.login(w['cash1']).post('/api/shifts/close', json={}, headers={'X-Hippo-Factory-Id': 'FM-1'})
    assert r.status_code == 200, r.text
    assert z_calls == []


def test_z_close_called_when_flag_on_both_paths(client, db, w, z_calls, monkeypatch):
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', True)
    _open_shift(db, w['cash1'], w['a1'])
    r = client.login(w['cash1']).post('/api/shifts/close', json={}, headers={'X-Hippo-Factory-Id': 'FM-1'})
    assert r.status_code == 200, r.text
    assert z_calls == ['FM-1']
    # POST /shifts/{id}/close yo'li (admin boshqa kassirning smenasini yopadi)
    sh = _open_shift(db, w['admin'], w['a1'])
    r = client.login(w['admin']).post(f'/api/shifts/{sh.id}/close', json={}, headers={'X-Hippo-Factory-Id': 'FM-2'})
    assert r.status_code == 200, r.text
    assert z_calls == ['FM-1', 'FM-2']


def test_z_close_skipped_for_foreign_branch_device(client, db, w, z_calls, monkeypatch, caplog):
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', True)
    _device(db, w['ca'], 'FM-A2', branch=w['a2'])      # qurilma faqat a2 filialiga ruxsat etilgan
    _open_shift(db, w['cash1'], w['a1'])
    with caplog.at_level('WARNING', logger='hippo.shift'):
        r = client.login(w['cash1']).post('/api/shifts/close', json={}, headers={'X-Hippo-Factory-Id': 'FM-A2'})
    assert r.status_code == 200, r.text                  # smena baribir yopiladi
    assert z_calls == []
    assert any('o\'tkazib yuborildi' in m for m in caplog.messages)


def test_z_close_allowed_for_own_branch_device_and_empty_registry(client, db, w, z_calls, monkeypatch):
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', True)
    _device(db, w['ca'], 'FM-A1', branch=w['a1'])
    _open_shift(db, w['cash1'], w['a1'])
    assert client.login(w['cash1']).post('/api/shifts/close', json={}, headers={'X-Hippo-Factory-Id': 'FM-A1'}).status_code == 200
    assert z_calls == ['FM-A1']
    # B korxonada registr bo'sh -> tekshiruv yo'q (eski xatti-harakat)
    cb_cashier = client.login(w['admin_b'])
    _open_shift(db, w['admin_b'], w['b1'])
    assert cb_cashier.post('/api/shifts/close', json={}, headers={'X-Hippo-Factory-Id': 'FM-B'}).status_code == 200
    assert z_calls == ['FM-A1', 'FM-B']


# ── 3. SalePayment reference / terminal_id (T3.18) ───────────────────────────

def test_build_entries_carry_reference_and_terminal():
    pay = SimpleNamespace(type=SimpleNamespace(value='click'), amount=D('1000'), rate=D('1'), currency='UZS',
                          reference='  TX-77 ', terminal_id=5)
    plain = SimpleNamespace(type=SimpleNamespace(value='cash'), amount=D('500'), rate=D('1'), currency='UZS',
                            reference=None, terminal_id=None)
    data = SimpleNamespace(payments=[pay, plain], paid_amount=D('1500'), payment_type=None)
    e = build_sale_payment_entries(data)
    assert e[0]['reference'] == 'TX-77' and e[0]['terminal_id'] == 5
    assert e[1]['reference'] is None and e[1]['terminal_id'] is None


def test_sale_payment_gets_reference_without_attach(client, db, w, monkeypatch):
    """attach_payment_references (summa bo'yicha moslash) o'chirilsa ham reference yoziladi."""
    monkeypatch.setattr(sales_router, 'attach_payment_references', lambda *a, **k: None)
    body = _sale_body(w, [{'type': 'click', 'amount': 600, 'reference': 'CLK-1'},
                          {'type': 'click', 'amount': 400, 'reference': 'CLK-2'}])
    r = client.login(w['admin']).post('/api/sales/', json=body, headers={'Idempotency-Key': 'c41-ref'})
    assert r.status_code == 200, r.text
    rows = db.query(SalePayment).filter(SalePayment.sale_id == r.json()['id']).order_by(SalePayment.id).all()
    assert [(x.amount, x.reference) for x in rows] == [(D('600'), 'CLK-1'), (D('400'), 'CLK-2')]


# ── 4. fiscal_default_vat (T4.2) ─────────────────────────────────────────────

def test_vat_percent_uses_company_default_for_null_type():
    from app.models.mxik import VatRateType
    null_p = SimpleNamespace(id=1, name='x', vat_rate_type=None)
    assert hippo_fiscalize._vat_percent(null_p) == 12
    assert hippo_fiscalize._vat_percent(null_p, None) == 12
    assert hippo_fiscalize._vat_percent(null_p, 0) == 0
    assert hippo_fiscalize._vat_percent(null_p, 7) == 7
    # belgilangan tur korxona standartidan ustun
    zero_p = SimpleNamespace(id=2, name='y', vat_rate_type=VatRateType.zero)
    assert hippo_fiscalize._vat_percent(zero_p, 7) == 0


def test_receipt_payload_uses_company_fiscal_default_vat(client, db, w):
    r = client.login(w['admin']).post('/api/sales/', json=_sale_body(w, [{'type': 'cash', 'amount': 1000}]),
                                      headers={'Idempotency-Key': 'c41-vat'})
    assert r.status_code == 200, r.text
    sale = db.get(Sale, r.json()['id'])
    assert hippo_fiscalize._build_receipt_payload(sale, 'F1')['receipt']['items'][0]['vat_percent'] == 12
    w['ca'].fiscal_default_vat = 0
    db.flush()
    assert hippo_fiscalize._build_receipt_payload(sale, 'F1')['receipt']['items'][0]['vat_percent'] == 0


def test_fiscal_default_vat_column_and_migration():
    from app.models.company import Company
    col = Company.__table__.c.fiscal_default_vat
    assert col.nullable is True
    mig = 'alembic/versions/c4_1_company_fiscal_default_vat.py'
    py_compile.compile(os.path.join(ROOT, mig), doraise=True)
    s = _src(mig)
    assert "revision: str = 'c4_1'" in s and 'down_revision' in s and 'None' in s.split('down_revision')[1].split('\n')[0]
    assert 'fiscal_default_vat' in s and 'ADD COLUMN IF NOT EXISTS' in s


# ── 5. companies: promotions_auto_apply / fiscal_default_vat (T4.3) ──────────

def test_company_update_promotions_auto_apply_and_vat(client, db, w):
    cl = client.login(w['admin'])
    cid = w['ca'].id
    r = cl.put(f'/api/companies/{cid}', json={'promotions_auto_apply': True, 'fiscal_default_vat': 12})
    assert r.status_code == 200, r.text
    assert r.json()['promotions_auto_apply'] is True and r.json()['fiscal_default_vat'] == 12
    db.refresh(w['ca'])
    assert w['ca'].promotions_auto_apply is True and w['ca'].fiscal_default_vat == 12
    # null -> e'tiborsiz (NOT NULL ustun buzilmaydi)
    r = cl.put(f'/api/companies/{cid}', json={'promotions_auto_apply': None})
    assert r.status_code == 200, r.text
    assert r.json()['promotions_auto_apply'] is True
    # fiscal_default_vat null -> tozalash; noto'g'ri qiymat -> 400
    assert cl.put(f'/api/companies/{cid}', json={'fiscal_default_vat': None}).json()['fiscal_default_vat'] is None
    assert cl.put(f'/api/companies/{cid}', json={'fiscal_default_vat': 101}).status_code == 400
    r = cl.put(f'/api/companies/{cid}', json={'promotions_auto_apply': False})
    assert r.json()['promotions_auto_apply'] is False


def test_company_update_foreign_company_404(client, db, w):
    r = client.login(w['admin']).put(f"/api/companies/{w['cb'].id}", json={'promotions_auto_apply': True})
    assert r.status_code == 404
    db.refresh(w['cb'])
    assert w['cb'].promotions_auto_apply is False


def test_company_list_exposes_new_fields(client, db, w):
    w['ca'].promotions_auto_apply = True
    w['ca'].fiscal_default_vat = 12
    db.flush()
    rows = client.login(w['admin']).get('/api/companies').json()
    mine = [x for x in rows if x['id'] == w['ca'].id]
    assert mine and mine[0]['promotions_auto_apply'] is True and mine[0]['fiscal_default_vat'] == 12


# ── 6. SaleItemOut aksiya maydonlari (T4.3) ──────────────────────────────────

def test_sale_item_out_returns_promotion_fields(client, db, w):
    r = client.login(w['admin']).post('/api/sales/', json=_sale_body(w, [{'type': 'cash', 'amount': 1000}]),
                                      headers={'Idempotency-Key': 'c41-promo'})
    assert r.status_code == 200, r.text
    sid = r.json()['id']
    sale = db.get(Sale, sid)
    item = sale.items[0]
    item.promotion_discount = D('50')       # promotion_id FK: aksiyasiz (NULL) qoldiramiz, faqat ulushni tekshiramiz
    db.flush()
    out = sales_router._build_sale_out(sale)
    assert out.items[0].promotion_discount == D('50') and out.items[0].promotion_id is None
    assert 'promotion_id=getattr(i, \'promotion_id\'' in _src('app/routers/sales.py')
    got = client.login(w['admin']).get(f'/api/sales/{sid}')
    assert got.status_code == 200 and 'promotion_discount' in got.json()['items'][0]


# ── 7. stock_report <-> stock_utils (T4.4) ───────────────────────────────────

def test_stock_report_low_stock_delegates_to_stock_utils(db, w):
    ca = w['ca']
    pl = _product(db, ca, min_stock=10)
    _stock(db, pl, w['wh1'], 3)                  # kam
    ok = _product(db, ca, min_stock=2)
    _stock(db, ok, w['wh1'], 50)
    assert stock_report.low_stock_count(db, ca.id, None) == stock_utils.low_stock_count(db, ca.id, None) == 1
    a = stock_report.low_stock_products(db, ca.id, None)
    b = stock_utils.low_stock_products(db, ca.id, None)
    assert a == b and a[0]['product_id'] == pl.id and a[0]['scope'] == 'product'
    for k in ('warehouses', 'shortage', 'min_stock'):
        assert k in a[0]
    ids = {r[0] for r in db.query(stock_report.low_stock_subquery(db, ca.id, None).c[0]).all()}
    assert ids == {pl.id}
    assert stock_report.low_stock_count_for_scope(db, ca.id, None) == 1
    # korxona izolyatsiyasi: B korxonada kam qoldiq yo'q
    assert stock_report.low_stock_count(db, w['cb'].id, None) == 0


def test_inventory_rows_is_low_respects_warehouse_settings(db, w):
    ca = w['ca']
    p = _product(db, ca, min_stock=0)            # mahsulot darajasida min yo'q
    _stock(db, p, w['wh1'], 4)
    db.add(WarehouseStockSetting(company_id=ca.id, warehouse_id=w['wh1'].id, product_id=p.id, min_qty=D('5')))
    db.flush()
    total, rows = stock_report.inventory_rows(db, ca.id, None)
    row = [r for r in rows if r['product'].id == p.id][0]
    assert row['is_low'] is True                 # eski formula (product.min_stock=0) False berardi
    q = _product(db, ca, min_stock=10)
    _stock(db, q, w['wh1'], 50)
    _, rows = stock_report.inventory_rows(db, ca.id, None)
    assert [r for r in rows if r['product'].id == q.id][0]['is_low'] is False
    src = _src('app/services/stock_report.py')
    assert 'stock_utils.row_stock_info' in src and '_low_stock_query' not in src
    assert 'stock_report' not in _src('app/utils/stock_utils.py').replace('stock_report.py', '')


# ── 8. X-Approval-Id (T4.6) ──────────────────────────────────────────────────

def test_approval_header_helper():
    mk_req = lambda v: SimpleNamespace(headers={} if v is None else {'X-Approval-Id': v})
    assert sales_router._approval_id_from_header(mk_req('15')) == 15
    assert sales_router._approval_id_from_header(mk_req('abc')) is None
    assert sales_router._approval_id_from_header(mk_req('')) is None
    assert sales_router._approval_id_from_header(mk_req(None)) is None
    body = SimpleNamespace(approval_id=None)
    sales_router._apply_header_approval(mk_req('7'), body)
    assert body.approval_id == 7
    sales_router._apply_header_approval(mk_req('9'), body)       # tana ustuvor
    assert body.approval_id == 7


def test_make_sale_takes_approval_from_header(client, db, w, monkeypatch):
    seen = {}
    real = sales_router.create_sale

    def spy(**kw):
        seen['approval_id'] = kw['data'].approval_id
        return real(**kw)
    monkeypatch.setattr(sales_router, 'create_sale', spy)
    body = _sale_body(w, [{'type': 'cash', 'amount': 1000}])
    r = client.login(w['admin']).post('/api/sales/', json=body, headers={'X-Approval-Id': '41', 'Idempotency-Key': 'c41-h1'})
    assert r.status_code == 200, r.text
    assert seen['approval_id'] == 41


def test_return_and_partial_return_and_delete_take_header(client, db, w, monkeypatch):
    seen = {}

    def fake_return(**kw):
        seen['ret'] = kw['data'].approval_id
        raise sales_router.HTTPException(status_code=418, detail='stop')

    def fake_partial(**kw):
        seen['partial'] = kw['data'].approval_id
        raise sales_router.HTTPException(status_code=418, detail='stop')

    def fake_delete(**kw):
        seen['delete'] = kw['approval_id']
        return None
    monkeypatch.setattr(sales_router, 'create_return_sale', fake_return)
    monkeypatch.setattr(sales_router, 'process_partial_return', fake_partial)
    monkeypatch.setattr(sales_router, 'delete_sale', fake_delete)
    cl = client.login(w['admin'])
    h = {'X-Approval-Id': '12'}
    body = _sale_body(w, [{'type': 'cash', 'amount': 1000}])
    assert cl.post('/api/sales/return', json=body, headers=h).status_code == 418
    assert cl.post('/api/sales/5/return-items', json={'items': [{'sale_item_id': 1, 'quantity': 1}]},
                   headers=h).status_code == 418
    assert cl.delete('/api/sales/5', headers=h).status_code == 200
    assert seen == {'ret': 12, 'partial': 12, 'delete': 12}
    assert cl.delete('/api/sales/5').status_code == 200 and seen['delete'] is None


def test_bulk_does_not_use_single_header_approval():
    src = _src('app/routers/sales.py')
    bulk = src.split('def make_bulk_sales')[1].split('@router.post("/pending"')[0]
    assert '_apply_header_approval' not in bulk and 'QO\'LLANMAYDI' in bulk


# ── 9. CORS expose_headers (qo'shimcha) ──────────────────────────────────────

def test_cors_exposes_total_count_header():
    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware][0]
    assert 'X-Total-Count' in cors.kwargs.get('expose_headers', [])


def test_python_files_compile():
    for rel in ('app/routers/shifts.py', 'app/routers/sales.py', 'app/routers/companies.py',
                'app/services/stock_report.py', 'app/services/sale_cash.py', 'app/services/hippo_fiscalize.py',
                'app/routers/product_search.py', 'app/models/company.py', 'app/main.py'):
        py_compile.compile(os.path.join(ROOT, rel), doraise=True)
    assert re.search(r'fiscal_default_vat\s*=\s*Column\(Integer, nullable=True\)', _src('app/models/company.py'))


# ── 10. 2-urinish: PUT /sales/{id} terminal tekshiruvi, Z-close smena korxonasi, bulk ─────────────────

def _terminal(db, company, provider, branch=None, require_reference=True):
    from app.models.payment_terminal import PaymentTerminal
    t = PaymentTerminal(company_id=company.id, branch_id=branch.id if branch else None, provider=provider,
                        label=f"{provider}-{next(_seq)}", merchant_id=f"M{next(_seq)}",
                        require_reference=require_reference, is_active=True)
    db.add(t)
    db.flush()
    return t


def _pending_sale_id(client, w):
    body = {'items': [{'product_id': w['p'].id, 'quantity': 1, 'unit_price': 1000}],
            'payment_type': 'cash', 'paid_amount': 0, 'warehouse_id': w['wh1'].id}
    r = client.login(w['admin']).post('/api/sales/pending', json=body)
    assert r.status_code == 200, r.text
    return r.json()['id']


def _finish_body(w, payment):
    return {'status': 'completed', 'items': [{'product_id': w['p'].id, 'quantity': 1, 'unit_price': 1000}],
            'payment_type': payment['type'], 'paid_amount': payment['amount'], 'payments': [payment],
            'warehouse_id': w['wh1'].id}


def test_edit_sale_foreign_company_terminal_404(client, db, w):
    """A korxona foydalanuvchisi PUT /sales/{id} da B korxona terminal_id sini yuborsa 404; SalePayment yozilmaydi."""
    foreign = _terminal(db, w['cb'], 'click', require_reference=False)
    sid = _pending_sale_id(client, w)
    r = client.login(w['admin']).put(f'/api/sales/{sid}', json=_finish_body(
        w, {'type': 'click', 'amount': 1000, 'reference': 'X-1', 'terminal_id': foreign.id}))
    assert r.status_code == 404, r.text
    assert db.query(SalePayment).filter(SalePayment.sale_id == sid).count() == 0
    # mavjud bo'lmagan id ham 500 emas, 404
    r = client.login(w['admin']).put(f'/api/sales/{sid}', json=_finish_body(
        w, {'type': 'click', 'amount': 1000, 'reference': 'X-1', 'terminal_id': 999999}))
    assert r.status_code == 404, r.text


def test_edit_sale_own_terminal_written_to_sale_payment(client, db, w):
    own = _terminal(db, w['ca'], 'click')
    sid = _pending_sale_id(client, w)
    r = client.login(w['admin']).put(f'/api/sales/{sid}', json=_finish_body(
        w, {'type': 'click', 'amount': 1000, 'reference': 'CLK-OK', 'terminal_id': own.id}))
    assert r.status_code == 200, r.text
    rows = db.query(SalePayment).filter(SalePayment.sale_id == sid).all()
    assert len(rows) == 1 and rows[0].reference == 'CLK-OK' and rows[0].terminal_id == own.id


def test_edit_sale_terminal_require_reference_enforced(client, db, w):
    own = _terminal(db, w['ca'], 'click', require_reference=True)
    sid = _pending_sale_id(client, w)
    r = client.login(w['admin']).put(f'/api/sales/{sid}', json=_finish_body(
        w, {'type': 'click', 'amount': 1000, 'terminal_id': own.id}))
    assert r.status_code == 400, r.text


def test_edit_sale_validates_before_update_sale_in_source():
    src = _src('app/routers/sales.py')
    i = src.index('def edit_sale(')
    block = src[i:src.index('@router.put("/{sale_id}/assign-customer"', i)]
    assert 'validate_sale_payment_terminals' in block
    assert block.index('validate_sale_payment_terminals') < block.index('update_sale(')


def test_z_close_device_check_uses_shift_company(db, w, monkeypatch):
    """super_admin boshqa korxona smenasini yopsa ham qurilma tekshiruvi smena korxonasi bo'yicha."""
    calls = []
    monkeypatch.setattr(shifts_router, '_hippo_z_close', lambda fid: calls.append(fid))
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', True)
    _device(db, w['ca'], 'FM-A1', branch=w['a1'])
    shift = _open_shift(db, w['cash1'], w['a2'])  # A korxona, a2 filiali
    req = SimpleNamespace(headers={'X-Hippo-Factory-Id': 'FM-A1'})
    bg = SimpleNamespace(add_task=lambda fn, *a: fn(*a))
    # B korxona admini (qurilmalar reestri bo'sh) -- eski kod ruxsat berib yuborardi
    shifts_router._schedule_hippo_z_close(bg, req, db, w['admin_b'], shift)
    assert calls == []
    shift_ok = _open_shift(db, w['admin'], w['a1'])
    shifts_router._schedule_hippo_z_close(bg, req, db, w['admin_b'], shift_ok)
    assert calls == ['FM-A1']


def test_bulk_no_longer_calls_attach_payment_references():
    src = _src('app/routers/sales.py')
    i = src.index('def bulk_sales') if 'def bulk_sales' in src else src.index('/bulk')
    block = src[i:src.index('@router.post("/pending"', i)]
    assert 'attach_payment_references(' not in block
