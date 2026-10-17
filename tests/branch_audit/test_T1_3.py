"""T1.3 — Ombor ro'yxatlari (scope/branch_id/include_inactive), yozish tekshiruvi (kirim, transfer, xarid)
va /inventory/stock, /purchase-orders ro'yxatlarining filial doirasi.

Qamrov: rol x scope x filial matritsasi, begona korxona izolyatsiyasi, transfer manba/maqsad,
PO PATCH filial ko'chirishi, include_inactive, /inventory/warehouses maydonlari.
"""
import itertools
from decimal import Decimal

import pytest

from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier
from app.models.user import UserRole

_seq = itertools.count(1)


# ─── yordamchilar ───

def _product(db, company):
    n = next(_seq)
    p = Product(name=f'Mahsulot {n}', sku=f'SKU-T13-{n}', barcode=f'BC-T13-{n}',
                company_id=company.id, cost_price=0, sale_price=0, product_type='simple')
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty):
    s = StockLevel(product_id=product.id, warehouse_id=warehouse.id, variant_id=None, quantity=Decimal(qty))
    db.add(s)
    db.flush()
    return s


def _supplier(db, company):
    s = Supplier(name=f'Taminotchi {company.id}', company_id=company.id, is_active=True,
                 debt_balance=Decimal(0), debt_balances={})
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def world(db, mk):
    """A korxona: 2 filial (b1: w1 + nofaol w3, b2: w2), B korxona: bitta filial/ombor."""
    a = mk.company('A korxona')
    b1 = mk.branch(a, 'Asosiy')
    b2 = mk.branch(a, 'Chilonzor')
    w1 = mk.warehouse(a, b1, name='Asosiy sklad')
    w2 = mk.warehouse(a, b2, name='Chilonzor sklad')
    w3 = mk.warehouse(a, b1, name='Eski sklad', is_active=False)
    other = mk.company('B korxona')
    ob = mk.branch(other)
    ow = mk.warehouse(other, ob, name='Begona sklad')
    p = _product(db, a)
    _stock(db, p, w1, 100)
    _stock(db, p, w2, 50)
    return dict(
        a=a, b1=b1, b2=b2, w1=w1, w2=w2, w3=w3, other=other, ob=ob, ow=ow, p=p,
        admin=mk.user(a, UserRole.admin, branch=b1),
        manager=mk.user(a, UserRole.manager, branch=b1),
        wh_user=mk.user(a, UserRole.warehouse, branch=b1),
        cashier=mk.user(a, UserRole.cashier, branch=b1),
        other_admin=mk.user(other, UserRole.admin, branch=ob),
    )


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return {w['id'] for w in resp.json()}


# ─── GET /warehouses ───

def test_warehouses_context_default_admin_sees_all_company_branches(client, world):
    w = world
    ids = _ids(client.login(w['admin']).get('/api/warehouses'))
    assert ids == {w['w1'].id, w['w2'].id}          # begona korxona ombori va nofaol ombor yo'q


def test_warehouses_context_non_bypass_only_own_branch(client, world):
    w = world
    assert _ids(client.login(w['manager']).get('/api/warehouses')) == {w['w1'].id}
    assert _ids(client.login(w['cashier']).get('/api/warehouses')) == {w['w1'].id}


def test_warehouses_scope_all_matrix(client, world):
    w = world
    both = {w['w1'].id, w['w2'].id}
    for role_key in ('admin', 'manager', 'wh_user'):
        assert _ids(client.login(w[role_key]).get('/api/warehouses?scope=all')) == both, role_key
    r = client.login(w['cashier']).get('/api/warehouses?scope=all')
    assert r.status_code == 403
    assert r.json()['detail'] == "Barcha omborlarni ko'rish ruxsati yo'q"


def test_warehouses_scope_all_with_branch_name(client, world):
    w = world
    rows = client.login(w['wh_user']).get('/api/warehouses?scope=all').json()
    names = {r['id']: r['branch_name'] for r in rows}
    assert names == {w['w1'].id: 'Asosiy', w['w2'].id: 'Chilonzor'}


