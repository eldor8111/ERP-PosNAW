"""T2.4 — Dashboard va mobil dashboard to'g'rilash.

Qamrov: /mobile/dashboard/summary (sof savdo, status/hujjat filtri, USD qarz, Toshkent kuni, filial filtri,
cheklangan menejer 403, begona korxona filiali 404, kassir 403), /mobile/dashboard/top-products (30 kun,
qaytarilgan miqdor ayiriladi), /dashboard/summary (deprecated log, kassa balansi valyuta/filial bo'yicha,
company_id filtri), sales_summary(wh_ids), statik tekshiruvlar (Profile.jsx, MobileDashboard.jsx, i18n).
"""
import itertools
import json
import logging
import os
from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.inventory import StockLevel
from app.models.currency import Currency
from app.models.moliya import Transaction
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole
from app.utils.report_utils import _today_range, local_day_start, local_today, sales_summary

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _now():
    """Bugungi kun ichidagi vaqt (Toshkent kuni boshlanishidan 1 soat keyin) — kun chegarasidan xavfsiz."""
    return local_day_start(local_today()) + timedelta(hours=1)


def _product(db, company, **kw):
    n = next(_seq)
    p = Product(name=kw.pop('name', f"Tovar {n}"), sku=f"T24-{n}", barcode=f"B24-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"), **kw)
    db.add(p)
    db.flush()
    return p


def _sale(db, user, company, warehouse, amount=1000, paid=None, cash=None, card=0, rate=1,
          status=SaleStatus.completed, refund=False, created_at=None, product=None, qty=1):
    n = next(_seq)
    paid = amount if paid is None else paid
    s = Sale(number=f"{'R' if refund else 'S'}T24-{n}", cashier_id=user.id, company_id=company.id,
             warehouse_id=warehouse.id if warehouse else None, total_amount=Decimal(amount),
             paid_amount=Decimal(paid), paid_cash=Decimal(paid if cash is None else cash), paid_card=Decimal(card),
             exchange_rate=rate, payment_type=PaymentType.cash,
             status=SaleStatus.refunded if refund else status, created_at=created_at or _now())
    db.add(s)
    db.flush()
    if product is not None:
        db.add(SaleItem(sale_id=s.id, product_id=product.id, quantity=Decimal(qty), unit_price=Decimal(amount),
                        cost_price=Decimal(0), subtotal=Decimal(amount), currency_code="UZS", exchange_rate=1))
        db.flush()
    return s


@pytest.fixture
def t(mk):
    """Korxona A: admin, ikki filial (A1, A2) va omborlari; korxona B."""
    c = mk.company()
    a1, a2 = mk.branch(c), mk.branch(c)
    w1, w2 = mk.warehouse(c, a1), mk.warehouse(c, a2)
    admin = mk.user(c, role=UserRole.admin)
    cb, bb, wb, ub = mk.tenant()
    return dict(c=c, a1=a1, a2=a2, w1=w1, w2=w2, admin=admin, cb=cb, bb=bb, wb=wb, ub=ub)


def _summary(client, user, **params):
    r = client.login(user).get('/api/mobile/dashboard/summary', params=params)
    return r


# ── /mobile/dashboard/summary ────────────────────────────────────────────────

def test_net_gross_returns(client, db, t):
    """50 mln sotuv va 5 mln qaytarish: today_sales=45 mln, gross=50 mln, returns=5 mln."""
    _sale(db, t['admin'], t['c'], t['w1'], amount=50_000_000)
    _sale(db, t['admin'], t['c'], t['w1'], amount=5_000_000, refund=True)
    r = _summary(client, t['admin'])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['today_sales'] == 45_000_000
    assert d['gross'] == 50_000_000
    assert d['returns'] == 5_000_000
    assert d['count'] == 1
    assert d['cash_in_register'] == 50_000_000
    assert d['currency'] == 'UZS'
    assert d['date'] == local_today().isoformat()
    assert d['branch_id'] is None


def test_cancelled_and_pending_excluded(client, db, t):
    _sale(db, t['admin'], t['c'], t['w1'], amount=1_000_000)
    _sale(db, t['admin'], t['c'], t['w1'], amount=7_000_000, status=SaleStatus.cancelled)
    _sale(db, t['admin'], t['c'], t['w1'], amount=3_000_000, status=SaleStatus.pending)
    d = _summary(client, t['admin']).json()
    assert d['today_sales'] == 1_000_000
    assert d['count'] == 1
    assert d['debt_sales'] == 0


