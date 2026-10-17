"""T0.32 — Transfer yaxlitligi: partiya, manfiy qoldiq, validatsiya.

Qamrov: qator validatsiyasi (422), virtual/xizmat mahsulot (400), bekor qilingan
transferni tahrirlash (400), manzilda qoldiq yetmasa cancel/DELETE/PUT 400 va hech
narsa o'zgarmaydi, partiyalar (Batch) ko'chishi va qaytishi, tungi/qo'lda hisobdan
chiqarish qoldiqni manfiyga tushirmasligi, TRANSFER_OUT/IN harakatlarida warehouse_id,
ikki korxona izolyatsiyasi.
"""
import asyncio
import itertools
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.batch import Batch
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product, ProductConversion
from app.models.transfer import StockTransfer, StockTransferBatch, StockTransferItem, TransferStatus
from app.models.user import UserRole

_seq = itertools.count(1)


# ─── yordamchilar ───

def _product(db, company, name=None, product_type='simple'):
    n = next(_seq)
    p = Product(name=name or f'Mahsulot {n}', sku=f'SKU-T032-{n}', barcode=f'BC-T032-{n}',
                company_id=company.id, cost_price=0, sale_price=0, product_type=product_type)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty, variant_id=None):
    s = StockLevel(product_id=product.id, warehouse_id=warehouse.id, variant_id=variant_id, quantity=Decimal(qty))
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


def _batch(db, product, warehouse, qty, lot='LOT-1', expiry=None, price='5000'):
    b = Batch(product_id=product.id, warehouse_id=warehouse.id, company_id=product.company_id,
              lot_number=lot, expiry_date=expiry, initial_quantity=Decimal(qty), quantity=Decimal(qty),
              purchase_price=Decimal(price))
    db.add(b)
    db.flush()
    return b


def _moves(db, transfer_id):
    return db.query(StockMovement).filter(
        StockMovement.reference_type == 'stock_transfer', StockMovement.reference_id == transfer_id
    ).order_by(StockMovement.id).all()


def _snapshot(db):
    """Qoldiq, harakat, partiya va transfer holati — o'zgarmaganini solishtirish uchun"""
    levels = sorted((s.product_id, s.warehouse_id, s.variant_id, float(s.quantity)) for s in db.query(StockLevel).all())
    moves = sorted((m.id, m.type.value, float(m.quantity), m.warehouse_id) for m in db.query(StockMovement).all())
    batches = sorted((b.id, b.warehouse_id, float(b.quantity)) for b in db.query(Batch).all())
    links = db.query(StockTransferBatch).count()
    transfers = sorted((t.id, t.status.value) for t in db.query(StockTransfer).all())
    return levels, moves, batches, links, transfers


def _tenant(db, mk):
    """Korxona: Chilonzor (wh1, mahsulot 100 dona) va Yunusobod (wh2) omborlari, admin."""
    c, b, wh1, u = mk.tenant()
    wh2 = mk.warehouse(c, b, name='Yunusobod')
    p = _product(db, c, name='Sut')
    _stock(db, p, wh1, 100)
    return dict(c=c, wh1=wh1, wh2=wh2, p=p, u=u)


def _body(from_wh, to_wh, items):
    return {'from_warehouse_id': from_wh.id, 'to_warehouse_id': to_wh.id, 'items': items}


def _create(client, t, qty=10, product=None):
    p = product or t['p']
    r = client.login(t['u']).post('/api/transfers', json=_body(t['wh1'], t['wh2'], [{'product_id': p.id, 'quantity': qty}]))
    assert r.status_code == 200, r.text
    return r.json()['id']


def _no_negative(db):
    assert all(s.quantity >= 0 for s in db.query(StockLevel).all())


# ─── 1. Qator validatsiyasi (422) ───

def test_create_validation_422_and_no_write(client, db, mk):
    t = _tenant(db, mk)
    c = client.login(t['u'])
    before = _snapshot(db)

    # manfiy miqdor
    r = c.post('/api/transfers', json=_body(t['wh1'], t['wh2'], [{'product_id': t['p'].id, 'quantity': -20}]))
    assert r.status_code == 422, r.text
    # nol miqdor
    r = c.post('/api/transfers', json=_body(t['wh1'], t['wh2'], [{'product_id': t['p'].id, 'quantity': 0}]))
    assert r.status_code == 422, r.text
    # bo'sh ro'yxat
    r = c.post('/api/transfers', json=_body(t['wh1'], t['wh2'], []))
    assert r.status_code == 422, r.text
    # takroriy qator
    r = c.post('/api/transfers', json=_body(t['wh1'], t['wh2'], [
        {'product_id': t['p'].id, 'quantity': 1}, {'product_id': t['p'].id, 'quantity': 2},
    ]))
    assert r.status_code == 422, r.text
    assert 'Takroriy qator' in r.text

    assert _snapshot(db) == before
    assert _qty(db, t['p'], t['wh1']) == 100.0 and _qty(db, t['p'], t['wh2']) is None


