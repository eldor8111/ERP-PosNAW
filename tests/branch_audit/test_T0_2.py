"""T0.2 — Inventarizatsiya (revizya) servisida korxona izolyatsiyasi."""
from decimal import Decimal

import pytest

from app.models.inventory import StockLevel
from app.models.inventory_count import CountStatus, InventoryCount, InventoryCountItem
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import UserRole

_n = [0]


def _product(db, company, name=None):
    _n[0] += 1
    p = Product(sku=f'SKU{_n[0]}', barcode=f'BC{_n[0]:08d}', name=name or f'Tovar {_n[0]}',
                company_id=company.id, product_type='simple')
    db.add(p)
    db.flush()
    return p


def _variant(db, product):
    v = ProductVariant(product_id=product.id, name='XL')
    db.add(v)
    db.flush()
    return v


def _stock(db, product, wh, qty, variant=None):
    s = StockLevel(product_id=product.id, variant_id=variant.id if variant else None,
                   warehouse_id=wh.id, quantity=Decimal(qty))
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def two(db, mk):
    """Ikki korxona: har biriga ombor, admin, mahsulot va qoldiq."""
    ca, ba, wa, ua = mk.tenant()
    cb, bb, wb, ub = mk.tenant()
    pa = _product(db, ca)
    pb = _product(db, cb)
    sa = _stock(db, pa, wa, '10')
    sb = _stock(db, pb, wb, '7')
    return dict(ca=ca, wa=wa, ua=ua, pa=pa, sa=sa, cb=cb, wb=wb, ub=ub, pb=pb, sb=sb)


def _counts(db):
    return db.query(InventoryCount).count(), db.query(InventoryCountItem).count()


def _b_count(db, t, status=CountStatus.in_progress, counted=None):
    """B korxonasida tayyor revizya (to'g'ridan-to'g'ri bazada)."""
    c = InventoryCount(number=f'ICB{t["wb"].id}{status.value}', warehouse_id=t['wb'].id,
                       created_by=t['ub'].id, status=status)
    db.add(c)
    db.flush()
    db.add(InventoryCountItem(count_id=c.id, product_id=t['pb'].id, system_qty=Decimal('7'),
                              counted_qty=counted, variance=None))
    db.flush()
    return c


# ---------- create ----------

def test_create_foreign_warehouse_404(db, client, two):
    before = _counts(db)
    r = client.login(two['ua']).post('/api/inventory-counts', json={'warehouse_id': two['wb'].id})
    assert r.status_code == 404
    assert r.json()['detail'] == 'Ombor topilmadi'
    assert _counts(db) == before


def test_create_own_warehouse_ok(db, client, two):
    r = client.login(two['ua']).post('/api/inventory-counts', json={'warehouse_id': two['wa'].id})
    assert r.status_code == 200, r.text
    assert r.json()['item_count'] == 1
    items = db.query(InventoryCountItem).all()
    assert [i.product_id for i in items] == [two['pa'].id]
    assert items[0].system_qty == Decimal('10')


# ---------- start / items / finalize begona revizya ----------

@pytest.mark.parametrize('status', [CountStatus.draft, CountStatus.in_progress])
def test_foreign_count_start_items_finalize_404(db, client, two, status):
    c = _b_count(db, two, status)
    cl = client.login(two['ua'])
    for path, body in (
        (f'/api/inventory-counts/{c.id}/start', None),
        (f'/api/inventory-counts/{c.id}/items', [{'product_id': two['pb'].id, 'counted_qty': 0}]),
        (f'/api/inventory-counts/{c.id}/finalize', None),
    ):
        r = cl.post(path, json=body) if body is not None else cl.post(path)
        assert r.status_code == 404, (path, r.text)
        assert r.json()['detail'] == 'Inventarizatsiya topilmadi'
    db.refresh(c)
    db.refresh(two['sb'])
    assert c.status == status
    assert two['sb'].quantity == Decimal('7')
    assert db.query(InventoryCountItem).filter_by(count_id=c.id).one().counted_qty is None


def test_foreign_finalize_does_not_touch_stock(db, client, two):
    c = _b_count(db, two, CountStatus.in_progress, counted=Decimal('0'))
    r = client.login(two['ua']).post(f'/api/inventory-counts/{c.id}/finalize')
    assert r.status_code == 404
    db.refresh(two['sb'])
    assert two['sb'].quantity == Decimal('7')


# ---------- items: begona product / variant ----------

def _own_count(db, client, two):
    cl = client.login(two['ua'])
    r = cl.post('/api/inventory-counts', json={'warehouse_id': two['wa'].id})
    assert r.status_code == 200, r.text
    cid = r.json()['id']
    assert cl.post(f'/api/inventory-counts/{cid}/start').status_code == 200
    return cl, cid


