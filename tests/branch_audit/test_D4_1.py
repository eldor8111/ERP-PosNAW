"""D4.1 — Muddat hisoboti va hisobdan chiqarish dalolatnomasi (dorixona rejimi)."""
import itertools
import json
import pathlib
from datetime import datetime, timedelta, timezone

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.category import Category
from app.models.product import Product
from app.models.user import UserRole
from app.services.expiry import expired_batches_query
from app.utils.report_utils import local_today

ROOT = pathlib.Path(__file__).resolve().parents[2]
_n = itertools.count(1)


def _pharmacy(db, company):
    company.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _product(db, company, name=None, perishable=None):
    n = next(_n)
    cat_id = None
    if perishable is not None:
        cat = Category(name=f"Kat {n}", company_id=company.id, is_perishable=perishable)
        db.add(cat)
        db.flush()
        cat_id = cat.id
    p = Product(name=name or f"Dori {n}", sku=f"D41-{n}", barcode=f"BCD41-{n}", company_id=company.id,
                category_id=cat_id, cost_price=1000, sale_price=1500)
    db.add(p)
    db.flush()
    return p


def _batch(db, company, product, warehouse, days, qty=10, price=2000, lot=None):
    exp = datetime.combine(local_today() + timedelta(days=days), datetime.min.time())
    b = Batch(product_id=product.id, warehouse_id=warehouse.id, company_id=company.id,
              lot_number=lot or f"L{next(_n)}", expiry_date=exp, quantity=qty, initial_quantity=qty,
              purchase_price=price)
    db.add(b)
    db.flush()
    return b


# ─── expiry.py qoidasi ───────────────────────────────────────────────────────

def test_pharmacy_sees_all_medicines(db, mk):
    c, b, w, u = mk.tenant()
    _pharmacy(db, c)
    plain = _product(db, c, perishable=False)
    nocat = _product(db, c)
    perish = _product(db, c, perishable=True)
    ids = [_batch(db, c, p, w, -3).id for p in (plain, nocat, perish)]
    got = {r.id for r in expired_batches_query(db, c.id, local_today(), only_expired=True).all()}
    assert set(ids) <= got


def test_plain_store_only_perishable(db, mk):
    c, b, w, u = mk.tenant()
    plain = _product(db, c, perishable=False)
    nocat = _product(db, c)
    perish = _product(db, c, perishable=True)
    b1 = _batch(db, c, plain, w, -3)
    b2 = _batch(db, c, nocat, w, -3)
    b3 = _batch(db, c, perish, w, -3)
    got = {r.id for r in expired_batches_query(db, c.id, local_today(), only_expired=True).all()}
    assert got == {b3.id}
    assert b1.id not in got and b2.id not in got


def test_existing_inventory_endpoint_sees_all_in_pharmacy(client, db, mk):
    c, b, w, admin = mk.tenant()
    p = _product(db, c, perishable=False)
    bt = _batch(db, c, p, w, 5)
    cl = client.login(admin)
    assert bt.id not in [x['batch_id'] for x in cl.get('/api/inventory/expiring-batches?days=30').json()]
    _pharmacy(db, c)
    assert bt.id in [x['batch_id'] for x in cl.get('/api/inventory/expiring-batches?days=30').json()]


# ─── /pharmacy/reports/expiry ────────────────────────────────────────────────

def test_report_forbidden_for_plain_store(client, db, mk):
    c, b, w, admin = mk.tenant()
    p = _product(db, c, perishable=True)
    _batch(db, c, p, w, -1)
    cl = client.login(admin)
    assert cl.get('/api/pharmacy/reports/expiry').status_code == 403
    assert cl.get('/api/pharmacy/reports/write-off-act').status_code == 403


