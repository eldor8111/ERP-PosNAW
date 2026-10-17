"""T1.8 — Chiqim va yaroqlilik muddati oqimlari.

Qamrov: chiqimda ombor majburiy (400/404/403), partiyasiz qoldiqni chiqim qilish (strict=False),
partiyalar shu ombor bo'yicha yechiladi, bekor qilish aynan yozilgan ombor/variantga qaytaradi,
PUT tahriri atomik, korxona izolyatsiyasi, expiring-batches (perishable qoidasi, ombor/filial),
qo'lda hisobdan chiqarish (batch_id/batch_ids, min(partiya, stock)), cron (perishable, ikki marta,
warehouse_id), Telegram ogohlantirishi (ombor nomi).
"""
import asyncio
import itertools
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.batch import Batch
from app.models.category import Category
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import UserRole

_seq = itertools.count(1)


# ─── yordamchilar ───

def _category(db, company, perishable=True, name=None):
    c = Category(name=name or f'Kat {next(_seq)}', company_id=company.id, is_perishable=perishable)
    db.add(c)
    db.flush()
    return c


def _product(db, company, name=None, category=None):
    n = next(_seq)
    p = Product(name=name or f'Mahsulot {n}', sku=f'SKU-T18-{n}', barcode=f'BC-T18-{n}',
                company_id=company.id, cost_price=0, sale_price=0, product_type='simple',
                category_id=category.id if category else None)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty, variant_id=None):
    s = StockLevel(product_id=product.id, warehouse_id=warehouse.id, variant_id=variant_id, quantity=Decimal(qty))
    db.add(s)
    db.flush()
    return s


def _qty(db, product, warehouse, variant_id=None):
    q = db.query(StockLevel).filter(StockLevel.product_id == product.id, StockLevel.warehouse_id == warehouse.id)
    q = q.filter(StockLevel.variant_id == variant_id) if variant_id else q.filter(StockLevel.variant_id.is_(None))
    s = q.first()
    return float(s.quantity) if s else None


def _batch(db, product, warehouse, qty, lot='LOT', expiry=None, price='5000'):
    b = Batch(product_id=product.id, warehouse_id=warehouse.id, company_id=product.company_id,
              lot_number=lot, expiry_date=expiry, initial_quantity=Decimal(qty), quantity=Decimal(qty),
              purchase_price=Decimal(price))
    db.add(b)
    db.flush()
    return b


def _bq(db, batch):
    db.expire_all()
    return float(db.get(Batch, batch.id).quantity)


def _all_levels(db):
    return sorted((s.product_id, s.warehouse_id, s.variant_id, float(s.quantity)) for s in db.query(StockLevel).all())


def _tenant(db, mk, role=UserRole.admin):
    """Korxona: bitta filial, ikki ombor (Chilonzor wh1, Yunusobod wh2), admin."""
    c = mk.company()
    b = mk.branch(c)
    wh1 = mk.warehouse(c, b, name='Chilonzor')
    wh2 = mk.warehouse(c, b, name='Yunusobod')
    u = mk.user(c, role=role, branch=b)
    return {'c': c, 'b': b, 'wh1': wh1, 'wh2': wh2, 'u': u}


def _chiqim_body(product, qty, wh=None, **item):
    body = {'items': [dict({'product_id': product.id, 'quantity': qty, 'type': 'Brak'}, **item)]}
    if wh is not None:
        body['warehouse_id'] = wh.id
    return body


def _mv(db, ref, rtype):
    return db.query(StockMovement).filter(
        StockMovement.reference_type == rtype, StockMovement.reference_id == ref
    ).order_by(StockMovement.id).all()


# ─── 1. Chiqim: ombor majburiy ───

def test_chiqim_warehouse_required_when_ambiguous(client, db, mk):
    t = _tenant(db, mk)            # ikki faol ombor
    p = _product(db, t['c'])
    _stock(db, p, t['wh1'], 10)
    r = client.login(t['u']).post('/api/inventory/chiqims', json=_chiqim_body(p, 3))
    assert r.status_code == 400, r.text
    assert r.json()['detail'] == 'Ombor tanlanmagan'
    assert _qty(db, p, t['wh1']) == 10.0
    assert db.query(StockMovement).count() == 0


