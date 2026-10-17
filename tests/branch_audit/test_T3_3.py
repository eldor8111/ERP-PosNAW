"""T3.3 — Ombor sahifalari UI to'g'rilash.

Backend: `GET /inventory/movements` ko'p qiymatli `type`, `POST /warehouses` filialni avtomatik qo'yishi,
transfer yaratish/bekor qilish (qoldiqni tiklash) regressiyasi. Frontend: Ombor.jsx / Operations.jsx /
Warehouse.jsx / InventoryCounts.jsx fayllarida kerakli o'zgarishlar va i18n pending kalitlari.
"""
import itertools
import json
import os
import re
from decimal import Decimal

import pytest

from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FE = os.path.join(ROOT, 'frontend', 'src')
_seq = itertools.count(1)


def _read(*parts):
    with open(os.path.join(FE, *parts), encoding='utf-8') as f:
        return f.read()


def _product(db, company):
    n = next(_seq)
    p = Product(name=f'Mahsulot {n}', sku=f'SKU-T33-{n}', barcode=f'BC-T33-{n}',
                company_id=company.id, cost_price=0, sale_price=0, product_type='simple')
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty):
    s = StockLevel(product_id=product.id, warehouse_id=warehouse.id, variant_id=None, quantity=Decimal(qty))
    db.add(s)
    db.flush()
    return s


def _movement(db, product, warehouse, user, mtype, qty=1):
    m = StockMovement(product_id=product.id, warehouse_id=warehouse.id, type=mtype,
                      qty_before=0, qty_after=qty, quantity=qty, user_id=user.id)
    db.add(m)
    db.flush()
    return m


def _qty(db, product, warehouse):
    s = db.query(StockLevel).filter(StockLevel.product_id == product.id,
                                    StockLevel.warehouse_id == warehouse.id).first()
    return Decimal(s.quantity) if s else Decimal(0)


@pytest.fixture
def world(db, mk):
    """A korxona: 2 filial, har birida ombor; B korxona: alohida tenant."""
    a = mk.company('A korxona')
    b1 = mk.branch(a, 'Chilonzor')
    b2 = mk.branch(a, 'Yunusobod')
    w1 = mk.warehouse(a, b1, name='Chilonzor ombor')
    w2 = mk.warehouse(a, b2, name='Yunusobod ombor')
    admin = mk.user(a, UserRole.admin, branch=b1)
    cb, bb, wb, ub = mk.tenant()
    return dict(a=a, b1=b1, b2=b2, w1=w1, w2=w2, admin=admin, cb=cb, bb=bb, wb=wb, ub=ub)


# ─── (a) GET /inventory/movements — ko'p qiymatli type ───

def _movement_world(db, w):
    p = _product(db, w['a'])
    for mt in (MovementType.IN, MovementType.OUT, MovementType.TRANSFER_IN, MovementType.TRANSFER_OUT):
        _movement(db, p, w['w1'], w['admin'], mt)
    return p


def _types(resp):
    assert resp.status_code == 200, resp.text
    return sorted(m['type'] for m in resp.json())


def test_movements_multiple_type_values(client, db, world):
    _movement_world(db, world)
    r = client.login(world['admin']).get('/api/inventory/movements?type=IN&type=OUT')
    assert _types(r) == ['IN', 'OUT']


def test_movements_kirim_chiqim_pairs(client, db, world):
    _movement_world(db, world)
    c = client.login(world['admin'])
    assert _types(c.get('/api/inventory/movements?type=IN&type=TRANSFER_IN')) == ['IN', 'TRANSFER_IN']
    assert _types(c.get('/api/inventory/movements?type=OUT&type=TRANSFER_OUT')) == ['OUT', 'TRANSFER_OUT']


def test_movements_single_type_backward_compatible(client, db, world):
    _movement_world(db, world)
    c = client.login(world['admin'])
    assert _types(c.get('/api/inventory/movements?type=IN')) == ['IN']
    assert len(c.get('/api/inventory/movements').json()) == 4      # filtrsiz — hammasi


def test_movements_invalid_type_422(client, db, world):
    _movement_world(db, world)
    c = client.login(world['admin'])
    assert c.get('/api/inventory/movements?type=in').status_code == 422      # kichik harf (eski xato)
    assert c.get('/api/inventory/movements?type=IN&type=XXX').status_code == 422


def test_movements_company_isolation(client, db, world):
    """B korxona harakatlari A foydalanuvchisiga ko'rinmaydi, o'z harakatlari ko'rinadi."""
    w = world
    pa = _product(db, w['a'])
    pb = _product(db, w['cb'])
    _movement(db, pa, w['w1'], w['admin'], MovementType.IN)
    mb = _movement(db, pb, w['wb'], w['ub'], MovementType.IN)
    r = client.login(w['admin']).get('/api/inventory/movements?type=IN&type=OUT')
    assert r.status_code == 200
    ids = {m['id'] for m in r.json()}
    assert mb.id not in ids and len(ids) == 1
    rb = client.login(w['ub']).get('/api/inventory/movements?type=IN')
    assert {m['id'] for m in rb.json()} == {mb.id}