def test_report_periods_and_fields(client, db, mk):
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    p = _product(db, c, name="Paratsetamol", perishable=False)
    b_exp = _batch(db, c, p, w, -2, qty=4, price=1500, lot="SER-EXP")
    b20 = _batch(db, c, p, w, 20, qty=5, price=1000, lot="SER-20")
    b50 = _batch(db, c, p, w, 50, lot="SER-50")
    b80 = _batch(db, c, p, w, 80, lot="SER-80")
    _batch(db, c, p, w, 200, lot="SER-200")
    _batch(db, c, p, w, 10, qty=0, lot="SER-EMPTY")
    cl = client.login(admin)

    def ids(days):
        r = cl.get(f'/api/pharmacy/reports/expiry?days={days}')
        assert r.status_code == 200, r.text
        return {x['batch_id'] for x in r.json()['rows']}

    assert ids('expired') == {b_exp.id}
    assert ids('30') == {b20.id}
    assert ids('60') == {b20.id, b50.id}
    assert ids('90') == {b20.id, b50.id, b80.id}
    assert cl.get('/api/pharmacy/reports/expiry?days=45').status_code == 422

    data = cl.get('/api/pharmacy/reports/expiry?days=30').json()
    row = data['rows'][0]
    assert row['product_name'] == 'Paratsetamol' and row['lot_number'] == 'SER-20'
    assert row['warehouse_name'] == w.name and row['branch_name'] == b.name
    assert row['quantity'] == 5 and row['unit_cost'] == 1000 and row['amount'] == 5000
    assert row['days_left'] == 20 and row['status'] == '30'
    assert data['summary']['amount'] == 5000 and data['summary']['batches'] == 1

    exp = cl.get('/api/pharmacy/reports/expiry?days=expired').json()['rows'][0]
    assert exp['status'] == 'expired' and exp['days_left'] == -2 and exp['amount'] == 6000


def test_report_search_and_csv(client, db, mk):
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    p1 = _product(db, c, name="Amoksitsillin")
    p2 = _product(db, c, name="Analgin")
    _batch(db, c, p1, w, 10, lot="AAA-1")
    _batch(db, c, p2, w, 10, lot="BBB-2")
    cl = client.login(admin)
    rows = cl.get('/api/pharmacy/reports/expiry?days=30&search=amoks').json()['rows']
    assert [r['product_name'] for r in rows] == ['Amoksitsillin']
    rows = cl.get('/api/pharmacy/reports/expiry?days=30&search=BBB').json()['rows']
    assert [r['lot_number'] for r in rows] == ['BBB-2']
    r = cl.get('/api/pharmacy/reports/expiry?days=30&format=csv')
    assert r.status_code == 200 and r.headers['content-type'].startswith('text/csv')
    text = r.content.decode('utf-8-sig')
    assert 'Mahsulot' in text.splitlines()[0] and 'AAA-1' in text and 'BBB-2' in text


def test_company_isolation(client, db, mk):
    a, ba, wa, admin_a = mk.tenant()
    bco, bb, wb, admin_b = mk.tenant()
    _pharmacy(db, a)
    _pharmacy(db, bco)
    pa = _product(db, a, name="A dori")
    pb = _product(db, bco, name="B dori")
    own = _batch(db, a, pa, wa, 10)
    other = _batch(db, bco, pb, wb, 10)
    cl = client.login(admin_a)
    got = {r['batch_id'] for r in cl.get('/api/pharmacy/reports/expiry?days=30').json()['rows']}
    assert got == {own.id}                                   # o'z resursi ishlaydi, boshqasi ko'rinmaydi
    assert cl.get(f'/api/pharmacy/reports/expiry?warehouse_id={wb.id}').status_code == 404
    assert cl.get(f'/api/pharmacy/reports/expiry?branch_id={bb.id}').status_code == 404
    assert cl.get(f'/api/pharmacy/reports/write-off-act?days=30&warehouse_id={wb.id}').status_code == 404
    # dalolatnoma ham boshqa korxona partiyasini chiqarmaydi
    r = cl.get(f'/api/pharmacy/reports/write-off-act?days=30&batch_ids={other.id}')
    assert r.status_code == 404