def test_chiqim_single_warehouse_is_auto_selected(client, db, mk):
    c, b, wh, u = mk.tenant()      # yagona ombor
    p = _product(db, c)
    _stock(db, p, wh, 10)
    r = client.login(u).post('/api/inventory/chiqims', json=_chiqim_body(p, 4))
    assert r.status_code == 200, r.text
    assert _qty(db, p, wh) == 6.0
    assert _mv(db, r.json()['reference_id'], 'chiqim')[0].warehouse_id == wh.id


def test_chiqim_warehouse_checks_company_active_and_branch(client, db, mk):
    t = _tenant(db, mk)
    other = _tenant(db, mk)
    p = _product(db, t['c'])
    _stock(db, p, t['wh1'], 10)
    cl = client.login(t['u'])
    # begona korxona ombori — 404
    assert cl.post('/api/inventory/chiqims', json=_chiqim_body(p, 1, other['wh1'])).status_code == 404
    # nofaol ombor — 404
    t['wh2'].is_active = False
    db.flush()
    assert cl.post('/api/inventory/chiqims', json=_chiqim_body(p, 1, t['wh2'])).status_code == 404
    # non-admin boshqa filial ombori — 403
    b2 = mk.branch(t['c'])
    wh_b2 = mk.warehouse(t['c'], b2, name='Sergeli')
    mgr = mk.user(t['c'], role=UserRole.manager, branch=t['b'])
    assert client.login(mgr).post('/api/inventory/chiqims', json=_chiqim_body(p, 1, wh_b2)).status_code == 403
    assert _qty(db, p, t['wh1']) == 10.0


# ─── 2. Partiyasiz qoldiq, ombor bo'yicha FIFO ───

def test_chiqim_without_batches_does_not_fail(client, db, mk):
    t = _tenant(db, mk)
    p = _product(db, t['c'])
    _stock(db, p, t['wh1'], 5)     # import orqali kirgan, partiyasiz
    r = client.login(t['u']).post('/api/inventory/chiqims', json=_chiqim_body(p, 5, t['wh1']))
    assert r.status_code == 200, r.text
    assert _qty(db, p, t['wh1']) == 0.0


def test_chiqim_deducts_batches_of_selected_warehouse_only(client, db, mk):
    t = _tenant(db, mk)
    p = _product(db, t['c'])
    _stock(db, p, t['wh1'], 10)
    _stock(db, p, t['wh2'], 10)
    ba = _batch(db, p, t['wh1'], 10, lot='A')
    bb = _batch(db, p, t['wh2'], 10, lot='B')
    r = client.login(t['u']).post('/api/inventory/chiqims', json=_chiqim_body(p, 4, t['wh1']))
    assert r.status_code == 200, r.text
    assert _bq(db, ba) == 6.0 and _bq(db, bb) == 10.0
    assert _qty(db, p, t['wh1']) == 6.0 and _qty(db, p, t['wh2']) == 10.0


# ─── 3. Bekor qilish: aynan o'sha ombor va variant ───

def test_chiqim_cancel_returns_to_original_warehouse_and_variant(client, db, mk):
    t = _tenant(db, mk)
    p = _product(db, t['c'])
    v1 = ProductVariant(product_id=p.id, name='XL')
    v2 = ProductVariant(product_id=p.id, name='M')
    db.add_all([v1, v2])
    db.flush()
    _stock(db, p, t['wh1'], 50, variant_id=v1.id)      # eng ko'p qoldiq Chilonzorda
    _stock(db, p, t['wh2'], 7, variant_id=v1.id)
    _stock(db, p, t['wh2'], 9, variant_id=v2.id)
    b2 = _batch(db, p, t['wh2'], 7, lot='YU')
    b2.variant_id = v1.id
    db.flush()
    cl = client.login(t['u'])
    r = cl.post('/api/inventory/chiqims', json=_chiqim_body(p, 5, t['wh2'], variant_id=v1.id))
    assert r.status_code == 200, r.text
    ref = r.json()['reference_id']
    assert _qty(db, p, t['wh2'], v1.id) == 2.0 and _bq(db, b2) == 2.0
    before_levels = _all_levels(db)

    r = cl.delete(f'/api/inventory/chiqims/{ref}')
    assert r.status_code == 200, r.text
    assert _qty(db, p, t['wh2'], v1.id) == 7.0
    assert _qty(db, p, t['wh1'], v1.id) == 50.0 and _qty(db, p, t['wh2'], v2.id) == 9.0
    assert _bq(db, b2) == 7.0
    # ortiqcha qator (boshqa ombor/variant/NULL) hosil bo'lmadi
    assert len(_all_levels(db)) == len(before_levels)
    rev = _mv(db, ref, 'chiqim_revert')
    assert len(rev) == 1 and rev[0].warehouse_id == t['wh2'].id and rev[0].variant_id == v1.id
    assert db.query(Batch).filter(Batch.lot_number == 'chiqim-revert').count() == 0
    # takroriy bekor qilish — 400, qoldiq oshmaydi
    assert cl.delete(f'/api/inventory/chiqims/{ref}').status_code == 400
    assert _qty(db, p, t['wh2'], v1.id) == 7.0


