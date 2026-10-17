"""T0.33 — Inventarizatsiya yaxlitligi: delta bilan yakunlash, bir omborda bitta ochiq revizya."""
import importlib.util
import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.inventory_count import CountStatus, InventoryCount, InventoryCountItem
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import UserRole

_n = [0]
D = Decimal


def _product(db, company):
    _n[0] += 1
    p = Product(sku=f'T33SKU{_n[0]}', barcode=f'T33BC{_n[0]:08d}', name=f'Tovar {_n[0]}',
                company_id=company.id, product_type='simple')
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty, variant=None):
    s = StockLevel(product_id=product.id, variant_id=variant.id if variant else None,
                   warehouse_id=wh.id, quantity=D(qty))
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def one(db, mk):
    """Bitta korxona: ombor, admin, mahsulot (qoldiq 50)."""
    c, b, w, u = mk.tenant()
    p = _product(db, c)
    s = _stock(db, p, w, '50')
    return dict(c=c, w=w, u=u, p=p, s=s)


def _create(client, one):
    r = client.login(one['u']).post('/api/inventory-counts', json={'warehouse_id': one['w'].id})
    assert r.status_code == 200, r.text
    return r.json()['id']


def _count_and_start(client, one):
    cid = _create(client, one)
    r = client.login(one['u']).post(f'/api/inventory-counts/{cid}/start')
    assert r.status_code == 200, r.text
    return cid


def _count(client, one, cid, qty, reason=None):
    r = client.login(one['u']).post(f'/api/inventory-counts/{cid}/items', json=[
        {'product_id': one['p'].id, 'counted_qty': qty, 'variance_reason': reason}])
    return r


def _item(db, cid):
    return db.query(InventoryCountItem).filter_by(count_id=cid).one()


def _set_stock(db, one, qty):
    one['s'].quantity = D(qty)
    db.flush()


# ---------- 1-2. delta bilan yakunlash ----------

def test_finalize_applies_delta_after_sale(db, client, one):
    cid = _count_and_start(client, one)
    assert _count(client, one, cid, 48).status_code == 200
    it = _item(db, cid)
    assert it.system_qty == D('50') and it.variance == D('-2') and it.counted_at is not None

    _set_stock(db, one, 30)  # 20 dona sotildi
    r = client.login(one['u']).post(f'/api/inventory-counts/{cid}/finalize')
    assert r.status_code == 200, r.text

    db.refresh(one['s'])
    assert one['s'].quantity == D('28')  # 30 + (48 - 50), 48 emas
    mov = db.query(StockMovement).filter_by(reference_type='revision', reference_id=cid).one()
    assert (mov.qty_before, mov.qty_after, mov.quantity) == (D('30'), D('28'), D('2'))
    assert mov.warehouse_id == one['w'].id
    assert mov.type == MovementType.ADJUST
    assert db.query(InventoryCount).get(cid).status == CountStatus.completed


def test_finalize_keeps_receipt_after_count(db, client, one):
    cid = _count_and_start(client, one)
    _count(client, one, cid, 48)
    _set_stock(db, one, 60)  # +10 kirim
    assert client.login(one['u']).post(f'/api/inventory-counts/{cid}/finalize').status_code == 200
    db.refresh(one['s'])
    assert one['s'].quantity == D('58')  # 60 + (48 - 50)


def test_finalize_zero_delta_no_movement(db, client, one):
    cid = _count_and_start(client, one)
    _count(client, one, cid, 50)
    _set_stock(db, one, 44)
    assert client.login(one['u']).post(f'/api/inventory-counts/{cid}/finalize').status_code == 200
    db.refresh(one['s'])
    assert one['s'].quantity == D('44')
    assert db.query(StockMovement).filter_by(reference_type='revision', reference_id=cid).count() == 0