# ─── (b) POST /warehouses — filial avtomatik ───

def test_create_warehouse_without_branch_uses_user_branch(client, world):
    w = world
    r = client.login(w['admin']).post('/api/warehouses', json={'name': 'Yangi ombor'})
    assert r.status_code in (200, 201), r.text
    assert r.json()['branch_id'] == w['b1'].id           # foydalanuvchining filiali


def test_create_warehouse_explicit_branch_kept(client, world):
    w = world
    r = client.login(w['admin']).post('/api/warehouses', json={'name': 'Boshqa filial ombori', 'branch_id': w['b2'].id})
    assert r.status_code in (200, 201), r.text
    assert r.json()['branch_id'] == w['b2'].id


def test_create_warehouse_foreign_branch_rejected(client, world):
    """Boshqa korxona filialiga ombor biriktirib bo'lmaydi (korxona izolyatsiyasi)."""
    w = world
    r = client.login(w['admin']).post('/api/warehouses', json={'name': 'Begona', 'branch_id': w['bb'].id})
    assert r.status_code in (400, 404), r.text


def test_create_warehouse_single_branch_company_no_user_branch(client, db, mk):
    """Filialga biriktirilmagan admin, korxonada yagona filial bo'lsa — shu filial qo'yiladi."""
    c = mk.company()
    b = mk.branch(c)
    admin = mk.user(c, UserRole.admin)
    r = client.login(admin).post('/api/warehouses', json={'name': 'Asosiy sklad'})
    assert r.status_code in (200, 201), r.text
    assert r.json()['branch_id'] == b.id


# ─── (c) transfer + bekor qilish — qoldiqni tiklash (regressiya) ───

def test_transfer_then_cancel_restores_stock(client, db, world):
    w = world
    p = _product(db, w['a'])
    _stock(db, p, w['w1'], 40)
    _stock(db, p, w['w2'], 0)
    c = client.login(w['admin'])
    r = c.post('/api/transfers', json={'from_warehouse_id': w['w1'].id, 'to_warehouse_id': w['w2'].id,
                                      'items': [{'product_id': p.id, 'quantity': 10}],
                                      'two_step': False})  # T4.1: filiallararo standart ikki bosqichli
    assert r.status_code == 200, r.text
    tid = r.json()['id']
    assert r.json()['status'] == 'received'               # yaratilishi bilan qabul qilinadi
    assert _qty(db, p, w['w1']) == Decimal(30) and _qty(db, p, w['w2']) == Decimal(10)
    rc = c.post(f'/api/transfers/{tid}/cancel')
    assert rc.status_code == 200, rc.text
    assert _qty(db, p, w['w1']) == Decimal(40) and _qty(db, p, w['w2']) == Decimal(0)
    # ro'yxatda `status=received` filtri 422 bermaydi, `confirmed` esa enumda yo'q
    assert c.get('/api/transfers?status=received').status_code == 200
    assert c.get('/api/transfers?status=confirmed').status_code == 422


def test_transfer_cancel_foreign_company_404(client, db, world):
    w = world
    p = _product(db, w['a'])
    _stock(db, p, w['w1'], 5)
    tid = client.login(w['admin']).post('/api/transfers', json={
        'from_warehouse_id': w['w1'].id, 'to_warehouse_id': w['w2'].id,
        'items': [{'product_id': p.id, 'quantity': 2}], 'two_step': False}).json()['id']  # T4.1
    r = client.login(w['ub']).post(f'/api/transfers/{tid}/cancel')
    assert r.status_code in (403, 404)
    assert _qty(db, p, w['w2']) == Decimal(2)             # begona bekor qila olmadi


def test_products_search_with_warehouse_returns_source_stock(client, db, world):
    """Chilonzorda 0, Yunusobodda 40: warehouse_id=Chilonzor bo'lganda stock_quantity = 0 (manba qoldig'i)."""
    w = world
    p = _product(db, w['a'])
    _stock(db, p, w['w1'], 0)
    _stock(db, p, w['w2'], 40)
    c = client.login(w['admin'])
    r = c.get(f'/api/products/?search={p.name}&warehouse_id={w["w1"].id}&limit=30')
    assert r.status_code == 200, r.text
    row = next(x for x in r.json() if x['id'] == p.id)
    assert Decimal(str(row['stock_quantity'])) == 0
    r2 = c.get(f'/api/products/?search={p.name}&warehouse_id={w["w2"].id}&limit=30')
    assert Decimal(str(next(x for x in r2.json() if x['id'] == p.id)['stock_quantity'])) == 40


# ─── Frontend fayllari (statik tekshiruv) ───