def test_usd_debt_uses_rate(client, db, t):
    """100$ (kurs 12 700 = 1 270 000 so'm) sotuvga 50$ to'langan: qarz 635 000, naqd 635 000."""
    _sale(db, t['admin'], t['c'], t['w1'], amount=1_270_000, paid=50, cash=50, rate=12700)
    d = _summary(client, t['admin']).json()
    assert d['debt_sales'] == 635_000
    assert d['cash_in_register'] == 635_000
    assert d['today_sales'] == 1_270_000


def test_cash_excludes_card(client, db, t):
    _sale(db, t['admin'], t['c'], t['w1'], amount=1_000_000, paid=1_000_000, cash=400_000, card=600_000)
    d = _summary(client, t['admin']).json()
    assert d['cash_in_register'] == 400_000
    assert d['card'] == 600_000
    assert d['debt_sales'] == 0


def test_tashkent_day_boundary(client, db, t):
    """Toshkent 00:30 — bugun, kechagi 23:30 — kecha."""
    start = local_day_start(local_today())
    _sale(db, t['admin'], t['c'], t['w1'], amount=100, created_at=start + timedelta(minutes=30))
    _sale(db, t['admin'], t['c'], t['w1'], amount=900, created_at=start - timedelta(minutes=30))
    d = _summary(client, t['admin']).json()
    assert d['today_sales'] == 100
    assert d['count'] == 1


def test_branch_filter(client, db, t):
    _sale(db, t['admin'], t['c'], t['w1'], amount=1000)
    _sale(db, t['admin'], t['c'], t['w2'], amount=20_000)
    assert _summary(client, t['admin']).json()['today_sales'] == 21_000
    d1 = _summary(client, t['admin'], branch_id=t['a1'].id).json()
    assert d1['today_sales'] == 1000 and d1['branch_id'] == t['a1'].id
    assert _summary(client, t['admin'], branch_id=t['a2'].id).json()['today_sales'] == 20_000


def test_company_isolation(client, db, t):
    """A korxona foydalanuvchisi B korxona filialini so'rasa 404; B sotuvi A raqamiga qo'shilmaydi."""
    _sale(db, t['ub'], t['cb'], t['wb'], amount=9_999_000)
    _sale(db, t['admin'], t['c'], t['w1'], amount=1000)
    assert _summary(client, t['admin'], branch_id=t['bb'].id).status_code == 404
    assert _summary(client, t['admin']).json()['today_sales'] == 1000
    # ijobiy yo'l: B o'z filialini ko'radi
    assert _summary(client, t['ub'], branch_id=t['bb'].id).json()['today_sales'] == 9_999_000


def test_restricted_manager_other_branch_403(client, db, mk, t):
    mgr = mk.user(t['c'], role=UserRole.manager, branch=t['a1'])
    _sale(db, t['admin'], t['c'], t['w1'], amount=1000)
    _sale(db, t['admin'], t['c'], t['w2'], amount=20_000)
    assert _summary(client, mgr, branch_id=t['a2'].id).status_code == 403
    own = _summary(client, mgr, branch_id=t['a1'].id)
    assert own.status_code == 200 and own.json()['today_sales'] == 1000
    # parametrsiz — faqat o'z filiali (biriktirilgan filial avto-tanlanadi)
    assert _summary(client, mgr).json()['today_sales'] == 1000


def test_cashier_forbidden(client, db, mk, t):
    cashier = mk.user(t['c'], role=UserRole.cashier, branch=t['a1'])
    assert _summary(client, cashier).status_code == 403
    assert client.login(cashier).get('/api/mobile/dashboard/top-products').status_code == 403


# ── /mobile/dashboard/top-products ───────────────────────────────────────────