def test_finalize_negative_result_written_with_note(db, client, one):
    cid = _count_and_start(client, one)
    _count(client, one, cid, 10)  # delta -40
    _set_stock(db, one, 5)        # oradagi sotuvlar
    assert client.login(one['u']).post(f'/api/inventory-counts/{cid}/finalize').status_code == 200
    db.refresh(one['s'])
    assert one['s'].quantity == D('-35')
    mov = db.query(StockMovement).filter_by(reference_type='revision', reference_id=cid).one()
    assert mov.qty_after == D('-35') and mov.quantity == D('40')
    assert 'manfiy' in mov.reason


def test_finalize_creates_stock_row_when_missing(db, client, mk):
    c, b, w, u = mk.tenant()
    p = _product(db, c)  # qoldiq yozuvi yo'q
    one = dict(c=c, w=w, u=u, p=p)
    cid = _count_and_start(client, one)
    assert _count(client, one, cid, 7).status_code == 200
    assert client.login(u).post(f'/api/inventory-counts/{cid}/finalize').status_code == 200
    st = db.query(StockLevel).filter_by(product_id=p.id, warehouse_id=w.id).one()
    assert st.quantity == D('7')


# ---------- system_qty yangilanishi ----------

def test_start_refreshes_system_qty(db, client, one):
    cid = _create(client, one)
    assert _item(db, cid).system_qty == D('50')
    _set_stock(db, one, 42)  # draft vaqtida qoldiq o'zgardi
    client.login(one['u']).post(f'/api/inventory-counts/{cid}/start')
    db.refresh(_item(db, cid))
    assert _item(db, cid).system_qty == D('42')


def test_changed_count_refreshes_system_qty_unchanged_does_not(db, client, one):
    cid = _count_and_start(client, one)
    _count(client, one, cid, 48)
    it = _item(db, cid)
    first_at = it.counted_at
    _set_stock(db, one, 30)

    # Qiymat o'zgarmadi — faqat sabab yoziladi, system_qty yangilanmaydi
    _count(client, one, cid, 48, reason='izoh')
    db.refresh(it)
    assert it.system_qty == D('50') and it.variance == D('-2')
    assert it.variance_reason == 'izoh' and it.counted_at == first_at

    # Qiymat o'zgardi — system_qty joriy qoldiqqa yangilanadi
    _count(client, one, cid, 29)
    db.refresh(it)
    assert it.system_qty == D('30') and it.variance == D('-1')


def test_new_item_row_uses_current_stock(db, client, mk):
    c, b, w, u = mk.tenant()
    p1 = _product(db, c)
    cid_one = dict(c=c, w=w, u=u, p=p1)
    cid = _create(client, cid_one)  # p1 sanoq ro'yxatida
    client.login(u).post(f'/api/inventory-counts/{cid}/start')
    p2 = _product(db, c)
    _stock(db, p2, w, '9')  # revizya ochilgandan keyin paydo bo'lgan tovar
    r = client.login(u).post(f'/api/inventory-counts/{cid}/items',
                             json=[{'product_id': p2.id, 'counted_qty': 8}])
    assert r.status_code == 200, r.text
    it = db.query(InventoryCountItem).filter_by(count_id=cid, product_id=p2.id).one()
    assert (it.system_qty, it.variance) == (D('9'), D('-1'))


# ---------- 3. bir omborda bitta ochiq revizya ----------

def test_second_open_count_same_warehouse_409(db, client, one):
    cid = _create(client, one)
    num = db.query(InventoryCount).get(cid).number
    r = client.login(one['u']).post('/api/inventory-counts', json={'warehouse_id': one['w'].id})
    assert r.status_code == 409
    assert r.json()['detail'] == f"Bu omborda ochiq inventarizatsiya bor: {num} (ID {cid})"
    assert db.query(InventoryCount).count() == 1

    # in_progress holatida ham bloklanadi
    client.login(one['u']).post(f'/api/inventory-counts/{cid}/start')
    r = client.login(one['u']).post('/api/inventory-counts', json={'warehouse_id': one['w'].id})
    assert r.status_code == 409


