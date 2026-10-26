"""Sotuvlar ro'yxati (web "Sotuv" -> Sotuvlar): sana oralig'i Toshkent kunida, sonlar va jamilar butun filtr bo'yicha.

Muammo: 25–26 oralig'ida 25 dagi sotuvlar ko'rinmas, 26 dagilari "to'liq emas" edi. Sabablari:
- sahifada 25 ta sotuv bor edi, pastdagi "N ta sotuv" va summalar faqat shu sahifaniki edi;
- filtr o'zgarganda sahifa raqami 1-sahifaga qaytmasdi;
- kun chegarasi UTC yarim tuni (Toshkent 05:00) edi, boshqa sahifalar esa `date_bounds` ishlatadi.
"""
import itertools
import os
from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.sale import PaymentType, Sale, SaleStatus
from app.utils.report_utils import local_day_start, local_today

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
D = Decimal


def _day(offset):
    return (local_today() + timedelta(days=offset)).isoformat()


def _sale(db, w, day_offset, total, paid, status=SaleStatus.completed):
    c, b, wh, u = w
    s = Sale(number=f"SLD-{next(_seq)}", cashier_id=u.id, company_id=c.id, warehouse_id=wh.id, branch_id=b.id,
             total_amount=D(total), paid_amount=D(paid), paid_cash=D(paid), payment_type=PaymentType.cash,
             status=status,
             # kun o'rtasi (Toshkent 12:00): kun chegarasidan uzoq
             created_at=local_day_start(local_today() + timedelta(days=day_offset)) + timedelta(hours=12))
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def w(mk):
    return mk.tenant()


def test_with_total_counts_and_sums_whole_filter_not_page(client, db, w):
    y1 = _sale(db, w, -1, 1000, 1000)
    y2 = _sale(db, w, -1, 3000, 1000)                 # qarz 2000
    for _ in range(3):
        _sale(db, w, 0, 500, 500)
    _sale(db, w, 0, 9000, 9000, status=SaleStatus.refunded)   # standart ro'yxatda yo'q
    _sale(db, w, -3, 7000, 7000)                      # oraliqdan tashqarida
    api = client.login(w[3])

    r = api.get('/api/sales/', params={'date_from': _day(-1), 'date_to': _day(0), 'with_total': True, 'limit': 2})
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d['items']) == 2 and d['total'] == 5
    assert (d['sum_total'], d['sum_paid'], d['sum_debt']) == (5500, 3500, 2000)

    last = api.get('/api/sales/', params={'date_from': _day(-1), 'date_to': _day(0), 'with_total': True,
                                      'limit': 2, 'skip': 4}).json()
    assert len(last['items']) == 1 and last['items'][0]['number'] in (y1.number, y2.number)   # kechagisi oxirgi sahifada

    one_day = api.get('/api/sales/', params={'date_from': _day(-1), 'date_to': _day(-1), 'with_total': True}).json()
    assert one_day['total'] == 2 and one_day['sum_total'] == 4000

    plain = api.get('/api/sales/', params={'date_from': _day(-1), 'date_to': _day(0)})
    assert isinstance(plain.json(), list) and plain.headers['X-Total-Count'] == '5'


def test_sales_list_and_pdf_use_tashkent_day_bounds():
    with open(os.path.join(ROOT, 'app/routers/sales.py'), encoding='utf-8') as f:
        src = f.read()
    assert 'datetime.combine(date_' not in src and 'datetime.combine(today' not in src
    assert src.count('q = _sale_date_filter(q, date_from, date_to, date_today)') == 2
    helper = src[src.index('def _sale_date_filter'):]
    assert 'date_bounds(date_from, date_to)' in helper and 'local_day_start(local_today())' in helper


def test_sales_page_shows_whole_filter_totals():
    with open(os.path.join(ROOT, 'frontend/src/pages/admin/UlgurjiSotuv.jsx'), encoding='utf-8') as f:
        src = f.read()
    assert "useState({ date_from: today(), date_to: today()," in src           # mahalliy kun, UTC emas
    assert "with_total: true" in src and "const LIMIT = 100;" in src
    assert "{t('wholesale.salesCount', { count: salesMeta.total })}" in src and "fmt(salesMeta.sum_total)" in src
    assert "disabled={(page + 1) * LIMIT >= salesMeta.total}" in src
    assert "const setFilter = (k, v) => { setPage(0);" in src
    assert "onChange={e => setFilters(f =>" not in src
    excel = src[src.index('const exportToExcel = async'):src.index('const exportToPdf = async')]
    assert 'fetchAllSales()' in excel and 'allSales.map(' in excel
    for lang in ('uz', 'ru', 'en'):
        with open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8') as f:
            assert "'wholesale.pageOfTotal'" in f.read()