def test_chiqim_cancel_creates_batch_in_same_warehouse_when_none(client, db, mk):
    t = _tenant(db, mk)
    p = _product(db, t['c'])
    _stock(db, p, t['wh2'], 5)
    cl = client.login(t['u'])
    ref = cl.post('/api/inventory/chiqims', json=_chiqim_body(p, 5, t['wh2'])).json()['reference_id']
    assert cl.delete(f'/api/inventory/chiqims/{ref}').status_code == 200
    nb = db.query(Batch).filter(Batch.lot_number == 'chiqim-revert').all()
    assert len(nb) == 1 and nb[0].warehouse_id == t['wh2'].id and float(nb[0].quantity) == 5.0


# ─── 4. PUT atomikligi ───

def test_chiqim_put_updates_in_one_transaction(client, db, mk):
    t = _tenant(db, mk)
    p = _product(db, t['c'])
    _stock(db, p, t['wh2'], 20)
    cl = client.login(t['u'])
    ref = cl.post('/api/inventory/chiqims', json=_chiqim_body(p, 5, t['wh2'])).json()['reference_id']
    assert _qty(db, p, t['wh2']) == 15.0

    r = cl.put(f'/api/inventory/chiqims/{ref}', json=_chiqim_body(p, 8, t['wh2']))
    assert r.status_code == 200, r.text
    assert r.json()['reference_id'] == ref
    assert _qty(db, p, t['wh2']) == 12.0

    # ro'yxat va tafsilotda faqat joriy qatorlar
    det = cl.get(f'/api/inventory/chiqims/{ref}').json()
    assert len(det) == 1 and float(det[0]['quantity']) == 8.0
    assert det[0]['warehouse_id'] == t['wh2'].id and det[0]['warehouse_name'] == 'Yunusobod'
    lst = [d for d in cl.get('/api/inventory/chiqims').json() if d['reference_id'] == ref]
    assert len(lst) == 1 and float(lst[0]['total_qty']) == 8.0 and lst[0]['warehouse_name'] == 'Yunusobod'

    # tahrirdan keyin bekor qilish — faqat yangi qator qaytadi
    assert cl.delete(f'/api/inventory/chiqims/{ref}').status_code == 200
    assert _qty(db, p, t['wh2']) == 20.0
    assert cl.get('/api/inventory/chiqims').json() == []


def test_chiqim_put_failure_keeps_old_chiqim(client, db, mk):
    t = _tenant(db, mk)
    other = _tenant(db, mk)
    p = _product(db, t['c'])
    foreign = _product(db, other['c'])
    _stock(db, p, t['wh2'], 20)
    cl = client.login(t['u'])
    ref = cl.post('/api/inventory/chiqims', json=_chiqim_body(p, 5, t['wh2'])).json()['reference_id']
    levels = _all_levels(db)
    n_moves = db.query(StockMovement).count()

    # yangi qator xato beradi (begona mahsulot) — eski chiqim bekor bo'lmaydi
    r = cl.put(f'/api/inventory/chiqims/{ref}', json=_chiqim_body(foreign, 1, t['wh2']))
    assert r.status_code == 404, r.text
    assert _all_levels(db) == levels
    assert db.query(StockMovement).count() == n_moves
    assert len(_mv(db, ref, 'chiqim')) == 1 and _mv(db, ref, 'chiqim_revert') == []
    assert _qty(db, p, t['wh2']) == 15.0


# ─── 5. reference_id va korxona izolyatsiyasi ───

