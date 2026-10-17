"""T1.16 — Xarid (PO) va ta'minotchi to'lovlarining filialga to'g'ri bog'lanishi.

Qamrov: resolve_branch(prefer_warehouse), PO to'lovi xarajati ombor filialiga, ombor o'zgarganda
to'lov filiali ko'chishi, PO ro'yxati/yaratish/ko'rish filial cheklovi, PO qatori varianti (parent mahsulot),
variantli qabul, ta'minotchiga qaytarishda ombor majburiyligi, ta'minotchi tarixida ombor/filial.
"""
import itertools
from decimal import Decimal

import pytest

from app.models.batch import Batch
from app.models.inventory import StockLevel
from app.models.moliya import Transaction
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.purchase_order import POItem, PurchaseOrder
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services import supplier_ledger as ledger

_seq = itertools.count(1)


# ─── yordamchilar ───

def _product(db, company, ptype='simple', **kw):
    n = next(_seq)
    p = Product(name=f'Mahsulot {n}', sku=f'SKU-T116-{n}', barcode=f'BC-T116-{n}', company_id=company.id,
                cost_price=kw.pop('cost_price', 100), sale_price=kw.pop('sale_price', 200),
                product_type=ptype, **kw)
    db.add(p)
    db.flush()
    return p


def _variant(db, product, name='42'):
    v = ProductVariant(product_id=product.id, name=name, sku=f'V-{next(_seq)}', barcode=f'VB-{next(_seq)}',
                       cost_price=10, sale_price=20, wholesale_price=15)
    db.add(v)
    db.flush()
    return v


def _supplier(db, company):
    s = Supplier(name=f'Taminotchi {company.id}-{next(_seq)}', company_id=company.id, is_active=True,
                 debt_balance=Decimal(0), debt_balances={})
    db.add(s)
    db.flush()
    return s


def _stock(db, product, warehouse, qty, variant=None):
    s = StockLevel(product_id=product.id, warehouse_id=warehouse.id,
                   variant_id=variant.id if variant else None, quantity=Decimal(qty))
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def world(db, mk):
    """A korxona: b1 (w1), b2 (w2). Xodimlar: central accountant (filialsiz), b1 accountant, admin.
    B korxona: bitta filial/ombor."""
    a = mk.company('A korxona')
    b1 = mk.branch(a, 'Chilonzor')
    b2 = mk.branch(a, 'Yunusobod')
    w1 = mk.warehouse(a, b1, name='Chilonzor sklad')
    w2 = mk.warehouse(a, b2, name='Yunusobod sklad')
    other = mk.company('B korxona')
    ob = mk.branch(other)
    ow = mk.warehouse(other, ob, name='Begona sklad')
    return dict(
        a=a, b1=b1, b2=b2, w1=w1, w2=w2, other=other, ob=ob, ow=ow,
        sup=_supplier(db, a),
        central=mk.user(a, UserRole.accountant, branch=None),
        acc1=mk.user(a, UserRole.accountant, branch=b1),
        admin=mk.user(a, UserRole.admin, branch=b1),
        other_admin=mk.user(other, UserRole.admin, branch=ob),
    )


def _po(client, user, wh, sup, items, **extra):
    body = {'supplier_id': sup.id, 'warehouse_id': wh.id, 'items': items}
    body.update(extra)
    return client.login(user).post('/api/purchase-orders', json=body)


def _simple_items(p, qty=2, cost=1000):
    return [{'product_id': p.id, 'qty_ordered': qty, 'unit_cost': cost}]


def _po_txs(db, po_id):
    return db.query(Transaction).filter(
        Transaction.reference_type == 'purchase_order', Transaction.reference_id == po_id).all()


# ─── resolve_branch ───

def test_resolve_branch_prefers_warehouse(db, world):
    w = world
    # filialli xodim (b1), ombor b2
    assert ledger.resolve_branch(db, w['acc1'], w['w2'].id) == w['b1'].id
    assert ledger.resolve_branch(db, w['acc1'], w['w2'].id, prefer_warehouse=False) == w['b1'].id
    assert ledger.resolve_branch(db, w['acc1'], w['w2'].id, prefer_warehouse=True) == w['b2'].id
    # filialsiz xodim: ombor filiali
    assert ledger.resolve_branch(db, w['central'], w['w2'].id, prefer_warehouse=True) == w['b2'].id
    # ombor berilmasa — xodim filialiga qaytadi
    assert ledger.resolve_branch(db, w['acc1'], None, prefer_warehouse=True) == w['b1'].id


def test_resolve_branch_ignores_foreign_company_warehouse(db, world):
    w = world
    # begona korxona ombori filiali e'tiborga olinmaydi — xodim filialiga qaytadi
    assert ledger.resolve_branch(db, w['acc1'], w['ow'].id, prefer_warehouse=True) == w['b1'].id