def test_update_validation_422(client, db, mk):
    t = _tenant(db, mk)
    tid = _create(client, t, qty=10)
    before = _snapshot(db)
    c = client.login(t['u'])
    r = c.put(f'/api/transfers/{tid}', json=_body(t['wh1'], t['wh2'], [{'product_id': t['p'].id, 'quantity': -5}]))
    assert r.status_code == 422, r.text
    r = c.put(f'/api/transfers/{tid}', json=_body(t['wh1'], t['wh2'], []))
    assert r.status_code == 422, r.text
    assert _snapshot(db) == before


# ─── 2. Virtual / xizmat mahsulot (400) ───

def test_virtual_sell_product_400_and_no_write(client, db, mk):
    t = _tenant(db, mk)
    virt = _product(db, t['c'], name='Dumba', product_type='sell')
    db.add(ProductConversion(sell_product_id=virt.id, source_product_id=t['p'].id, ratio=Decimal('1')))
    db.flush()
    before = _snapshot(db)

    r = client.login(t['u']).post('/api/transfers', json=_body(t['wh1'], t['wh2'], [{'product_id': virt.id, 'quantity': 5}]))
    assert r.status_code == 400, r.text
    assert "ko'chirib bo'lmaydi" in r.json()['detail']
    assert _snapshot(db) == before
    assert db.query(StockLevel).filter(StockLevel.product_id == virt.id).count() == 0
    assert db.query(StockMovement).count() == 0
    assert db.query(StockTransfer).count() == 0

    # Xizmat mahsulot ham
    svc = _product(db, t['c'], name='Yetkazish', product_type='service')
    r = client.login(t['u']).post('/api/transfers', json=_body(t['wh1'], t['wh2'], [{'product_id': svc.id, 'quantity': 1}]))
    assert r.status_code == 400, r.text

    # Maqsad mahsulot virtual bo'lsa ham 400
    r = client.login(t['u']).post('/api/transfers', json=_body(
        t['wh1'], t['wh2'], [{'product_id': t['p'].id, 'quantity': 1, 'target_product_id': virt.id}]
    ))
    assert r.status_code == 400, r.text
    assert _qty(db, t['p'], t['wh1']) == 100.0


# ─── 3. Bekor qilingan transferni tahrirlash (400) ───

def test_update_cancelled_transfer_400(client, db, mk):
    t = _tenant(db, mk)
    tid = _create(client, t, qty=10)
    c = client.login(t['u'])
    assert c.post(f'/api/transfers/{tid}/cancel').status_code == 200
    assert _qty(db, t['p'], t['wh1']) == 100.0 and _qty(db, t['p'], t['wh2']) == 0.0
    before = _snapshot(db)

    r = c.put(f'/api/transfers/{tid}', json=_body(t['wh1'], t['wh2'], [{'product_id': t['p'].id, 'quantity': 10}]))
    assert r.status_code == 400, r.text
    assert r.json()['detail'] == "Bekor qilingan transferni tahrirlab bo'lmaydi"
    assert _snapshot(db) == before
    assert db.get(StockTransfer, tid).status == TransferStatus.cancelled
    assert len(_moves(db, tid)) == 2   # T1.19: asl harakatlar saqlanadi (storno alohida yoziladi)


# ─── 4. Manzilda tovar sotilgan: cancel / DELETE / PUT → 400, qoldiq o'zgarmaydi ───