def test_warehouses_scope_invalid_422(client, world):
    assert client.login(world['admin']).get('/api/warehouses?scope=zzz').status_code == 422


def test_warehouses_branch_id_filter_and_foreign_404(client, world):
    w = world
    assert _ids(client.login(w['admin']).get(f"/api/warehouses?branch_id={w['b2'].id}")) == {w['w2'].id}
    # begona korxona filiali
    assert client.login(w['admin']).get(f"/api/warehouses?branch_id={w['ob'].id}").status_code == 404
    assert client.login(w['admin']).get(f"/api/warehouses?scope=all&branch_id={w['ob'].id}").status_code == 404
    # non-bypass: context da ruxsatsiz filial -> 403, scope=all da ruxsat bor
    assert client.login(w['manager']).get(f"/api/warehouses?branch_id={w['b2'].id}").status_code == 403
    assert _ids(client.login(w['manager']).get(f"/api/warehouses?scope=all&branch_id={w['b2'].id}")) == {w['w2'].id}
    # o'z filiali — ishlaydi
    assert _ids(client.login(w['manager']).get(f"/api/warehouses?branch_id={w['b1'].id}")) == {w['w1'].id}


def test_warehouses_include_inactive(client, world):
    w = world
    assert w['w3'].id not in _ids(client.login(w['admin']).get('/api/warehouses'))
    ids = _ids(client.login(w['admin']).get('/api/warehouses?include_inactive=true'))
    assert ids == {w['w1'].id, w['w2'].id, w['w3'].id}
    rows = client.login(w['admin']).get('/api/warehouses?include_inactive=true').json()
    assert {r['id']: r['is_active'] for r in rows}[w['w3'].id] is False


def test_warehouses_company_isolation(client, world):
    w = world
    assert _ids(client.login(w['other_admin']).get('/api/warehouses?scope=all')) == {w['ow'].id}


# ─── GET /inventory/warehouses ───

def test_inventory_warehouses_fields_and_scope(client, world):
    w = world
    rows = client.login(w['admin']).get('/api/inventory/warehouses?scope=all').json()
    assert {r['id'] for r in rows} == {w['w1'].id, w['w2'].id}
    row = next(r for r in rows if r['id'] == w['w2'].id)
    assert row['branch_id'] == w['b2'].id and row['branch_name'] == 'Chilonzor'
    assert row['is_active'] is True and row['name'] == 'Chilonzor sklad' and 'type' in row
    # kontekst: filialga biriktirilgan xodim faqat o'z filiali
    assert _ids(client.login(w['wh_user']).get('/api/inventory/warehouses')) == {w['w1'].id}
    assert _ids(client.login(w['wh_user']).get('/api/inventory/warehouses?scope=all')) == {w['w1'].id, w['w2'].id}
    assert client.login(w['cashier']).get('/api/inventory/warehouses?scope=all').status_code == 403
    assert client.login(w['admin']).get(f"/api/inventory/warehouses?branch_id={w['ob'].id}").status_code == 404
    assert _ids(client.login(w['admin']).get('/api/inventory/warehouses?include_inactive=true')) >= {w['w3'].id}


# ─── POST /transfers ───

def _transfer(client, user, frm, to, product, qty=5):
    return client.login(user).post('/api/transfers', json={
        'from_warehouse_id': frm.id, 'to_warehouse_id': to.id,
        'items': [{'product_id': product.id, 'quantity': qty}],
        'two_step': False})  # T4.1: filiallararo standart ikki bosqichli; bu testlar bir bosqichli rejimni tekshiradi


def test_transfer_admin_cross_branch_ok(client, world):
    w = world
    assert _transfer(client, w['admin'], w['w1'], w['w2'], w['p']).status_code == 200