# ─── PO to'lovi xarajati filiali ───

def test_po_payment_expense_goes_to_warehouse_branch(client, db, world):
    w = world
    p = _product(db, w['a'])
    for user in (w['central'], w['admin']):
        r = _po(client, user, w['w2'], w['sup'], _simple_items(p), paid_amount=2000, payment_type='cash')
        assert r.status_code == 200, r.text
        txs = _po_txs(db, r.json()['id'])
        assert len(txs) == 1
        assert txs[0].branch_id == w['b2'].id


def test_po_payment_by_branch_user_in_own_branch(client, db, world):
    w = world
    p = _product(db, w['a'])
    r = _po(client, w['acc1'], w['w1'], w['sup'], _simple_items(p), paid_amount=1000)
    assert r.status_code == 200, r.text
    assert _po_txs(db, r.json()['id'])[0].branch_id == w['b1'].id


def test_update_po_warehouse_moves_payment_branch(client, db, world):
    w = world
    p = _product(db, w['a'])
    r = _po(client, w['admin'], w['w1'], w['sup'], _simple_items(p), paid_amount=2000)
    po_id = r.json()['id']
    assert _po_txs(db, po_id)[0].branch_id == w['b1'].id
    r = client.login(w['admin']).patch(f'/api/purchase-orders/{po_id}', json={'warehouse_id': w['w2'].id})
    assert r.status_code == 200, r.text
    db.expire_all()
    txs = _po_txs(db, po_id)
    assert len(txs) == 1 and txs[0].branch_id == w['b2'].id


# ─── Filial cheklovi ───

def test_po_scope_forbidden_other_branch(client, db, world):
    w = world
    p = _product(db, w['a'])
    # Chilonzorga biriktirilgan accountant Yunusobod ombori uchun PO yarata olmaydi
    r = _po(client, w['acc1'], w['w2'], w['sup'], _simple_items(p))
    assert r.status_code == 403
    assert r.json()['detail'] == "Bu ombor sizning filialingizga tegishli emas"
    # o'z filiali ombori — ishlaydi
    assert _po(client, w['acc1'], w['w1'], w['sup'], _simple_items(p)).status_code == 200


def test_po_list_and_get_scoped_for_branch_user(client, db, world):
    w = world
    p = _product(db, w['a'])
    po1 = _po(client, w['admin'], w['w1'], w['sup'], _simple_items(p)).json()['id']
    po2 = _po(client, w['admin'], w['w2'], w['sup'], _simple_items(p)).json()['id']
    c = client.login(w['acc1'])
    rows = c.get('/api/purchase-orders').json()
    assert [r['id'] for r in rows] == [po1]
    # boshqa filial PO si — 404
    assert c.get(f'/api/purchase-orders/{po2}').status_code == 404
    assert c.get(f'/api/purchase-orders/{po1}').status_code == 200
    # boshqa filial yoki uning ombori so'ralsa — 403
    assert c.get(f"/api/purchase-orders?branch_id={w['b2'].id}").status_code == 403
    assert c.get(f"/api/purchase-orders?warehouse_id={w['w2'].id}").status_code == 403
    assert c.get(f"/api/purchase-orders?branch_id={w['b1'].id}").status_code == 200
    # admin hammasini ko'radi
    assert {r['id'] for r in client.login(w['admin']).get('/api/purchase-orders').json()} == {po1, po2}


def test_po_company_isolation(client, db, world):
    w = world
    p = _product(db, w['a'])
    po = _po(client, w['admin'], w['w1'], w['sup'], _simple_items(p)).json()['id']
    c = client.login(w['other_admin'])
    assert c.get(f'/api/purchase-orders/{po}').status_code == 404
    assert c.get('/api/purchase-orders').json() == []


# ─── Variant ───

def test_build_items_requires_variant_for_parent(client, db, world):
    w = world
    parent = _product(db, w['a'], ptype='parent')
    _variant(db, parent)
    r = _po(client, w['admin'], w['w1'], w['sup'], _simple_items(parent))
    assert r.status_code == 400
    assert 'variant' in r.json()['detail'].lower()


def test_build_items_rejects_foreign_variant(client, db, world):
    w = world
    parent = _product(db, w['a'], ptype='parent')
    other_parent = _product(db, w['a'], ptype='parent')
    foreign_variant = _variant(db, other_parent)
    r = _po(client, w['admin'], w['w1'], w['sup'], [
        {'product_id': parent.id, 'variant_id': foreign_variant.id, 'qty_ordered': 1, 'unit_cost': 10}])
    assert r.status_code == 404
    r = _po(client, w['admin'], w['w1'], w['sup'], [
        {'product_id': parent.id, 'variant_id': 99999999, 'qty_ordered': 1, 'unit_cost': 10}])
    assert r.status_code == 404