def test_branch_permission(client, db, mk):
    c, b1, w1, admin = mk.tenant()
    b2 = mk.branch(c)
    w2 = mk.warehouse(c, b2)
    _pharmacy(db, c)
    p = _product(db, c)
    x1 = _batch(db, c, p, w1, 10)
    x2 = _batch(db, c, p, w2, 10)
    mgr = mk.user(c, role=UserRole.manager, branch=b1)

    # admin ikkala filialni ko'radi
    got = {r['batch_id'] for r in client.login(admin).get('/api/pharmacy/reports/expiry?days=30').json()['rows']}
    assert got == {x1.id, x2.id}
    # filialga biriktirilgan menejer faqat o'z filialini ko'radi
    cl = client.login(mgr)
    got = {r['batch_id'] for r in cl.get('/api/pharmacy/reports/expiry?days=30').json()['rows']}
    assert got == {x1.id}
    assert cl.get(f'/api/pharmacy/reports/expiry?days=30&branch_id={b2.id}').status_code == 403
    assert cl.get(f'/api/pharmacy/reports/expiry?days=30&warehouse_id={w2.id}').status_code == 403
    assert cl.get(f'/api/pharmacy/reports/expiry?days=30&branch_id={b1.id}').status_code == 200
    assert cl.get(f'/api/pharmacy/reports/write-off-act?days=30&batch_ids={x2.id}').status_code == 404


def test_cashier_cannot_open_report(client, db, mk):
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    assert client.login(cashier).get('/api/pharmacy/reports/expiry').status_code == 403


# ─── Dalolatnoma PDF ─────────────────────────────────────────────────────────

def test_write_off_act_pdf(client, db, mk):
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    p = _product(db, c, name="Валидол (Uzb: O'tgan)")
    x = _batch(db, c, p, w, -5, lot="SER-PDF")
    _batch(db, c, p, w, -6, lot="SER-PDF2")
    cl = client.login(admin)
    r = cl.get('/api/pharmacy/reports/write-off-act', params={
        'days': 'expired', 'commission': ['Aliyev A.', 'Valiyev B.'], 'reason': 'Muddati tugagan'})
    assert r.status_code == 200, r.text
    assert r.headers['content-type'] == 'application/pdf'
    assert r.content[:5] == b'%PDF-'
    assert 'dalolatnoma' in r.headers['content-disposition']
    # tanlangan partiyalar bilan ham ishlaydi
    r = cl.get(f'/api/pharmacy/reports/write-off-act?days=expired&batch_ids={x.id}&commission=A,B,C')
    assert r.status_code == 200 and r.content[:5] == b'%PDF-'
    # bo'sh natija -> 404
    assert cl.get('/api/pharmacy/reports/write-off-act?days=30').status_code == 404
    assert cl.get('/api/pharmacy/reports/write-off-act?batch_ids=abc').status_code == 422


def test_write_off_act_many_rows_paginates(client, db, mk):
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    p = _product(db, c)
    for i in range(60):
        _batch(db, c, p, w, -1, lot=f"S{i}")
    r = client.login(admin).get('/api/pharmacy/reports/write-off-act?days=expired')
    assert r.status_code == 200 and r.content[:5] == b'%PDF-'
    assert r.content.count(b'/Type /Page\n') >= 2 or r.content.count(b'/Type /Page') >= 3


# ─── i18n va fayllar ─────────────────────────────────────────────────────────

def test_pending_i18n_keys_match():
    d = json.loads((pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D4.1.json").read_text(encoding='utf-8'))
    assert set(d) == {'uz', 'ru', 'en'}
    assert set(d['uz']) == set(d['ru']) == set(d['en'])
    src = (ROOT / 'frontend' / 'src' / 'pages' / 'admin' / 'pharmacy' / 'ExpiryReport.jsx').read_text(encoding='utf-8')
    import re
    used = set(re.findall(r"tf\('(pharmacyExpiry\.[A-Za-z0-9]+)'", src))
    assert used and used <= set(d['uz'])


def test_pdf_fallback_without_unicode_font(monkeypatch):
    """Serverda Unicode shrift bo'lmasa ham PDF yaratiladi (kirill belgilar '?' bo'ladi)."""
    from datetime import date
    from app.routers import pharmacy_reports as pr
    monkeypatch.setattr(pr, '_first_existing', lambda paths: None)
    rows = [{'product_name': 'Валидол', 'variant_name': None, 'lot_number': 'S1', 'expiry_date': '2026-01-01',
             'warehouse_name': 'Ombor', 'quantity': 2.0, 'unit_cost': 100.0, 'amount': 200.0}]
    out = pr.build_write_off_pdf(company_name='Дорихона', branch_label='Filial', act_date=date(2026, 1, 2),
                                 rows=rows, commission=[], reason='Sabab')
    assert out[:5] == b'%PDF-'