def test_dest_sold_cancel_delete_put_400_nothing_changes(client, db, mk):
    t = _tenant(db, mk)
    src_batch = _batch(db, t['p'], t['wh1'], 100)
    tid = _create(client, t, qty=10)
    assert _qty(db, t['p'], t['wh1']) == 90.0 and _qty(db, t['p'], t['wh2']) == 10.0

    # Yunusobod 8 tasini sotdi (qoldiq 2)
    s2 = db.query(StockLevel).filter(StockLevel.product_id == t['p'].id, StockLevel.warehouse_id == t['wh2'].id).first()
    s2.quantity = Decimal('2')
    db.flush()
    before = _snapshot(db)
    c = client.login(t['u'])

    r = c.post(f'/api/transfers/{tid}/cancel')
    assert r.status_code == 400, r.text
    assert 'manzil omborida yetarli qoldiq yo\'q' in r.json()['detail']
    assert 'mavjud: 2.000' in r.json()['detail'] and 'kerak: 10.000' in r.json()['detail']
    assert _snapshot(db) == before

    r = c.delete(f'/api/transfers/{tid}')
    assert r.status_code == 400, r.text
    assert _snapshot(db) == before
    assert db.get(StockTransfer, tid) is not None

    r = c.put(f'/api/transfers/{tid}', json=_body(t['wh1'], t['wh2'], [{'product_id': t['p'].id, 'quantity': 5}]))
    assert r.status_code == 400, r.text
    assert _snapshot(db) == before

    db.expire_all()
    assert db.get(StockTransfer, tid).status == TransferStatus.received
    assert _qty(db, t['p'], t['wh2']) == 2.0 and _qty(db, t['p'], t['wh1']) == 90.0
    # Partiyalar ham o'zgarmagan (atomar: xato bo'lsa hech narsa o'zgarmaydi)
    assert float(db.get(Batch, src_batch.id).quantity) == 90.0
    assert db.query(StockTransferBatch).filter(StockTransferBatch.transfer_id == tid).count() == 1
    _no_negative(db)


# ─── 5-6. Partiyalar ko'chadi va qaytadi ───

def test_batch_moves_to_destination(client, db, mk):
    t = _tenant(db, mk)
    exp = datetime(2026, 10, 20)
    src = _batch(db, t['p'], t['wh1'], 100, lot='SUT-20OKT', expiry=exp, price='7500')
    tid = _create(client, t, qty=100)

    db.expire_all()
    assert float(db.get(Batch, src.id).quantity) == 0.0
    mirror = db.query(Batch).filter(Batch.warehouse_id == t['wh2'].id, Batch.product_id == t['p'].id).one()
    assert float(mirror.quantity) == 100.0 and float(mirror.initial_quantity) == 100.0
    assert mirror.lot_number == 'SUT-20OKT' and mirror.expiry_date == exp
    assert float(mirror.purchase_price) == 7500.0 and mirror.company_id == t['c'].id

    link = db.query(StockTransferBatch).filter(StockTransferBatch.transfer_id == tid).one()
    assert link.source_batch_id == src.id and link.dest_batch_id == mirror.id
    assert float(link.quantity) == 100.0 and link.product_id == t['p'].id
    assert _qty(db, t['p'], t['wh1']) == 0.0 and _qty(db, t['p'], t['wh2']) == 100.0


def test_batch_fefo_and_batchless_remainder(client, db, mk):
    """Avval muddati yaqin partiya, keyin keyingisi; partiyasiz qoldiq jim ko'chadi."""
    t = _tenant(db, mk)
    late = _batch(db, t['p'], t['wh1'], 30, lot='LATE', expiry=datetime(2026, 12, 1))
    early = _batch(db, t['p'], t['wh1'], 30, lot='EARLY', expiry=datetime(2026, 10, 20))
    # Qoldiq 100, partiyalar 60 — 40 partiyasiz
    _create(client, t, qty=70)
    db.expire_all()
    assert float(db.get(Batch, early.id).quantity) == 0.0
    assert float(db.get(Batch, late.id).quantity) == 0.0
    mirrors = db.query(Batch).filter(Batch.warehouse_id == t['wh2'].id).order_by(Batch.id).all()
    assert [m.lot_number for m in mirrors] == ['EARLY', 'LATE']
    assert sum(float(m.quantity) for m in mirrors) == 60.0
    assert _qty(db, t['p'], t['wh1']) == 30.0 and _qty(db, t['p'], t['wh2']) == 70.0