def test_other_warehouse_and_after_finalize_allowed(db, client, mk, one):
    w2 = mk.warehouse(one['c'])
    cid = _create(client, one)
    r = client.login(one['u']).post('/api/inventory-counts', json={'warehouse_id': w2.id})
    assert r.status_code == 200, r.text  # boshqa ombor — mumkin

    client.login(one['u']).post(f'/api/inventory-counts/{cid}/start')
    assert client.login(one['u']).post(f'/api/inventory-counts/{cid}/finalize').status_code == 200
    r = client.login(one['u']).post('/api/inventory-counts', json={'warehouse_id': one['w'].id})
    assert r.status_code == 200, r.text  # yakunlangach yangisi ochiladi


def test_db_index_blocks_parallel_open_counts(db, one):
    """Parallel so'rov holati: servis tekshiruvidan o'tib ketsa ham indeks to'sadi."""
    def mkc(num, status):
        return InventoryCount(number=num, warehouse_id=one['w'].id, created_by=one['u'].id, status=status)

    db.add(mkc('IDX1', CountStatus.draft))
    db.flush()
    db.add(mkc('IDX2', CountStatus.completed))  # yopilgan revizyalar cheklanmaydi
    db.add(mkc('IDX3', CountStatus.cancelled))
    db.flush()
    sp = db.begin_nested()
    db.add(mkc('IDX4', CountStatus.in_progress))
    with pytest.raises(IntegrityError):
        db.flush()
    sp.rollback()


# ---------- 4. revert ----------

def test_revert_blocked_when_other_open_count(db, client, one):
    cid = _count_and_start(client, one)
    _count(client, one, cid, 48)
    assert client.login(one['u']).post(f'/api/inventory-counts/{cid}/finalize').status_code == 200
    other = _create(client, one)  # yakunlangach yangi ochiq revizya

    r = client.login(one['u']).post(f'/api/inventory-counts/{cid}/revert')
    assert r.status_code == 409
    assert f'ID {other}' in r.json()['detail']
    assert db.query(InventoryCount).get(cid).status == CountStatus.completed
    db.refresh(one['s'])
    assert one['s'].quantity == D('48')  # qoldiq qaytarilmadi


def test_revert_restores_delta_when_no_other_open(db, client, one):
    cid = _count_and_start(client, one)
    _count(client, one, cid, 48)
    _set_stock(db, one, 30)
    client.login(one['u']).post(f'/api/inventory-counts/{cid}/finalize')
    db.refresh(one['s'])
    assert one['s'].quantity == D('28')
    r = client.login(one['u']).post(f'/api/inventory-counts/{cid}/revert')
    assert r.status_code == 200, r.text
    db.refresh(one['s'])
    assert one['s'].quantity == D('30')
    assert r.json()['status'] == 'in_progress'


# ---------- 5. counted_qty validatsiyasi ----------

@pytest.mark.parametrize('qty', [-5, -0.001, 1000000000])
def test_counted_qty_out_of_range_422(db, client, one, qty):
    cid = _count_and_start(client, one)
    r = _count(client, one, cid, qty)
    assert r.status_code == 422
    assert _item(db, cid).counted_qty is None


def test_counted_qty_zero_ok(db, client, one):
    cid = _count_and_start(client, one)
    assert _count(client, one, cid, 0).status_code == 200
    assert _item(db, cid).variance == D('-50')


# ---------- 6. ikki marta yakunlash ----------

def test_double_finalize_applies_delta_once(db, client, one):
    cid = _count_and_start(client, one)
    _count(client, one, cid, 48)
    cl = client.login(one['u'])
    assert cl.post(f'/api/inventory-counts/{cid}/finalize').status_code == 200
    r = cl.post(f'/api/inventory-counts/{cid}/finalize')
    assert r.status_code == 400
    assert r.json()['detail'].startswith('Faqat jarayondagi')
    db.refresh(one['s'])
    assert one['s'].quantity == D('48')
    assert db.query(StockMovement).filter_by(reference_type='revision', reference_id=cid).count() == 1