def test_chiqim_reference_ids_unique_and_company_isolation(client, db, mk):
    a = _tenant(db, mk)
    b = _tenant(db, mk)
    pa = _product(db, a['c'])
    pb = _product(db, b['c'])
    _stock(db, pa, a['wh1'], 10)
    _stock(db, pb, b['wh1'], 10)
    ca, cb = client.login(a['u']), None
    ra = ca.post('/api/inventory/chiqims', json=_chiqim_body(pa, 1, a['wh1'])).json()['reference_id']
    ra2 = ca.post('/api/inventory/chiqims', json=_chiqim_body(pa, 1, a['wh1'])).json()['reference_id']
    cb = client.login(b['u'])
    rb = cb.post('/api/inventory/chiqims', json=_chiqim_body(pb, 2, b['wh1'])).json()['reference_id']
    assert len({ra, ra2, rb}) == 3

    ca = client.login(a['u'])
    before = _all_levels(db)
    # A foydalanuvchisi B chiqimini ko'rmaydi, o'chira/tahrirlay olmaydi
    assert ca.delete(f'/api/inventory/chiqims/{rb}').status_code == 404
    assert ca.put(f'/api/inventory/chiqims/{rb}', json=_chiqim_body(pa, 1, a['wh1'])).status_code == 404
    assert ca.get(f'/api/inventory/chiqims/{rb}').json() == []
    assert all(d['reference_id'] != rb for d in ca.get('/api/inventory/chiqims').json())
    # B mahsulotini chiqim qila olmaydi
    assert ca.post('/api/inventory/chiqims', json=_chiqim_body(pb, 1, a['wh1'])).status_code == 404
    assert _all_levels(db) == before
    # ijobiy yo'l: o'z chiqimini bekor qiladi
    assert ca.delete(f'/api/inventory/chiqims/{ra}').status_code == 200


def test_chiqim_list_filter_by_warehouse(client, db, mk):
    t = _tenant(db, mk)
    p = _product(db, t['c'])
    _stock(db, p, t['wh1'], 10)
    _stock(db, p, t['wh2'], 10)
    cl = client.login(t['u'])
    r1 = cl.post('/api/inventory/chiqims', json=_chiqim_body(p, 1, t['wh1'])).json()['reference_id']
    r2 = cl.post('/api/inventory/chiqims', json=_chiqim_body(p, 1, t['wh2'])).json()['reference_id']
    out = cl.get('/api/inventory/chiqims', params={'warehouse_id': t['wh2'].id}).json()
    assert [d['reference_id'] for d in out] == [r2]
    assert {d['reference_id'] for d in cl.get('/api/inventory/chiqims').json()} == {r1, r2}


# ─── 6. Yaroqlilik muddati ro'yxati ───

def _expiry_setup(db, mk):
    t = _tenant(db, mk)
    perish = _category(db, t['c'], True)
    plain = _category(db, t['c'], False)
    sut = _product(db, t['c'], 'Sut', perish)
    dori = _product(db, t['c'], 'Dori', plain)
    for p in (sut, dori):
        _stock(db, p, t['wh1'], 20)
        _stock(db, p, t['wh2'], 20)
    now = datetime.now()
    t.update(
        sut=sut, dori=dori,
        exp1=_batch(db, sut, t['wh1'], 10, lot='S1', expiry=now - timedelta(days=3)),
        exp2=_batch(db, sut, t['wh2'], 10, lot='S2', expiry=now - timedelta(days=2)),
        soon=_batch(db, sut, t['wh1'], 5, lot='S3', expiry=now + timedelta(days=10)),
        far=_batch(db, sut, t['wh1'], 5, lot='S4', expiry=now + timedelta(days=200)),
        plain_exp=_batch(db, dori, t['wh1'], 7, lot='D1', expiry=now - timedelta(days=3)),
    )
    return t


def test_expiring_batches_perishable_rule_and_warehouse_info(client, db, mk):
    t = _expiry_setup(db, mk)
    cl = client.login(t['u'])
    r = cl.get('/api/inventory/expiring-batches')
    assert r.status_code == 200, r.text
    by_id = {x['batch_id']: x for x in r.json()}
    assert set(by_id) == {t['exp1'].id, t['exp2'].id, t['soon'].id}      # non-perishable va 200 kunlik yo'q
    x = by_id[t['exp1'].id]
    assert x['warehouse_id'] == t['wh1'].id and x['warehouse_name'] == 'Chilonzor'
    assert x['branch_id'] == t['b'].id and x['product_id'] == t['sut'].id and x['is_expired'] is True
    assert by_id[t['soon'].id]['is_expired'] is False

    # filtrlar
    ids = {x['batch_id'] for x in cl.get('/api/inventory/expiring-batches', params={'warehouse_id': t['wh2'].id}).json()}
    assert ids == {t['exp2'].id}
    ids = {x['batch_id'] for x in cl.get('/api/inventory/expiring-batches', params={'days': 300}).json()}
    assert t['far'].id in ids and t['plain_exp'].id not in ids
    ids = {x['batch_id'] for x in cl.get('/api/inventory/expiring-batches', params={'branch_id': t['b'].id}).json()}
    assert ids == {t['exp1'].id, t['exp2'].id, t['soon'].id}


