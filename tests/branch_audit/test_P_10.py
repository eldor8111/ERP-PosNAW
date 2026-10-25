"""P.10 — E-Code POS (desktop) dorixona uchun: GET /products ro'yxatida yaroqlilik muddati.

Desktop kassa tovarlarni GET /products dan oladi (pos-list emas). Dorixona yoqilgan korxonada ro'yxat qatorida
`nearest_expiry` (eng yaqin yaroqli muddat), `expiry_warn` va `expired_qty` (muddati o'tgan qoldiq) bo'ladi —
web kassa (pos-list) bilan bir xil hisob. Oddiy korxona javobida bu maydonlar umuman chiqmaydi.
"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.product_pharma import ProductPharma
from app.models.warehouse import Warehouse
from app.services.batch_allocator import tashkent_today

FIELDS = ('nearest_expiry', 'expiry_warn', 'expired_qty')


def _pharmacy_on(db, company, warn_days=30):
    company.pharmacy_enabled = True
    company.pharmacy_settings = {'expiry_warn_days': warn_days}
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code='pharmacy', is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _dt(days):
    return datetime.combine(tashkent_today() + timedelta(days=days), time.min)


def _drug(db, c, wh, batches, name):
    """batches: [(miqdor, muddatgacha kun)] — shu omborda."""
    p = Product(name=name, sku='SKU-' + name[-6:], barcode='B' + name[-6:], company_id=c.id,
                cost_price=D('500'), sale_price=D('1000'))
    db.add(p)
    db.flush()
    db.add(ProductPharma(product_id=p.id, company_id=c.id))
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(sum(q for q, _ in batches))))
    for q, days in batches:
        db.add(Batch(product_id=p.id, warehouse_id=wh.id, quantity=D(q), initial_quantity=D(q),
                     purchase_price=D('500'), company_id=c.id, expiry_date=_dt(days)))
    db.flush()
    return p


def _rows(client, u, **params):
    r = client.login(u).get('/api/products/', params={'limit': 500, **params})
    assert r.status_code == 200, r.text
    return {x['id']: x for x in r.json()}


def test_products_list_has_expiry_fields_in_pharmacy(client, db, mk):
    c, _, wh, u = mk.tenant()
    _pharmacy_on(db, c, warn_days=30)
    p = _drug(db, c, wh, [(5, -3), (7, -1), (20, 10), (30, 200)], name='Dori P10-000001')
    far = _drug(db, c, wh, [(10, 400)], name='Dori P10-000002')
    rows = _rows(client, u, warehouse_id=wh.id)
    assert rows[p.id]['nearest_expiry'] == (tashkent_today() + timedelta(days=10)).isoformat()
    assert rows[p.id]['expiry_warn'] is True                     # 10 kun <= 30
    assert rows[p.id]['expired_qty'] == 12                       # 5 + 7 muddati o'tgan
    assert rows[far.id]['expiry_warn'] is False and rows[far.id]['expired_qty'] == 0
    assert rows[far.id]['nearest_expiry'] == (tashkent_today() + timedelta(days=400)).isoformat()


def test_products_list_without_warehouse_uses_company_warehouses(client, db, mk):
    c, _, wh, u = mk.tenant()
    _pharmacy_on(db, c)
    wh2 = Warehouse(name='Ikkinchi ombor P10', company_id=c.id, branch_id=wh.branch_id)
    db.add(wh2)
    db.flush()
    p = _drug(db, c, wh2, [(4, -2), (6, 60)], name='Dori P10-000003')
    rows = _rows(client, u)
    assert rows[p.id]['expired_qty'] == 4
    assert rows[p.id]['nearest_expiry'] == (tashkent_today() + timedelta(days=60)).isoformat()
    # boshqa ombor tanlansa — o'sha ombor partiyalari hisoblanadi (wh dagi dori; wh2 dagi muddati o'tgan qoldiq kirmaydi)
    q = _drug(db, c, wh, [(9, 30)], name='Dori P10-000005')
    db.add(Batch(product_id=q.id, warehouse_id=wh2.id, quantity=D(3), initial_quantity=D(3),
                 purchase_price=D('500'), company_id=c.id, expiry_date=_dt(-5)))
    db.flush()
    assert _rows(client, u)[q.id]['expired_qty'] == 3
    assert _rows(client, u, warehouse_id=wh.id)[q.id]['expired_qty'] == 0


def test_products_list_plain_company_unchanged(client, db, mk):
    c, _, wh, u = mk.tenant()                                    # dorixona yoqilmagan
    p = _drug(db, c, wh, [(5, -3), (8, 20)], name='Dori P10-000004')
    row = _rows(client, u, warehouse_id=wh.id)[p.id]
    for f in FIELDS + ('units',):
        assert f not in row, f


def test_features_endpoint_exposes_pharmacy_for_desktop(client, db, mk):
    c, _, _, u = mk.tenant()
    r = client.login(u).get('/api/companies/me/features')
    assert r.status_code == 200 and r.json()['pharmacy'] is False
    _pharmacy_on(db, c, warn_days=45)
    body = client.login(u).get('/api/companies/me/features').json()
    assert body['pharmacy'] is True
    assert body['pharmacy_settings']['expiry_warn_days'] == 45
    assert 'price_round' in body['pharmacy_settings']