def test_top_products_period_and_returns(client, db, t):
    p1 = _product(db, t['c'], name="Birinchi")
    p2 = _product(db, t['c'], name="Ikkinchi")
    old = _now() - timedelta(days=40)
    _sale(db, t['admin'], t['c'], t['w1'], amount=5000, product=p1, qty=10)
    _sale(db, t['admin'], t['c'], t['w1'], amount=1000, product=p1, qty=4, refund=True)     # qaytarish: -4
    _sale(db, t['admin'], t['c'], t['w1'], amount=2000, product=p2, qty=7)
    _sale(db, t['admin'], t['c'], t['w1'], amount=9000, product=p2, qty=100, created_at=old)  # 30 kundan eski
    _sale(db, t['admin'], t['c'], t['w1'], amount=9000, product=p2, qty=100, status=SaleStatus.cancelled)
    rows = client.login(t['admin']).get('/api/mobile/dashboard/top-products').json()
    by = {r['name']: r for r in rows}
    assert by['Birinchi']['sold_quantity'] == 6 and by['Ikkinchi']['sold_quantity'] == 7
    assert by['Birinchi']['revenue_uzs'] == 4000
    assert [r['name'] for r in rows] == ['Ikkinchi', 'Birinchi']
    # days=90 eski sotuvni ham qamraydi
    rows90 = client.login(t['admin']).get('/api/mobile/dashboard/top-products', params={'days': 90}).json()
    assert {r['name']: r['sold_quantity'] for r in rows90}['Ikkinchi'] == 107
    # limit va tekshiruv
    assert len(client.login(t['admin']).get('/api/mobile/dashboard/top-products', params={'limit': 1}).json()) == 1
    assert client.login(t['admin']).get('/api/mobile/dashboard/top-products', params={'limit': 51}).status_code == 422
    assert client.login(t['admin']).get('/api/mobile/dashboard/top-products', params={'days': 0}).status_code == 422


def test_top_products_branch_and_company(client, db, t):
    p = _product(db, t['c'], name="Filialli")
    _sale(db, t['admin'], t['c'], t['w1'], amount=100, product=p, qty=3)
    _sale(db, t['admin'], t['c'], t['w2'], amount=100, product=p, qty=5)
    c = client.login(t['admin'])
    assert c.get('/api/mobile/dashboard/top-products', params={'branch_id': t['a1'].id}).json()[0]['sold_quantity'] == 3
    assert c.get('/api/mobile/dashboard/top-products', params={'branch_id': t['bb'].id}).status_code == 404


# ── sales_summary(wh_ids) ────────────────────────────────────────────────────

def test_sales_summary_wh_ids(db, t):
    _sale(db, t['admin'], t['c'], t['w1'], amount=1000)
    _sale(db, t['admin'], t['c'], t['w2'], amount=2000)
    start, end = _today_range()
    assert sales_summary(db, t['c'].id, start, end)['gross'] == 3000          # standart: filtr yo'q
    assert sales_summary(db, t['c'].id, start, end, wh_ids=[t['w2'].id])['gross'] == 2000
    assert sales_summary(db, t['c'].id, start, end, wh_ids=[])['gross'] == 0


# ── /dashboard/summary (deprecated) ──────────────────────────────────────────

def test_dashboard_summary_deprecated_log_and_numbers(client, db, t, caplog):
    p = _product(db, t['c'], name="Eski", min_stock=5)
    db.add(StockLevel(product_id=p.id, warehouse_id=t['w1'].id, quantity=Decimal(2)))
    db.flush()
    _sale(db, t['admin'], t['c'], t['w1'], amount=50_000, product=p, qty=2)
    _sale(db, t['admin'], t['c'], t['w1'], amount=10_000, product=p, qty=1, refund=True)
    _sale(db, t['admin'], t['c'], t['w1'], amount=99_000, status=SaleStatus.pending)
    with caplog.at_level(logging.WARNING):
        r = client.login(t['admin']).get('/api/dashboard/summary')
    assert r.status_code == 200, r.text
    assert any('deprecated /dashboard/summary' in m for m in caplog.messages)
    d = r.json()
    assert d['sales']['revenue'] == 40_000 and d['sales']['count'] == 1
    assert d['top_products'] == [{'name': 'Eski', 'qty': 1.0}]
    assert d['low_stock_count'] == 1
    assert d['cash_balance_scope'] == 'company'
    assert d['period']['from'] == local_today().isoformat()
    assert client.app.openapi()['paths']['/api/dashboard/summary']['get'].get('deprecated') is True