def test_expiring_batches_branch_restriction_and_company_isolation(client, db, mk):
    t = _expiry_setup(db, mk)
    other = _expiry_setup(db, mk)
    # kassir boshqa filialda: bu korxona partiyalarini ko'rmaydi
    b2 = mk.branch(t['c'])
    cashier_other = mk.user(t['c'], role=UserRole.cashier, branch=b2)
    assert client.login(cashier_other).get('/api/inventory/expiring-batches').json() == []
    # o'z filialidagi kassir ko'radi
    cashier_own = mk.user(t['c'], role=UserRole.cashier, branch=t['b'])
    ids = {x['batch_id'] for x in client.login(cashier_own).get('/api/inventory/expiring-batches').json()}
    assert ids == {t['exp1'].id, t['exp2'].id, t['soon'].id}
    # B korxonasi partiyalari A ro'yxatida yo'q
    ids = {x['batch_id'] for x in client.login(t['u']).get('/api/inventory/expiring-batches').json()}
    assert not ids & {other['exp1'].id, other['exp2'].id, other['soon'].id}


# ─── 7. Qo'lda hisobdan chiqarish ───

def test_write_off_expired_single_min_batch_and_stock(client, db, mk):
    t = _expiry_setup(db, mk)
    s = db.query(StockLevel).filter(StockLevel.product_id == t['sut'].id, StockLevel.warehouse_id == t['wh1'].id).one()
    s.quantity = Decimal('4')          # partiya 10, omborda 4
    db.flush()
    r = client.login(t['u']).post('/api/inventory/write-off-expired', json={'batch_id': t['exp1'].id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['skipped'] == [] and body['written_off'] == [{'batch_id': t['exp1'].id, 'quantity': 4.0}]
    assert _qty(db, t['sut'], t['wh1']) == 0.0 and _bq(db, t['exp1']) == 0.0
    m = _mv(db, t['exp1'].id, 'batch_write_off')[0]
    assert m.type == MovementType.EXPIRED and float(m.quantity) == 4.0
    assert m.warehouse_id == t['wh1'].id and m.user_id == t['u'].id
    assert 'nolga tushirildi' in m.reason


def test_write_off_expired_batch_ids_skipped_and_errors(client, db, mk):
    t = _expiry_setup(db, mk)
    other = _expiry_setup(db, mk)
    cl = client.login(t['u'])
    empty = _batch(db, t['sut'], t['wh1'], 0, lot='EMPTY', expiry=datetime.now() - timedelta(days=1))
    r = cl.post('/api/inventory/write-off-expired',
                json={'batch_ids': [t['exp1'].id, t['exp2'].id, empty.id, other['exp1'].id]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert {w['batch_id'] for w in body['written_off']} == {t['exp1'].id, t['exp2'].id}
    assert {s['batch_id'] for s in body['skipped']} == {empty.id, other['exp1'].id}
    assert _qty(db, t['sut'], t['wh1']) == 10.0 and _qty(db, t['sut'], t['wh2']) == 10.0
    assert _bq(db, other['exp1']) == 10.0                      # begona korxona partiyasi tegilmadi

    # yagona so'rov: 404 / 400 / 422
    assert cl.post('/api/inventory/write-off-expired', json={'batch_id': other['exp2'].id}).status_code == 404
    assert cl.post('/api/inventory/write-off-expired', json={'batch_id': empty.id}).status_code == 400
    assert cl.post('/api/inventory/write-off-expired', json={}).status_code == 422
    # Alerts eski shakli {batch_ids:[id]} ham 422 bermaydi
    r = cl.post('/api/inventory/write-off-expired', json={'batch_ids': [t['soon'].id]})
    assert r.status_code == 200 and r.json()['written_off'][0]['batch_id'] == t['soon'].id


def test_write_off_expired_other_branch_manager_forbidden(client, db, mk):
    t = _expiry_setup(db, mk)
    b2 = mk.branch(t['c'])
    mgr = mk.user(t['c'], role=UserRole.manager, branch=b2)
    r = client.login(mgr).post('/api/inventory/write-off-expired', json={'batch_id': t['exp1'].id})
    assert r.status_code == 403
    assert _bq(db, t['exp1']) == 10.0


# ─── 8. Cron ───

def _scheduler(monkeypatch):
    import app.database as app_database
    import app.services.scheduler as scheduler
    monkeypatch.setattr(scheduler, 'SessionLocal', app_database.SessionLocal)
    return scheduler


def test_cron_writes_off_only_perishable_expired_and_is_idempotent(db, mk, monkeypatch):
    sched = _scheduler(monkeypatch)
    t = _expiry_setup(db, mk)

    asyncio.run(sched.auto_write_off_expired())
    db.expire_all()
    assert _bq(db, t['exp1']) == 0.0 and _bq(db, t['exp2']) == 0.0
    assert _bq(db, t['plain_exp']) == 7.0                      # perishable emas — tegilmadi
    assert _bq(db, t['soon']) == 5.0 and _bq(db, t['far']) == 5.0
    assert _qty(db, t['sut'], t['wh1']) == 10.0 and _qty(db, t['sut'], t['wh2']) == 10.0
    assert _qty(db, t['dori'], t['wh1']) == 20.0
    m = _mv(db, t['exp1'].id, 'auto_batch_write_off')
    assert len(m) == 1 and m[0].warehouse_id == t['wh1'].id and m[0].type == MovementType.EXPIRED

    # ikkinchi marta — qoldiq qayta kamaymaydi
    n = db.query(StockMovement).count()
    asyncio.run(sched.auto_write_off_expired())
    assert _qty(db, t['sut'], t['wh1']) == 10.0 and _qty(db, t['sut'], t['wh2']) == 10.0
    assert db.query(StockMovement).count() == n


def test_cron_skips_batch_without_stock_row_and_other_batches_continue(db, mk, monkeypatch):
    sched = _scheduler(monkeypatch)
    t = _expiry_setup(db, mk)
    db.query(StockLevel).filter(StockLevel.product_id == t['sut'].id, StockLevel.warehouse_id == t['wh2'].id).delete()
    db.flush()
    asyncio.run(sched.auto_write_off_expired())
    assert _bq(db, t['exp2']) == 10.0                          # qoldiq qatori yo'q — o'tkazib yuborildi
    assert _bq(db, t['exp1']) == 0.0                           # boshqa partiya baribir yechildi


def test_cron_uses_skip_locked_and_rechecks_quantity(db, mk, monkeypatch):
    """Partiya qulflanganda skip_locked ishlatiladi; ro'yxat olingandan keyin qoldig'i 0 bo'lib qolgan partiya o'tkaziladi."""
    sched = _scheduler(monkeypatch)
    t = _expiry_setup(db, mk)
    from sqlalchemy.orm import Query
    calls = []
    orig = Query.with_for_update

    def spy(self, *a, **kw):
        calls.append(kw)
        return orig(self, *a, **kw)

    monkeypatch.setattr(Query, 'with_for_update', spy)
    # boshqa jarayon allaqachon hisobdan chiqargan deb faraz qilamiz
    t['exp1'].quantity = Decimal('0')
    db.flush()
    asyncio.run(sched.auto_write_off_expired())
    assert any(kw.get('skip_locked') for kw in calls)
    assert _mv(db, t['exp1'].id, 'auto_batch_write_off') == []
    assert _qty(db, t['sut'], t['wh1']) == 20.0


# ─── 9. Telegram ogohlantirishi ───

def test_notify_expiring_products_uses_shared_rule_and_shows_warehouse(db, mk, monkeypatch):
    from app.admin_tg_bot.models import CompanyBot
    sched = _scheduler(monkeypatch)
    t = _expiry_setup(db, mk)
    t['u'].tg_chat_id = '12345'
    db.add(CompanyBot(company_id=t['c'].id, bot_token=f'tok-{next(_seq)}', bot_type='admin',
                      notify_expired_products=True, expired_days_before=15, is_active=True))
    # perishable bo'lmagan, muddati yaqin partiya — xabarda bo'lmasligi kerak
    _batch(db, t['dori'], t['wh1'], 3, lot='D2', expiry=datetime.now() + timedelta(days=3))
    db.flush()

    sent = []

    async def fake_send(token, chat_id, msg, *a, **kw):
        sent.append(msg)
        return True

    monkeypatch.setattr(sched, 'send_tg_msg_async', fake_send)
    asyncio.run(sched.notify_expiring_products())
    assert len(sent) == 1
    assert 'Sut' in sent[0] and 'Ombor: Chilonzor' in sent[0]
    assert 'Dori' not in sent[0]