def test_cancel_restores_batches_and_removes_links(client, db, mk):
    t = _tenant(db, mk)
    src = _batch(db, t['p'], t['wh1'], 100, lot='L1')
    tid = _create(client, t, qty=40)
    mirror = db.query(Batch).filter(Batch.warehouse_id == t['wh2'].id).one()

    r = client.login(t['u']).post(f'/api/transfers/{tid}/cancel')
    assert r.status_code == 200, r.text
    db.expire_all()
    assert float(db.get(Batch, src.id).quantity) == 100.0
    assert float(db.get(Batch, mirror.id).quantity) == 0.0
    assert db.query(StockTransferBatch).filter(StockTransferBatch.transfer_id == tid).count() == 0
    assert len(_moves(db, tid)) == 2   # T1.19: asl harakatlar saqlanadi (storno alohida yoziladi)
    assert _qty(db, t['p'], t['wh1']) == 100.0 and _qty(db, t['p'], t['wh2']) == 0.0
    assert db.get(StockTransfer, tid).status == TransferStatus.cancelled
    _no_negative(db)


def test_revert_partial_sold_mirror_uses_other_dest_batches(client, db, mk):
    """Ko'zgu partiya qisman sotilgan, manzilda boshqa partiya bor: yetmagan qism undan ayiriladi."""
    t = _tenant(db, mk)
    src = _batch(db, t['p'], t['wh1'], 100, lot='L1')
    other = _batch(db, t['p'], t['wh2'], 50, lot='OTHER')
    _stock(db, t['p'], t['wh2'], 50)
    tid = _create(client, t, qty=40)   # wh2: 90, mirror 40
    mirror = db.query(Batch).filter(Batch.warehouse_id == t['wh2'].id, Batch.lot_number == 'L1').one()
    # 30 tasi ko'zgu partiyadan sotildi (qoldiq 60)
    mirror.quantity = Decimal('10')
    s2 = db.query(StockLevel).filter(StockLevel.product_id == t['p'].id, StockLevel.warehouse_id == t['wh2'].id).first()
    s2.quantity = Decimal('60')
    db.flush()

    r = client.login(t['u']).delete(f'/api/transfers/{tid}')
    assert r.status_code == 200, r.text
    db.expire_all()
    assert float(db.get(Batch, src.id).quantity) == 100.0
    assert float(db.get(Batch, mirror.id).quantity) == 0.0
    assert float(db.get(Batch, other.id).quantity) == 20.0   # 50 - 30 yetmagan qism
    assert _qty(db, t['p'], t['wh2']) == 20.0 and _qty(db, t['p'], t['wh1']) == 100.0
    # T1.19: DELETE — yumshoq o'chirish (transfer saqlanadi, status=cancelled)
    assert db.get(StockTransfer, tid).status == TransferStatus.cancelled
    assert db.query(StockTransferBatch).count() == 0
    _no_negative(db)


def test_update_received_moves_batches_again(client, db, mk):
    t = _tenant(db, mk)
    src = _batch(db, t['p'], t['wh1'], 100, lot='L1')
    tid = _create(client, t, qty=10)
    r = client.login(t['u']).put(f'/api/transfers/{tid}', json=_body(t['wh1'], t['wh2'], [{'product_id': t['p'].id, 'quantity': 25}]))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert float(db.get(Batch, src.id).quantity) == 75.0
    live_mirrors = db.query(Batch).filter(Batch.warehouse_id == t['wh2'].id, Batch.quantity > 0).all()
    assert len(live_mirrors) == 1 and float(live_mirrors[0].quantity) == 25.0
    assert db.query(StockTransferBatch).filter(StockTransferBatch.transfer_id == tid).count() == 1
    assert _qty(db, t['p'], t['wh1']) == 75.0 and _qty(db, t['p'], t['wh2']) == 25.0
    assert db.get(StockTransfer, tid).status == TransferStatus.received


# ─── pending: tahrir qoldiqni ko'chirmaydi, confirm bir marta ko'chiradi ───

def test_update_pending_no_stock_change_then_confirm_once(client, db, mk):
    t = _tenant(db, mk)
    tp = StockTransfer(number=f'TR-T032-{next(_seq)}', from_warehouse_id=t['wh1'].id, to_warehouse_id=t['wh2'].id,
                       created_by=t['u'].id, status=TransferStatus.pending)
    db.add(tp)
    db.flush()
    db.add(StockTransferItem(transfer_id=tp.id, product_id=t['p'].id, quantity=Decimal(10)))
    db.flush()
    c = client.login(t['u'])

    r = c.put(f'/api/transfers/{tp.id}', json=_body(t['wh1'], t['wh2'], [{'product_id': t['p'].id, 'quantity': 30}]))
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'pending' and float(r.json()['items'][0]['quantity']) == 30.0
    assert _qty(db, t['p'], t['wh1']) == 100.0 and _qty(db, t['p'], t['wh2']) is None
    assert len(_moves(db, tp.id)) == 0

    assert c.post(f'/api/transfers/{tp.id}/send').status_code == 200  # T4.1: pending avval yuboriladi
    r = c.post(f'/api/transfers/{tp.id}/confirm')
    assert r.status_code == 200, r.text
    assert _qty(db, t['p'], t['wh1']) == 70.0 and _qty(db, t['p'], t['wh2']) == 30.0
    ms = _moves(db, tp.id)
    assert len(ms) == 2 and all(m.warehouse_id is not None for m in ms)