def test_pending_i18n_keys_complete():
    path = os.path.join(os.path.dirname(__file__), 'i18n_pending', 'T3.3.json')
    data = json.load(open(path, encoding='utf-8'))
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    required = {'warehouse.addWarehouse', 'warehouse.noWarehouses', 'warehouse.notVisibleWarning',
                'ombor.statusReceived', 'ombor.statusInTransit', 'ombor.cancelReceivedConfirm',
                'ombor.branchWarehousesList'}
    assert required <= set(data['uz'])
    assert data['uz']['warehouse.addWarehouse'] == "Yangi ombor qo'shish"
    assert data['ru']['warehouse.addWarehouse'] == 'Новый склад'
    assert data['en']['warehouse.addWarehouse'] == 'New Warehouse'
    assert all(v.strip() for lang in data.values() for v in lang.values())


def test_new_transfer_key_not_used_in_frontend():
    """`warehouse.newTransfer` kaliti JSX da ishlatilmaydi (ombor yaratish — addWarehouse, transfer — ops.newTransfer)."""
    for rel in (('pages', 'admin', 'Ombor.jsx'), ('pages', 'admin', 'Warehouse.jsx'),
                ('pages', 'admin', 'Operations.jsx'), ('pages', 'admin', 'InventoryCounts.jsx')):
        assert 'warehouse.newTransfer' not in _read(*rel), rel
    om = _read('pages', 'admin', 'Ombor.jsx')
    assert "t('ops.newTransfer')" in om and "t('warehouse.addWarehouse')" in om
    assert "t('warehouse.noWarehouses')" in om


def test_ombor_status_badge_and_cancel_received():
    om = _read('pages', 'admin', 'Ombor.jsx')
    assert "received:  { label: t('ombor.statusReceived')" in om
    assert "in_transit: { label: t('ombor.statusInTransit')" in om
    assert "tr.status === 'received'" in om and 'ombor.cancelReceivedConfirm' in om
    assert 'alert(' not in om


def test_ombor_movements_tab_types_and_serializer():
    om = _read('pages', 'admin', 'Ombor.jsx')
    assert "in: ['IN', 'TRANSFER_IN']" in om and "out: ['OUT', 'TRANSFER_OUT']" in om
    assert 'paramsSerializer: { indexes: null }' in om
    assert 'console.error' not in om


def test_ombor_transfer_uses_server_search_not_preload():
    om = _read('pages', 'admin', 'Ombor.jsx')
    assert 'limit: 300' not in om
    assert re.search(r"warehouse_id: warehouseId, limit: 30", om)
    assert 'ProductCombo' in om and "p.product_type !== 'sell'" in om
    # manba ombor o'zgarsa qatorlar tozalanadi
    assert 'setFromWarehouse' in om


def test_operations_status_filter_and_meta():
    op = _read('pages', 'admin', 'Operations.jsx')
    m = re.search(r"const trMeta = \{(.*?)\n\};", op, re.S)
    assert m, 'trMeta topilmadi'
    body = m.group(1)
    assert 'confirmed' not in body
    assert 'received:' in body and 'ombor.statusReceived' in body
    assert 'in_transit:' in body and 'ombor.statusInTransit' in body
    # holat filtri — select, matn bo'yicha taxmin yo'q
    assert 'Object.entries(trMeta).find' not in op
    assert 'Object.entries(trMeta).map(([k, m]) => <option key={k} value={k}>' in op


def test_operations_transfer_view_source_warehouse_stock():
    op = _read('pages', 'admin', 'Operations.jsx')
    i = op.index('function TransferCreateView')
    j = op.index('function TransferlarTab')
    view = op[i:j]
    assert 'localProducts' not in view and 'limit: 200' not in view
    assert '<SrvProdSearch key={form.from_warehouse_id} warehouseId={form.from_warehouse_id}' in view
    assert 'warehouse_id' in op[op.index('function useServerProducts'):op.index('function ProdSearch')]


def test_warehouse_forms_default_branch_and_required():
    wh = _read('pages', 'admin', 'Warehouse.jsx')
    assert 'currentBranchId ?? assignedBranchId' in wh
    assert "warehouse.notVisibleWarning" in wh and "warehouse.addWarehouse" in wh
    assert "warehouse.newTransfer" not in wh
    assert re.search(r'branches\.length > 0 && !canSelectAll && !branchId', wh)
    om = _read('pages', 'admin', 'Ombor.jsx')
    assert 'currentBranchId ?? assignedBranchId' in om and 'warehouse.notVisibleWarning' in om


def test_inventory_counts_no_bulk_preload():
    ic = _read('pages', 'admin', 'InventoryCounts.jsx')
    assert 'limit: 1000' not in ic
    # qidiruv serverdan: faqat search + limit (warehouse_id filtri ishlatilmaydi)
    assert "params: { search: v, limit: 15, status: 'active' }" in ic