def test_transfer_warehouse_role_source_other_branch_403(client, world):
    w = world
    r = _transfer(client, w['wh_user'], w['w2'], w['w1'], w['p'])
    assert r.status_code == 403
    assert r.json()['detail'] == "Bu ombor sizning filialingizga tegishli emas"


def test_transfer_warehouse_role_target_other_branch_ok(client, world, db):
    w = world
    assert _transfer(client, w['wh_user'], w['w1'], w['w2'], w['p'], qty=7).status_code == 200
    q = db.query(StockLevel).filter(StockLevel.product_id == w['p'].id, StockLevel.warehouse_id == w['w2'].id).first()
    assert q.quantity == Decimal(57)


def test_transfer_foreign_company_warehouse_404(client, world):
    w = world
    assert _transfer(client, w['wh_user'], w['w1'], w['ow'], w['p']).status_code == 404
    assert _transfer(client, w['wh_user'], w['ow'], w['w1'], w['p']).status_code == 404


# ─── POST /inventory/receive ───

def _receive(client, user, wh, product, qty=3):
    return client.login(user).post('/api/inventory/receive', json={
        'warehouse_id': wh.id, 'items': [{'product_id': product.id, 'quantity': qty}]})


def test_receive_other_branch_warehouse_403(client, world):
    w = world
    r = _receive(client, w['wh_user'], w['w2'], w['p'])
    assert r.status_code == 403
    assert r.json()['detail'] == "Bu ombor sizning filialingizga tegishli emas"


def test_receive_own_branch_and_admin_ok(client, world):
    w = world
    assert _receive(client, w['wh_user'], w['w1'], w['p']).status_code == 200
    assert _receive(client, w['admin'], w['w2'], w['p']).status_code == 200


def test_receive_foreign_company_warehouse_404(client, world):
    w = world
    assert _receive(client, w['admin'], w['ow'], w['p']).status_code == 404


# ─── GET /inventory/stock ───

def test_stock_levels_branch_scope(client, world):
    w = world
    rows = client.login(w['manager']).get('/api/inventory/stock').json()
    assert {r['warehouse_id'] for r in rows} == {w['w1'].id}
    rows = client.login(w['admin']).get('/api/inventory/stock').json()
    assert {r['warehouse_id'] for r in rows} == {w['w1'].id, w['w2'].id}
    rows = client.login(w['admin']).get(f"/api/inventory/stock?branch_id={w['b2'].id}").json()
    assert {r['warehouse_id'] for r in rows} == {w['w2'].id}
    # non-bypass uchun ruxsatsiz branch_id e'tiborsiz — baribir faqat o'z filiali
    rows = client.login(w['manager']).get(f"/api/inventory/stock?branch_id={w['b2'].id}").json()
    assert {r['warehouse_id'] for r in rows} == {w['w1'].id}


def test_stock_levels_company_isolation(client, world):
    w = world
    assert client.login(w['other_admin']).get('/api/inventory/stock').json() == []


# ─── Xarid buyurtmalari ───

def _po(client, user, wh, supplier, product):
    return client.login(user).post('/api/purchase-orders', json={
        'supplier_id': supplier.id, 'warehouse_id': wh.id,
        'items': [{'product_id': product.id, 'qty_ordered': 2, 'unit_cost': 1000}]})


def test_po_list_branch_scope_and_branch_column(client, world, db):
    w = world
    sup = _supplier(db, w['a'])
    po1 = _po(client, w['admin'], w['w1'], sup, w['p'])
    po2 = _po(client, w['admin'], w['w2'], sup, w['p'])
    assert po1.status_code == 200 and po2.status_code == 200, (po1.text, po2.text)
    rows = client.login(w['manager']).get('/api/purchase-orders').json()
    assert [r['id'] for r in rows] == [po1.json()['id']]
    assert rows[0]['branch_name'] == 'Asosiy' and rows[0]['branch_id'] == w['b1'].id
    assert rows[0]['warehouse_id'] == w['w1'].id
    rows = client.login(w['admin']).get('/api/purchase-orders').json()
    assert {r['branch_name'] for r in rows} == {'Asosiy', 'Chilonzor'}
    rows = client.login(w['admin']).get(f"/api/purchase-orders?branch_id={w['b2'].id}").json()
    assert [r['id'] for r in rows] == [po2.json()['id']]