def test_build_items_rejects_variant_for_simple_product(client, db, world):
    w = world
    parent = _product(db, w['a'], ptype='parent')
    v = _variant(db, parent)
    simple = _product(db, w['a'])
    r = _po(client, w['admin'], w['w1'], w['sup'], [
        {'product_id': simple.id, 'variant_id': v.id, 'qty_ordered': 1, 'unit_cost': 10}])
    assert r.status_code == 400


def test_receive_variant_increments_variant_stock(client, db, world):
    w = world
    parent = _product(db, w['a'], ptype='parent', cost_price=100, sale_price=200)
    v42 = _variant(db, parent, '42')
    v43 = _variant(db, parent, '43')
    # tasodifiy boshqa Product ning id si variant id si bilan bir xil bo'lishi mumkin — unga kirim tushmasin
    r = _po(client, w['admin'], w['w1'], w['sup'], [
        {'product_id': parent.id, 'variant_id': v42.id, 'qty_ordered': 5, 'unit_cost': 1000,
         'new_sale_price': 1500, 'new_wholesale_price': 1200}], status='received')
    assert r.status_code == 200, r.text
    out = r.json()
    assert out['items'][0]['variant_id'] == v42.id and out['items'][0]['variant_name'] == '42'
    po_id = out['id']

    item = db.query(POItem).filter(POItem.po_id == po_id).one()
    assert item.product_id == parent.id and item.variant_id == v42.id

    st = db.query(StockLevel).filter(StockLevel.product_id == parent.id, StockLevel.warehouse_id == w['w1'].id,
                                     StockLevel.variant_id == v42.id).one()
    assert Decimal(st.quantity) == Decimal(5)
    assert db.query(StockLevel).filter(StockLevel.variant_id == v43.id).count() == 0
    b = db.query(Batch).filter(Batch.po_id == po_id).one()
    assert b.variant_id == v42.id and b.product_id == parent.id

    db.expire_all()
    # variant narxlari yangilandi, parent narxlari o'zgarmadi
    v = db.get(ProductVariant, v42.id)
    assert Decimal(v.cost_price) == Decimal(1000)
    assert Decimal(v.sale_price) == Decimal(1500)
    assert Decimal(v.wholesale_price) == Decimal(1200)
    pr = db.get(Product, parent.id)
    assert Decimal(pr.cost_price) == Decimal(100) and Decimal(pr.sale_price) == Decimal(200)
    # boshqa variant tegilmagan
    assert Decimal(db.get(ProductVariant, v43.id).cost_price) == Decimal(10)


# ─── Ta'minotchiga qaytarish ───

def test_supplier_return_requires_warehouse_multi_wh(client, db, world):
    w = world
    p = _product(db, w['a'])
    _stock(db, p, w['w1'], 10)
    body = {'supplier_id': w['sup'].id, 'items': [{'product_id': p.id, 'quantity': 1, 'unit_cost': 100}]}
    r = client.login(w['admin']).post('/api/inventory/return-to-supplier', json=body)
    assert r.status_code == 400
    assert r.json()['detail'] == "Qaytarish ombori ko'rsatilishi shart"
    body['warehouse_id'] = w['w1'].id
    r = client.login(w['admin']).post('/api/inventory/return-to-supplier', json=body)
    assert r.status_code == 200, r.text


def test_supplier_return_single_warehouse_auto(client, db, mk):
    c, b, wh, admin = mk.tenant()
    sup = _supplier(db, c)
    p = _product(db, c)
    _stock(db, p, wh, 10)
    r = client.login(admin).post('/api/inventory/return-to-supplier', json={
        'supplier_id': sup.id, 'items': [{'product_id': p.id, 'quantity': 3, 'unit_cost': 100}]})
    assert r.status_code == 200, r.text
    db.expire_all()
    st = db.query(StockLevel).filter(StockLevel.product_id == p.id, StockLevel.warehouse_id == wh.id).one()
    assert Decimal(st.quantity) == Decimal(7)


# ─── Ta'minotchi tarixi ───

def test_supplier_history_has_warehouse_and_branch(client, db, world):
    w = world
    p = _product(db, w['a'])
    r = _po(client, w['central'], w['w2'], w['sup'], _simple_items(p), paid_amount=1000)
    assert r.status_code == 200, r.text
    rows = client.login(w['admin']).get(f"/api/suppliers/{w['sup'].id}/history").json()
    purchase = [x for x in rows if x['op_type'] == 'purchase'][0]
    payment = [x for x in rows if x['op_type'] == 'payment'][0]
    assert purchase['warehouse_name'] == 'Yunusobod sklad'
    assert payment['branch_name'] == 'Yunusobod'
    # begona korxona ta'minotchisi — 404
    assert client.login(w['other_admin']).get(f"/api/suppliers/{w['sup'].id}/history").status_code == 404