def test_items_foreign_product_404(db, client, two):
    cl, cid = _own_count(db, client, two)
    n = db.query(InventoryCountItem).count()
    r = cl.post(f'/api/inventory-counts/{cid}/items', json=[
        {'product_id': two['pa'].id, 'counted_qty': 5},
        {'product_id': two['pb'].id, 'counted_qty': 0},
    ])
    assert r.status_code == 404
    assert r.json()['detail'] == f"Mahsulot ID={two['pb'].id} topilmadi"
    assert db.query(InventoryCountItem).count() == n
    # birinchi (to'g'ri) qator ham yozilmagan bo'lishi kerak
    own = db.query(InventoryCountItem).filter_by(count_id=cid, product_id=two['pa'].id).one()
    assert own.counted_qty is None


def test_items_variant_of_other_product_404(db, client, two):
    pa2 = _product(db, two['ca'])
    v_other = _variant(db, pa2)
    cl, cid = _own_count(db, client, two)
    n = db.query(InventoryCountItem).count()
    r = cl.post(f'/api/inventory-counts/{cid}/items', json=[
        {'product_id': two['pa'].id, 'variant_id': v_other.id, 'counted_qty': 3},
    ])
    assert r.status_code == 404
    assert db.query(InventoryCountItem).count() == n


def test_items_foreign_variant_404(db, client, two):
    vb = _variant(db, two['pb'])
    cl, cid = _own_count(db, client, two)
    r = cl.post(f'/api/inventory-counts/{cid}/items', json=[
        {'product_id': two['pa'].id, 'variant_id': vb.id, 'counted_qty': 3},
    ])
    assert r.status_code == 404


# ---------- o'z korxonasi: to'liq oqim ----------

def test_own_full_flow_and_revert_delete(db, client, two):
    cl, cid = _own_count(db, client, two)
    r = cl.post(f'/api/inventory-counts/{cid}/items',
                json=[{'product_id': two['pa'].id, 'counted_qty': 4}])
    assert r.status_code == 200, r.text
    r = cl.post(f'/api/inventory-counts/{cid}/finalize')
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'completed'
    db.refresh(two['sa'])
    assert two['sa'].quantity == Decimal('4')
    # B qoldig'i o'zgarmagan
    db.refresh(two['sb'])
    assert two['sb'].quantity == Decimal('7')

    r = cl.post(f'/api/inventory-counts/{cid}/revert')
    assert r.status_code == 200, r.text
    db.refresh(two['sa'])
    assert two['sa'].quantity == Decimal('10')

    assert cl.delete(f'/api/inventory-counts/{cid}').status_code == 200


def test_own_new_item_with_valid_variant(db, client, two):
    v = _variant(db, two['pa'])
    cl, cid = _own_count(db, client, two)
    r = cl.post(f'/api/inventory-counts/{cid}/items', json=[
        {'product_id': two['pa'].id, 'variant_id': v.id, 'counted_qty': 2},
    ])
    assert r.status_code == 200, r.text


def test_revert_delete_foreign_still_404(db, client, two):
    c = _b_count(db, two, CountStatus.completed)
    cl = client.login(two['ua'])
    assert cl.post(f'/api/inventory-counts/{c.id}/revert').status_code == 404
    assert cl.delete(f'/api/inventory-counts/{c.id}').status_code == 404


# ---------- super_admin va korxonasiz foydalanuvchi ----------

def test_super_admin_can_operate_any_company(db, client, mk, two):
    sa_user = mk.user(None, role=UserRole.super_admin)
    cl = client.login(sa_user)
    r = cl.post('/api/inventory-counts', json={'warehouse_id': two['wb'].id})
    assert r.status_code == 200, r.text
    cid = r.json()['id']
    assert cl.post(f'/api/inventory-counts/{cid}/start').status_code == 200
    r = cl.post(f'/api/inventory-counts/{cid}/items',
                json=[{'product_id': two['pb'].id, 'counted_qty': 1}])
    assert r.status_code == 200, r.text
    # super_admin ham begona korxona mahsuloti (ombor egasiga tegishli bo'lmagan) qo'sha olmaydi
    r = cl.post(f'/api/inventory-counts/{cid}/items',
                json=[{'product_id': two['pa'].id, 'counted_qty': 1}])
    assert r.status_code == 404
    assert cl.post(f'/api/inventory-counts/{cid}/finalize').status_code == 200


def test_user_without_company_forbidden(db, client, mk, two):
    u = mk.user(None, role=UserRole.admin)
    cl = client.login(u)
    before = _counts(db)
    r = cl.post('/api/inventory-counts', json={'warehouse_id': two['wb'].id})
    assert r.status_code == 403
    assert _counts(db) == before
