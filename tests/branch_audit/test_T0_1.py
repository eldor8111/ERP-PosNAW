"""T0.1 — Transfer servisi va routerida korxona izolyatsiyasi.

Ikki korxona (A va B), har birida ombor(lar), mahsulot va admin foydalanuvchi.
A foydalanuvchisi B resurslari bilan create/confirm/update/delete/cancel qilsa 404
oladi va B qoldiqlari (StockLevel/StockMovement) hamda stock_transfers o'zgarmaydi.
O'z korxonasi ichida hammasi avvalgidek ishlaydi; super_admin hamma korxonada ishlaydi.
"""
import itertools
from decimal import Decimal

from app.models.inventory import StockLevel, StockMovement
from app.models.product import Product
from app.models.transfer import StockTransfer, StockTransferItem, TransferStatus
from app.models.user import UserRole

_pseq = itertools.count(1)


# ─── yordamchilar ───

def _product(db, company, name=None):
    n = next(_pseq)
    p = Product(name=name or f'Mahsulot {n}', sku=f'SKU-T01-{n}', barcode=f'BC-T01-{n}',
                company_id=company.id, cost_price=0, sale_price=0)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty):
    s = StockLevel(product_id=product.id, warehouse_id=warehouse.id, variant_id=None, quantity=Decimal(qty))
    db.add(s)
    db.flush()
    return s


def _qty(db, product, warehouse):
    s = db.query(StockLevel).filter(
        StockLevel.product_id == product.id,
        StockLevel.warehouse_id == warehouse.id,
        StockLevel.variant_id.is_(None),
    ).first()
    return float(s.quantity) if s else None


def _pending_transfer(db, from_wh, to_wh, product, qty, user):
    """To'g'ridan-to'g'ri DB'da pending transfer (confirm testlari uchun)"""
    t = StockTransfer(number=f'TR-TEST-{next(_pseq)}', from_warehouse_id=from_wh.id,
                      to_warehouse_id=to_wh.id, created_by=user.id, status=TransferStatus.pending)
    db.add(t)
    db.flush()
    db.add(StockTransferItem(transfer_id=t.id, product_id=product.id, quantity=Decimal(qty)))
    db.flush()
    return t


def _snapshot(db):
    """Qoldiq va harakatlar holati — o'zgarmaganini solishtirish uchun"""
    levels = sorted((s.product_id, s.warehouse_id, float(s.quantity)) for s in db.query(StockLevel).all())
    moves = db.query(StockMovement).count()
    transfers = db.query(StockTransfer).count()
    return levels, moves, transfers


def _two_tenants(db, mk):
    """A: ombor1, ombor2, mahsulot (ombor1 da 100). B: ombor1, ombor2, mahsulot (ombor1 da 100)."""
    ca, ba, wa1, ua = mk.tenant()
    wa2 = mk.warehouse(ca, ba)
    pa = _product(db, ca)
    _stock(db, pa, wa1, 100)

    cb, bb, wb1, ub = mk.tenant()
    wb2 = mk.warehouse(cb, bb)
    pb = _product(db, cb)
    _stock(db, pb, wb1, 100)
    return dict(ca=ca, wa1=wa1, wa2=wa2, pa=pa, ua=ua, cb=cb, wb1=wb1, wb2=wb2, pb=pb, ub=ub)


def _create_body(from_wh, to_wh, product, qty=10, target_product=None):
    item = {'product_id': product.id, 'quantity': qty}
    if target_product is not None:
        item['target_product_id'] = target_product.id
    return {'from_warehouse_id': from_wh.id, 'to_warehouse_id': to_wh.id, 'items': [item]}


# ─── 1. create: begona ombor ───

def test_create_foreign_from_warehouse_404_and_no_write(client, db, mk):
    t = _two_tenants(db, mk)
    before = _snapshot(db)
    r = client.login(t['ua']).post('/api/transfers', json=_create_body(t['wb1'], t['wa1'], t['pb']))
    assert r.status_code == 404, r.text
    assert 'Ombor' in r.json()['detail']
    assert _snapshot(db) == before
    assert _qty(db, t['pb'], t['wb1']) == 100.0


def test_create_foreign_to_warehouse_404_and_no_write(client, db, mk):
    t = _two_tenants(db, mk)
    before = _snapshot(db)
    r = client.login(t['ua']).post('/api/transfers', json=_create_body(t['wa1'], t['wb1'], t['pa']))
    assert r.status_code == 404, r.text
    assert 'Ombor' in r.json()['detail']
    assert _snapshot(db) == before
    assert _qty(db, t['pa'], t['wa1']) == 100.0
    assert _qty(db, t['pa'], t['wb1']) is None


# ─── 2. create: begona mahsulot ───

def test_create_foreign_product_404_and_no_write(client, db, mk):
    t = _two_tenants(db, mk)
    before = _snapshot(db)
    r = client.login(t['ua']).post('/api/transfers', json=_create_body(t['wa1'], t['wa2'], t['pb']))
    assert r.status_code == 404, r.text
    assert 'Mahsulot' in r.json()['detail']
    assert _snapshot(db) == before