# ─── 7. Muddati o'tgan partiyani hisobdan chiqarish — qoldiq manfiy bo'lmaydi ───

def _patch_scheduler_session(monkeypatch):
    """scheduler `SessionLocal` ni nom bo'yicha import qiladi — test ulanishiga yo'naltiramiz"""
    import app.database as app_database
    import app.services.scheduler as scheduler
    monkeypatch.setattr(scheduler, 'SessionLocal', app_database.SessionLocal)
    return scheduler


def _make_perishable(db, t):
    from app.models.category import Category
    cat = Category(name='Tez buziladigan', company_id=t['c'].id, is_perishable=True)
    db.add(cat)
    db.flush()
    t['p'].category_id = cat.id
    db.flush()


def test_auto_write_off_expired_limited_by_stock(db, mk, monkeypatch):
    auto_write_off_expired = _patch_scheduler_session(monkeypatch).auto_write_off_expired

    t = _tenant(db, mk)
    _make_perishable(db, t)   # T1.8: faqat tez buziladigan kategoriya avtomatik hisobdan chiqariladi
    # Ombor qoldig'i 100 → 70 tasi ko'chirilgan deylik (qoldiq 30), partiya hali 100 (eski transfer)
    s1 = db.query(StockLevel).filter(StockLevel.product_id == t['p'].id, StockLevel.warehouse_id == t['wh1'].id).first()
    s1.quantity = Decimal('30')
    expired = _batch(db, t['p'], t['wh1'], 100, lot='OLD', expiry=datetime.now() - timedelta(days=5))
    db.flush()

    asyncio.run(auto_write_off_expired())

    db.expire_all()
    assert _qty(db, t['p'], t['wh1']) == 0.0
    assert float(db.get(Batch, expired.id).quantity) == 0.0
    m = db.query(StockMovement).filter(
        StockMovement.reference_type == 'auto_batch_write_off', StockMovement.reference_id == expired.id
    ).one()
    assert m.type == MovementType.EXPIRED and float(m.quantity) == 30.0
    assert m.warehouse_id == t['wh1'].id
    _no_negative(db)


def test_auto_write_off_expired_zero_stock_no_movement(db, mk, monkeypatch):
    auto_write_off_expired = _patch_scheduler_session(monkeypatch).auto_write_off_expired

    t = _tenant(db, mk)
    _make_perishable(db, t)   # T1.8
    s1 = db.query(StockLevel).filter(StockLevel.product_id == t['p'].id, StockLevel.warehouse_id == t['wh1'].id).first()
    s1.quantity = Decimal('0')
    expired = _batch(db, t['p'], t['wh1'], 40, lot='OLD', expiry=datetime.now() - timedelta(days=1))
    db.flush()

    asyncio.run(auto_write_off_expired())

    db.expire_all()
    assert _qty(db, t['p'], t['wh1']) == 0.0
    assert float(db.get(Batch, expired.id).quantity) == 0.0   # fantom qism nolga tushdi
    assert db.query(StockMovement).filter(StockMovement.reference_id == expired.id).count() == 0
    _no_negative(db)