# ---------- izolyatsiya ----------

def test_other_company_cannot_touch_count(db, client, mk, one):
    cid = _count_and_start(client, one)
    _count(client, one, cid, 48)
    cb, bb, wb, ub = mk.tenant()
    cl = client.login(ub)
    for path in ('start', 'finalize', 'revert'):
        assert cl.post(f'/api/inventory-counts/{cid}/{path}').status_code == 404, path
    r = cl.post('/api/inventory-counts', json={'warehouse_id': one['w'].id})
    assert r.status_code == 404  # begona ombor
    db.refresh(one['s'])
    assert one['s'].quantity == D('50')


def test_other_company_own_warehouse_not_blocked(db, client, mk, one):
    _create(client, one)  # A korxonada ochiq revizya
    cb, bb, wb, ub = mk.tenant()
    _stock(db, _product(db, cb), wb, '3')
    r = client.login(ub).post('/api/inventory-counts', json={'warehouse_id': wb.id})
    assert r.status_code == 200, r.text


# ---------- 8. migratsiya ----------

def _load_migration():
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'alembic', 'versions',
                        't0_33_inventory_count_one_open_per_warehouse.py')
    spec = importlib.util.spec_from_file_location('mig_t0_33', os.path.abspath(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_cancels_duplicate_open_and_creates_index():
    mod = _load_migration()
    assert mod.revision == 't0_33' and mod.down_revision == 't0_32'

    eng = create_engine('sqlite://')
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE inventory_counts (id INTEGER PRIMARY KEY, warehouse_id INTEGER, "
                          "status VARCHAR(20), note TEXT)"))
        conn.execute(text("CREATE TABLE inventory_count_items (id INTEGER PRIMARY KEY)"))
        rows = [(1, 1, 'draft', None), (2, 1, 'in_progress', 'eski'), (3, 1, 'completed', None),
                (4, 2, 'draft', None), (5, 1, 'draft', None), (6, 2, 'cancelled', None)]
        for r in rows:
            conn.execute(text("INSERT INTO inventory_counts VALUES (:a,:b,:c,:d)"),
                         dict(a=r[0], b=r[1], c=r[2], d=r[3]))

        executed = []

        class FakeOp:
            @staticmethod
            def execute(sql):
                executed.append(sql)
                if sql.lstrip().upper().startswith('ALTER TABLE'):
                    # SQLite "ADD COLUMN IF NOT EXISTS" ni bilmaydi — ustun qo'shishni o'tkazib yuboramiz
                    return
                conn.execute(text(sql))

        mod.op = FakeOp
        mod.upgrade()

        st = {r[0]: (r[1], r[2]) for r in conn.execute(text("SELECT id, warehouse_id, status FROM inventory_counts"))}
        # 1-ombor: eng yangi ochiq (id=5) qoladi, 1 va 2 bekor; completed tegilmaydi
        assert st[5][1] == 'draft' and st[1][1] == 'cancelled' and st[2][1] == 'cancelled'
        assert st[3][1] == 'completed'
        assert st[4][1] == 'draft' and st[6][1] == 'cancelled'  # 2-ombor
        notes = dict(conn.execute(text("SELECT id, note FROM inventory_counts")).fetchall())
        assert 'avto-bekor' in notes[1] and notes[2].startswith('eski') and 'avto-bekor' in notes[2]
        assert notes[5] is None

        # Indeks yaratildi va endi ikkinchi ochiq revizyani rad etadi
        with pytest.raises(IntegrityError):
            conn.execute(text("INSERT INTO inventory_counts VALUES (7, 1, 'in_progress', NULL)"))