def test_create_foreign_target_product_404_and_no_write(client, db, mk):
    t = _two_tenants(db, mk)
    before = _snapshot(db)
    r = client.login(t['ua']).post(
        '/api/transfers', json=_create_body(t['wa1'], t['wa2'], t['pa'], target_product=t['pb'])
    )
    assert r.status_code == 404, r.text
    assert 'Maqsad mahsulot' in r.json()['detail']
    assert _snapshot(db) == before


# ─── 3. confirm / PUT / DELETE / cancel: begona transfer ───

def test_confirm_foreign_transfer_404_and_no_write(client, db, mk):
    t = _two_tenants(db, mk)
    tb = _pending_transfer(db, t['wb1'], t['wb2'], t['pb'], 10, t['ub'])
    before = _snapshot(db)
    r = client.login(t['ua']).post(f'/api/transfers/{tb.id}/confirm')
    assert r.status_code == 404, r.text
    assert r.json()['detail'] == 'Transfer topilmadi'
    assert _snapshot(db) == before
    db.refresh(tb)
    assert tb.status == TransferStatus.pending


def test_update_foreign_transfer_404_and_no_write(client, db, mk):
    t = _two_tenants(db, mk)
    # B o'z transferini yaratadi (auto-confirm: wb1 100→90, wb2 0→10)
    rb = client.login(t['ub']).post('/api/transfers', json=_create_body(t['wb1'], t['wb2'], t['pb']))
    assert rb.status_code == 200, rb.text
    tb_id = rb.json()['id']
    before = _snapshot(db)

    # A o'z omborlari/mahsuloti bilan B transferini tahrirlamoqchi
    r = client.login(t['ua']).put(f'/api/transfers/{tb_id}', json=_create_body(t['wa1'], t['wa2'], t['pa'], qty=5))
    assert r.status_code == 404, r.text
    assert _snapshot(db) == before
    assert _qty(db, t['pb'], t['wb1']) == 90.0 and _qty(db, t['pb'], t['wb2']) == 10.0


def test_update_own_transfer_with_foreign_warehouse_or_product_404(client, db, mk):
    t = _two_tenants(db, mk)
    ra = client.login(t['ua']).post('/api/transfers', json=_create_body(t['wa1'], t['wa2'], t['pa']))
    assert ra.status_code == 200, ra.text
    ta_id = ra.json()['id']
    before = _snapshot(db)

    # Begona ombor
    r = client.login(t['ua']).put(f'/api/transfers/{ta_id}', json=_create_body(t['wa1'], t['wb2'], t['pa']))
    assert r.status_code == 404 and 'Ombor' in r.json()['detail'], r.text
    assert _snapshot(db) == before
    # Begona mahsulot — revert'dan oldin tekshiriladi, qoldiq o'zgarmaydi
    r = client.login(t['ua']).put(f'/api/transfers/{ta_id}', json=_create_body(t['wa1'], t['wa2'], t['pb']))
    assert r.status_code == 404 and 'Mahsulot' in r.json()['detail'], r.text
    assert _snapshot(db) == before


def test_delete_foreign_transfer_404_and_no_write(client, db, mk):
    t = _two_tenants(db, mk)
    rb = client.login(t['ub']).post('/api/transfers', json=_create_body(t['wb1'], t['wb2'], t['pb']))
    assert rb.status_code == 200, rb.text
    tb_id = rb.json()['id']
    before = _snapshot(db)

    r = client.login(t['ua']).delete(f'/api/transfers/{tb_id}')
    assert r.status_code == 404, r.text
    assert _snapshot(db) == before
    assert db.query(StockTransfer).filter(StockTransfer.id == tb_id).first() is not None


def test_cancel_foreign_transfer_404_and_no_write(client, db, mk):
    t = _two_tenants(db, mk)
    rb = client.login(t['ub']).post('/api/transfers', json=_create_body(t['wb1'], t['wb2'], t['pb']))
    assert rb.status_code == 200, rb.text
    tb_id = rb.json()['id']
    before = _snapshot(db)

    r = client.login(t['ua']).post(f'/api/transfers/{tb_id}/cancel')
    assert r.status_code == 404, r.text
    assert _snapshot(db) == before
    assert db.get(StockTransfer, tb_id).status == TransferStatus.received


def test_cancel_transfer_with_foreign_to_warehouse_404(client, db, mk):
    """from = A ombori, to = B ombori (eski zararlangan yozuv) — A cancel qila olmaydi"""
    t = _two_tenants(db, mk)
    mixed = _pending_transfer(db, t['wa1'], t['wb1'], t['pa'], 10, t['ua'])
    before = _snapshot(db)
    r = client.login(t['ua']).post(f'/api/transfers/{mixed.id}/cancel')
    assert r.status_code == 404, r.text
    assert _snapshot(db) == before
    db.refresh(mixed)
    assert mixed.status == TransferStatus.pending
    # GET ham ko'rsatmaydi (to_warehouse begona)
    assert client.login(t['ua']).get(f'/api/transfers/{mixed.id}').status_code == 404