def test_manual_write_off_expired_limited_and_400_when_zero(client, db, mk):
    t = _tenant(db, mk)
    s1 = db.query(StockLevel).filter(StockLevel.product_id == t['p'].id, StockLevel.warehouse_id == t['wh1'].id).first()
    s1.quantity = Decimal('30')
    b = _batch(db, t['p'], t['wh1'], 100, lot='OLD', expiry=datetime.now() - timedelta(days=5))
    db.flush()
    c = client.login(t['u'])

    r = c.post('/api/inventory/write-off-expired', json={'batch_id': b.id})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert _qty(db, t['p'], t['wh1']) == 0.0 and float(db.get(Batch, b.id).quantity) == 0.0
    m = db.query(StockMovement).filter(StockMovement.reference_type == 'batch_write_off', StockMovement.reference_id == b.id).one()
    assert float(m.quantity) == 30.0 and m.warehouse_id == t['wh1'].id

    # Qoldiq 0 — 400
    b2 = _batch(db, t['p'], t['wh1'], 10, lot='OLD2', expiry=datetime.now() - timedelta(days=5))
    db.flush()
    r = c.post('/api/inventory/write-off-expired', json={'batch_id': b2.id})
    assert r.status_code == 400, r.text
    assert r.json()['detail'] == "Omborda bu partiya uchun qoldiq yo'q"
    db.expire_all()
    assert float(db.get(Batch, b2.id).quantity) == 10.0
    _no_negative(db)


# ─── 8. TRANSFER_OUT/IN harakatlarida warehouse_id ───

def test_transfer_movements_have_warehouse_id(client, db, mk):
    t = _tenant(db, mk)
    tid = _create(client, t, qty=10)
    ms = _moves(db, tid)
    assert {m.type for m in ms} == {MovementType.TRANSFER_OUT, MovementType.TRANSFER_IN}
    for m in ms:
        if m.type == MovementType.TRANSFER_OUT:
            assert m.warehouse_id == t['wh1'].id
        else:
            assert m.warehouse_id == t['wh2'].id

    # Tahrirdan keyin ham (harakatlar qayta yaratiladi): manzil — yangi ombor wh3
    wh3 = mk.warehouse(t['c'], None, name='Sergeli')
    r = client.login(t['u']).put(f'/api/transfers/{tid}', json=_body(t['wh1'], wh3, [{'product_id': t['p'].id, 'quantity': 5}]))
    assert r.status_code == 200, r.text
    # T1.19: tahrirda eski harakatlar saqlanadi (+ storno) — faqat yangi (oxirgi 2 ta) harakatlar tekshiriladi
    ms = _moves(db, tid)[-2:]
    assert len(ms) == 2
    for m in ms:
        assert m.warehouse_id == (t['wh1'].id if m.type == MovementType.TRANSFER_OUT else wh3.id)
    assert _qty(db, t['p'], t['wh1']) == 95.0 and _qty(db, t['p'], t['wh2']) == 0.0 and _qty(db, t['p'], wh3) == 5.0
    _no_negative(db)


# ─── Ikki korxona izolyatsiyasi ───

def test_isolation_two_companies(client, db, mk):
    a = _tenant(db, mk)
    b = _tenant(db, mk)
    bb = _batch(db, b['p'], b['wh1'], 100, lot='B-LOT')
    tid_b = _create(client, b, qty=10)
    before = _snapshot(db)

    ca = client.login(a['u'])
    # A foydalanuvchisi B transferini bekor qila olmaydi / tahrirlay olmaydi / o'chira olmaydi
    assert ca.post(f'/api/transfers/{tid_b}/cancel').status_code == 404
    assert ca.put(f'/api/transfers/{tid_b}', json=_body(a['wh1'], a['wh2'], [{'product_id': a['p'].id, 'quantity': 1}])).status_code == 404
    assert ca.delete(f'/api/transfers/{tid_b}').status_code == 404
    # A B mahsulotini o'z omborlari orasida ko'chira olmaydi
    assert ca.post('/api/transfers', json=_body(a['wh1'], a['wh2'], [{'product_id': b['p'].id, 'quantity': 1}])).status_code == 404
    # A B partiyasini hisobdan chiqara olmaydi
    assert ca.post('/api/inventory/write-off-expired', json={'batch_id': bb.id}).status_code == 404
    assert _snapshot(db) == before

    # Ijobiy yo'l: A o'z transferini yaratadi, B partiyalari/qoldiqlari o'zgarmaydi
    _batch(db, a['p'], a['wh1'], 50, lot='A-LOT')
    tid_a = _create(client, a, qty=20)
    assert ca.post(f'/api/transfers/{tid_a}/cancel').status_code == 200
    db.expire_all()
    assert float(db.get(Batch, bb.id).quantity) == 90.0
    assert _qty(db, b['p'], b['wh1']) == 90.0 and _qty(db, b['p'], b['wh2']) == 10.0
    assert _qty(db, a['p'], a['wh1']) == 100.0
    assert db.query(StockTransferBatch).filter(StockTransferBatch.transfer_id == tid_b).count() == 1