def test_po_list_company_isolation(client, world, db):
    w = world
    sup = _supplier(db, w['a'])
    assert _po(client, w['admin'], w['w1'], sup, w['p']).status_code == 200
    assert client.login(w['other_admin']).get('/api/purchase-orders').json() == []


def test_po_create_other_branch_warehouse_403_for_manager(client, world, db):
    w = world
    sup = _supplier(db, w['a'])
    assert _po(client, w['manager'], w['w2'], sup, w['p']).status_code == 403
    assert _po(client, w['manager'], w['w1'], sup, w['p']).status_code == 200


def test_po_patch_move_to_other_branch(client, world, db):
    w = world
    sup = _supplier(db, w['a'])
    po_id = _po(client, w['manager'], w['w1'], sup, w['p']).json()['id']
    # non-bypass: boshqa filial omboriga ko'chirish — 403, xarid joyida qoladi
    r = client.login(w['manager']).patch(f'/api/purchase-orders/{po_id}', json={'warehouse_id': w['w2'].id})
    assert r.status_code == 403
    assert r.json()['detail'] == "Bu ombor sizning filialingizga tegishli emas"
    assert db.get(PurchaseOrder, po_id).warehouse_id == w['w1'].id
    # admin ko'chira oladi
    r = client.login(w['admin']).patch(f'/api/purchase-orders/{po_id}', json={'warehouse_id': w['w2'].id})
    assert r.status_code == 200, r.text
    assert r.json()['warehouse_id'] == w['w2'].id
    # endi manager (b1) bu xaridni tahrirlay olmaydi (boshqa filial ombori)
    r = client.login(w['manager']).patch(f'/api/purchase-orders/{po_id}', json={'note': 'x'})
    assert r.status_code == 403


def test_po_patch_same_branch_ok_and_foreign_company_404(client, world, db, mk):
    w = world
    sup = _supplier(db, w['a'])
    other_wh = mk.warehouse(w['a'], w['b1'], name='Ikkinchi sklad')
    po_id = _po(client, w['manager'], w['w1'], sup, w['p']).json()['id']
    r = client.login(w['manager']).patch(f'/api/purchase-orders/{po_id}', json={'warehouse_id': other_wh.id})
    assert r.status_code == 200, r.text
    # begona korxona xaridi / ombori
    assert client.login(w['other_admin']).patch(f'/api/purchase-orders/{po_id}', json={'note': 'x'}).status_code == 404
    assert client.login(w['admin']).patch(f'/api/purchase-orders/{po_id}', json={'warehouse_id': w['ow'].id}).status_code == 404


# ─── servis darajasi ───

def test_assert_warehouse_branch_access_unit(db, mk):
    from fastapi import HTTPException
    from app.core.branch_context import build_branch_context
    from app.services.warehouse_access import assert_warehouse_branch_access

    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    w1, w2 = mk.warehouse(c, b1), mk.warehouse(c, b2)
    orphan = mk.warehouse(c, None)
    u = mk.user(c, UserRole.warehouse, branch=b1)
    admin = mk.user(c, UserRole.admin, branch=b1)
    ctx = build_branch_context(db, u)
    assert assert_warehouse_branch_access(db, u, ctx, w1.id).id == w1.id
    assert assert_warehouse_branch_access(db, u, ctx, w2.id, as_transfer_target=True).id == w2.id
    for wid in (w2.id, orphan.id):
        with pytest.raises(HTTPException) as e:
            assert_warehouse_branch_access(db, u, ctx, wid)
        assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        assert_warehouse_branch_access(db, u, ctx, 99999, as_transfer_target=True)
    assert e.value.status_code == 404
    assert assert_warehouse_branch_access(db, admin, build_branch_context(db, admin), w2.id).id == w2.id