def test_dashboard_summary_cash_balance(client, db, t):
    def tx(branch, typ, amount, cur='UZS', **kw):
        db.add(Transaction(company_id=t['c'].id, branch_id=branch.id, type=typ, amount=Decimal(amount),
                           currency_code=cur, **kw))
    tx(t['a1'], 'income', 1000)
    tx(t['a1'], 'expense', 300)
    tx(t['a1'], 'income', 50, cur='USD')
    tx(t['a2'], 'income', 7000)
    tx(t['a1'], 'income', 999, reference_type='shift')            # ichki harakat — hisobga olinmaydi
    # T2.7: umumiy balans UZS ekvivalentida (USD kursi 100), valyuta bo'yicha qismi alohida qoladi
    db.add(Currency(name='US Dollar', code='USD', rate=Decimal('100'), company_id=t['c'].id))
    db.flush()
    c = client.login(t['admin'])
    allc = c.get('/api/dashboard/summary').json()
    assert allc['cash_balance'] == 7700 + 50 * 100
    assert allc['cash_balance_by_currency'] == {'UZS': 7700.0, 'USD': 50.0}
    assert allc['cash_balance_scope'] == 'company'
    br = c.get('/api/dashboard/summary', params={'branch_id': t['a1'].id}).json()
    assert br['cash_balance'] == 700 + 50 * 100 and br['cash_balance_scope'] == 'branch'
    assert br['cash_balance_by_currency'] == {'UZS': 700.0, 'USD': 50.0}
    # warehouse_id kassa balansiga ta'sir qilmaydi
    wh = c.get('/api/dashboard/summary', params={'warehouse_id': t['w2'].id}).json()
    assert wh['cash_balance'] == 7700 + 50 * 100 and wh['cash_balance_scope'] == 'company'


def test_dashboard_summary_company_isolation(client, db, t):
    _sale(db, t['ub'], t['cb'], t['wb'], amount=5_000_000)
    c = client.login(t['admin'])
    assert c.get('/api/dashboard/summary', params={'branch_id': t['bb'].id}).status_code == 404
    assert c.get('/api/dashboard/summary', params={'warehouse_id': t['wb'].id}).status_code == 404
    assert c.get('/api/dashboard/summary').json()['sales']['revenue'] == 0
    assert client.login(t['ub']).get('/api/dashboard/summary').json()['sales']['revenue'] == 5_000_000


# ── Statik tekshiruvlar (frontend / i18n) ────────────────────────────────────

def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


KEYS_T2_4 = ["mobileDashboard.returns", "mobileDashboard.net", "mobileDashboard.card", "mobileDashboard.branch", "mobileDashboard.period", "mobileDashboard.days"]


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


def test_pending_i18n_keys_consistent():
    d = _merged_i18n(KEYS_T2_4)
    assert set(d['uz']) == set(d['ru']) == set(d['en'])
    for k in ('mobileDashboard.returns', 'mobileDashboard.net', 'mobileDashboard.card',
              'mobileDashboard.branch', 'mobileDashboard.period'):
        assert k in d['uz']


def test_mobile_dashboard_frontend():
    src = _read('frontend', 'src', 'pages', 'admin', 'MobileDashboard.jsx')
    assert "branch_id" in src and "days" in src
    assert "visibilityState" in src
    assert "mobileDashboard.returns" in src and "mobileDashboard.card" in src


def test_profile_frontend():
    src = _read('frontend', 'src', 'pages', 'admin', 'Profile.jsx')
    assert "branch_id: branchId" in src                        # ombor ro'yxati filialga qarab
    assert "ROLE_LABELS[user.role]" in src                      # rol xom ko'rinmaydi
    assert "_suppressToast: true" in src                        # 403 toast yo'q
    assert "canDashboard" in src
    assert "localStorage.removeItem('dashboard_warehouse_id')" in src
    assert "(warehouses.length > 1 || warehouseId)" in src


def test_branch_filter_uses_sale_snapshot(client, db, t):
    """T1.9 bilan mos: sotuvning Sale.branch_id snapshot'i bor bo'lsa, filial shu bo'yicha (ombor hozirgi filiali emas)."""
    s = _sale(db, t['admin'], t['c'], t['w2'], amount=4000)
    s.branch_id = t['a1'].id
    db.flush()
    assert _summary(client, t['admin'], branch_id=t['a1'].id).json()['today_sales'] == 4000
    assert _summary(client, t['admin'], branch_id=t['a2'].id).json()['today_sales'] == 0