# ─── 4. ijobiy yo'l: o'z korxonasi va super_admin ───

def test_own_company_full_flow(client, db, mk):
    t = _two_tenants(db, mk)
    c = client.login(t['ua'])

    # create (auto-confirm)
    r = c.post('/api/transfers', json=_create_body(t['wa1'], t['wa2'], t['pa'], qty=10))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['status'] == 'received' and body['from_warehouse_id'] == t['wa1'].id
    tid = body['id']
    assert _qty(db, t['pa'], t['wa1']) == 90.0 and _qty(db, t['pa'], t['wa2']) == 10.0
    # B ga ta'sir yo'q
    assert _qty(db, t['pb'], t['wb1']) == 100.0

    # GET
    assert c.get(f'/api/transfers/{tid}').status_code == 200

    # update: 10 → 25
    r = c.put(f'/api/transfers/{tid}', json=_create_body(t['wa1'], t['wa2'], t['pa'], qty=25))
    assert r.status_code == 200, r.text
    assert float(r.json()['items'][0]['quantity']) == 25.0
    assert _qty(db, t['pa'], t['wa1']) == 75.0 and _qty(db, t['pa'], t['wa2']) == 25.0

    # cancel: qoldiqlar qaytadi
    r = c.post(f'/api/transfers/{tid}/cancel')
    assert r.status_code == 200, r.text
    assert _qty(db, t['pa'], t['wa1']) == 100.0 and _qty(db, t['pa'], t['wa2']) == 0.0
    assert db.get(StockTransfer, tid).status == TransferStatus.cancelled

    # delete
    r = c.delete(f'/api/transfers/{tid}')
    assert r.status_code == 200, r.text
    # T1.19: DELETE — yumshoq o'chirish: transfer saqlanadi (status=cancelled)
    assert db.get(StockTransfer, tid).status == TransferStatus.cancelled


def test_own_pending_confirm_and_delete_reverts(client, db, mk):
    t = _two_tenants(db, mk)
    c = client.login(t['ua'])
    tp = _pending_transfer(db, t['wa1'], t['wa2'], t['pa'], 30, t['ua'])

    assert c.post(f'/api/transfers/{tp.id}/send').status_code == 200  # T4.1: pending avval yuboriladi
    r = c.post(f'/api/transfers/{tp.id}/confirm')
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'received'
    assert _qty(db, t['pa'], t['wa1']) == 70.0 and _qty(db, t['pa'], t['wa2']) == 30.0

    r = c.post(f'/api/transfers/{tp.id}/cancel')  # T4.1: ikki bosqichli hujjat o'chirilmaydi — bekor qilinadi
    assert r.status_code == 200, r.text
    assert _qty(db, t['pa'], t['wa1']) == 100.0 and _qty(db, t['pa'], t['wa2']) == 0.0
    # T1.19: asl harakatlar o'chirilmaydi — storno harakatlar yoziladi (qoldiq qaytgan)
    assert db.query(StockMovement).filter(
        StockMovement.reference_type == 'stock_transfer', StockMovement.reference_id == tp.id
    ).count() == 2
    assert db.query(StockMovement).filter(
        StockMovement.reference_type == 'stock_transfer_revert', StockMovement.reference_id == tp.id
    ).count() == 2


def test_same_warehouse_still_400(client, db, mk):
    t = _two_tenants(db, mk)
    r = client.login(t['ua']).post('/api/transfers', json=_create_body(t['wa1'], t['wa1'], t['pa']))
    assert r.status_code == 400, r.text


def test_super_admin_works_across_companies(client, db, mk):
    t = _two_tenants(db, mk)
    sa = mk.user(None, role=UserRole.super_admin)
    c = client.login(sa)

    # B korxonasida yaratish
    r = c.post('/api/transfers', json=_create_body(t['wb1'], t['wb2'], t['pb'], qty=10))
    assert r.status_code == 200, r.text
    tid = r.json()['id']
    assert _qty(db, t['pb'], t['wb1']) == 90.0

    # A korxonasidagi pending transferni confirm
    tp = _pending_transfer(db, t['wa1'], t['wa2'], t['pa'], 5, t['ua'])
    assert c.post(f'/api/transfers/{tp.id}/send').status_code == 200  # T4.1: pending avval yuboriladi
    assert c.post(f'/api/transfers/{tp.id}/confirm').status_code == 200
    assert _qty(db, t['pa'], t['wa1']) == 95.0

    # B transferini tahrirlash, bekor qilish va o'chirish
    assert c.put(f'/api/transfers/{tid}', json=_create_body(t['wb1'], t['wb2'], t['pb'], qty=20)).status_code == 200
    assert _qty(db, t['pb'], t['wb1']) == 80.0
    assert c.post(f'/api/transfers/{tid}/cancel').status_code == 200
    assert _qty(db, t['pb'], t['wb1']) == 100.0
    assert c.delete(f'/api/transfers/{tid}').status_code == 200
