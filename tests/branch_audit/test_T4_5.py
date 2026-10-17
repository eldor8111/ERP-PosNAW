"""T4.5 — Ma'lumotlarni filialga import va ko'chirish.

Qamrov: mahsulot importida qator bo'yicha "Ombor" ustuni (ikki omborda alohida stock_levels qatori,
topilmagan nom faqat shu qator xatosi, boshqa filial ombori 403), bulk-check `stock_will_change`,
mijoz importida `branch_id` parametri va "Filial" ustuni (rol/filial ruxsati), `POST /branches/reassign`
(300 mijoz, begona ID -> 404 va hech narsa o'zgarmaydi, ochiq smenali kassa va snapshotsiz ombor -> 409,
audit), `PATCH /warehouses/{id}` (`branch_id=null` ajratadi, `name=null` rad etiladi),
`POST /kassa/bulk` (Wallet + KassaMovement(opening)), ikki korxona izolyatsiyasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T4_5.py -q -p no:cacheprovider
"""
import itertools
import json
import os
import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.customer import Customer
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.moliya import KassaMovement, Wallet
from app.models.product import Product
from app.models.sale import PaymentType, Sale
from app.models.user import User, UserRole
from app.models.user_company import UserCompany
from app.models.warehouse import Warehouse

# SQLite Integer ustuniga (products.min_stock) Decimal bog'lab bo'lmaydi — faqat test muhiti uchun adapter
sqlite3.register_adapter(Decimal, lambda d: int(d) if d == d.to_integral_value() else float(d))

IMPORT_URL = '/api/products/bulk-import'
CHECK_URL = '/api/products/bulk-check'
CUST_IMPORT_URL = '/api/customers/bulk-import'
REASSIGN_URL = '/api/branches/reassign'
_seq = itertools.count(1)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _product(db, company, name):
    p = Product(name=name, sku=f'S45-{name}', barcode=f'B45-{name}', company_id=company.id,
                cost_price=Decimal('1000'), sale_price=Decimal('1500'), images='[]')
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty):
    sl = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=Decimal(str(qty)))
    db.add(sl)
    db.flush()
    return sl


def _levels(db, product):
    return {r.warehouse_id: Decimal(str(r.quantity))
            for r in db.query(StockLevel).filter(StockLevel.product_id == product.id).all()}


def _movements(db, product):
    return db.query(StockMovement).filter(StockMovement.product_id == product.id).all()


def _customer(db, company, name=None, branch=None):
    n = next(_seq)
    c = Customer(name=name or f'Mijoz {n}', phone=f'9015{n:06d}', company_id=company.id,
                 branch_id=branch.id if branch else None)
    db.add(c)
    db.flush()
    return c


def _wallet(db, company, branch=None, name=None, is_open=False, balance='0'):
    w = Wallet(name=name or f'Kassa {next(_seq)}', type='cash', balance=Decimal(balance),
               company_id=company.id, branch_id=branch.id if branch else None, is_open=is_open)
    db.add(w)
    db.flush()
    return w


@pytest.fixture
def world(mk):
    """A korxona: 2 filial (a1, a2), har birida ombor; admin. B korxona: bitta filial + admin."""
    ca = mk.company()
    a1, a2 = mk.branch(ca, name='Chilonzor'), mk.branch(ca, name='Yunusobod')
    w1 = mk.warehouse(ca, a1, name='Asosiy ombor')
    w2 = mk.warehouse(ca, a2, name='Chilonzor ombori')
    admin = mk.user(ca, role=UserRole.admin)
    cb, bb, wb, adminb = mk.tenant()
    return dict(ca=ca, a1=a1, a2=a2, w1=w1, w2=w2, admin=admin, cb=cb, bb=bb, wb=wb, adminb=adminb)


# ══════════════════════════ Mahsulot importi: "Ombor" ustuni ══════════════════════════

def test_product_import_row_warehouse_column_two_warehouses(db, mk, client, world):
    w = world
    p = _product(db, w['ca'], 'Tovar')
    q = _product(db, w['ca'], 'Boshqa')
    _stock(db, p, w['w1'], 40)
    _stock(db, q, w['w1'], 11)

    rows = [
        {'Nomi': 'Tovar', 'Qoldiq': 100, 'Ombor': 'Chilonzor ombori'},
        {'Nomi': 'Tovar', 'Qoldiq': 7, 'Ombor': 'asosiy OMBOR'},         # katta-kichik harfsiz
        {'Nomi': 'Boshqa', 'Qoldiq': 5, 'Ombor': 'Chilonzor ombori'},
    ]
    r = client.login(w['admin']).post(f'{IMPORT_URL}?allow_update=true', json=rows)
    assert r.status_code == 200, r.text
    assert r.json()['updated'] == 3 and r.json()['errors'] == [], r.json()

    # Bir mahsulot ikki omborda alohida qatorlar; Asosiy ombor faqat o'z qatori bo'yicha o'zgargan
    assert _levels(db, p) == {w['w1'].id: Decimal('7'), w['w2'].id: Decimal('100')}
    assert _levels(db, q) == {w['w1'].id: Decimal('11'), w['w2'].id: Decimal('5')}
    mv = sorted(_movements(db, p), key=lambda m: m.id)
    assert [(m.warehouse_id, m.type, m.reference_type) for m in mv] == [
        (w['w2'].id, MovementType.ADJUST, 'product_import'),
        (w['w1'].id, MovementType.ADJUST, 'product_import'),
    ]
    assert Decimal(str(mv[0].qty_before)) == 0 and Decimal(str(mv[0].qty_after)) == 100
    assert Decimal(str(mv[1].qty_before)) == 40 and Decimal(str(mv[1].qty_after)) == 7


def test_product_import_column_overrides_query_param_and_new_product_gets_batch(db, mk, client, world):
    w = world
    r = client.login(w['admin']).post(
        f"{IMPORT_URL}?warehouse_id={w['w1'].id}",
        json=[{'Nomi': 'Yangi A', 'Qoldiq': 9, 'Tan narxi': 1200, 'Ombor': 'Chilonzor ombori'},
              {'Nomi': 'Yangi B', 'Qoldiq': 4, 'Tan narxi': 800}],      # ustun yo'q -> so'rov parametri
    )
    assert r.status_code == 200, r.text
    assert r.json()['created'] == 2, r.json()
    a = db.query(Product).filter(Product.name == 'Yangi A', Product.company_id == w['ca'].id).one()
    b = db.query(Product).filter(Product.name == 'Yangi B', Product.company_id == w['ca'].id).one()
    assert _levels(db, a) == {w['w2'].id: Decimal('9')}
    assert _levels(db, b) == {w['w1'].id: Decimal('4')}
    batch = db.query(Batch).filter(Batch.product_id == a.id).one()
    assert batch.warehouse_id == w['w2'].id and Decimal(str(batch.purchase_price)) == Decimal('1200')
    mv = _movements(db, a)
    assert len(mv) == 1 and mv[0].type == MovementType.IN and mv[0].warehouse_id == w['w2'].id


def test_product_import_unknown_warehouse_name_is_row_error_only(db, mk, client, world):
    w = world
    rows = [
        {'Nomi': 'Yaxshi 1', 'Qoldiq': 3, 'Ombor': 'Chilonzor ombori'},
        {'Nomi': 'Yomon', 'Qoldiq': 3, 'Ombor': 'Yo`q ombor'},
        {'Nomi': 'Begona', 'Qoldiq': 3, 'Ombor': w['wb'].name},          # boshqa korxona ombori nomi
        {'Nomi': 'Yaxshi 2', 'Qoldiq': 2, 'Ombor': 'Asosiy ombor'},
    ]
    r = client.login(w['admin']).post(IMPORT_URL, json=rows)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['created'] == 2, body
    assert sorted(e['row'] for e in body['errors']) == [3, 4]
    assert all('Ombor topilmadi' in e['error'] for e in body['errors'])
    names = {p.name for p in db.query(Product).filter(Product.company_id == w['ca'].id)}
    assert names == {'Yaxshi 1', 'Yaxshi 2'}


def test_product_import_foreign_or_missing_warehouse_id_rejected(db, mk, client, world):
    w = world
    before = db.query(Product).filter(Product.company_id == w['ca'].id).count()
    for bad in (w['wb'].id, 999999):
        r = client.login(w['admin']).post(f'{IMPORT_URL}?warehouse_id={bad}',
                                          json=[{'Nomi': 'Hech qachon', 'Qoldiq': 5}])
        assert r.status_code in (400, 404), r.text            # jim birinchi omborga yozilmaydi
    assert db.query(Product).filter(Product.company_id == w['ca'].id).count() == before
    assert db.query(StockLevel).count() == 0


def test_product_import_non_admin_cannot_use_other_branch_warehouse(db, mk, client, world):
    w = world
    p = _product(db, w['ca'], 'Tovar')
    wh_user = mk.user(w['ca'], role=UserRole.warehouse, branch=w['a1'])
    cl = client.login(wh_user)
    # so'rov parametri: boshqa filial ombori -> 403
    r = cl.post(f"{IMPORT_URL}?warehouse_id={w['w2'].id}&allow_update=true",
                json=[{'Nomi': 'Tovar', 'Qoldiq': 5}])
    assert r.status_code == 403, r.text
    # ustun: boshqa filial ombori -> faqat shu qator xatosi, o'z filiali ombori ishlaydi
    r = cl.post(f"{IMPORT_URL}?warehouse_id={w['w1'].id}&allow_update=true", json=[
        {'Nomi': 'Tovar', 'Qoldiq': 5, 'Ombor': 'Chilonzor ombori'},
        {'Nomi': 'Tovar', 'Qoldiq': 6, 'Ombor': 'Asosiy ombor'},
    ])
    assert r.status_code == 200, r.text
    assert r.json()['updated'] == 1 and len(r.json()['errors']) == 1
    assert 'ruxsat' in r.json()['errors'][0]['error']
    assert _levels(db, p) == {w['w1'].id: Decimal('6')}


def test_bulk_check_stock_will_change_and_warehouse_validation(db, mk, client, world):
    w = world
    p, q, new_unused = _product(db, w['ca'], 'A'), _product(db, w['ca'], 'B'), None
    _stock(db, p, w['w1'], 10)
    _stock(db, q, w['w2'], 5)
    rows = [
        {'Nomi': 'A', 'Qoldiq': 10},                         # Asosiy omborda bir xil -> o'zgarmaydi
        {'Nomi': 'B', 'Qoldiq': 5, 'Ombor': 'Chilonzor ombori'},   # bir xil -> o'zgarmaydi
        {'Nomi': 'B', 'Qoldiq': 5},                          # Asosiy omborda yo'q (0 -> 5) -> o'zgaradi
        {'Nomi': 'A', 'Qoldiq': 99, 'Ombor': 'Chilonzor ombori'},  # Chilonzorda yo'q -> o'zgaradi
        {'Nomi': 'Yangi', 'Qoldiq': 3},                      # yangi
    ]
    cl = client.login(w['admin'])
    r = cl.post(f"{CHECK_URL}?warehouse_id={w['w1'].id}", json=rows)
    assert r.status_code == 200, r.text
    assert r.json() == {'found_count': 4, 'new_count': 1, 'stock_will_change': 2}
    # begona korxona ombori -> rad etiladi
    r = cl.post(f"{CHECK_URL}?warehouse_id={w['wb'].id}", json=rows)
    assert r.status_code in (400, 404), r.text


# ══════════════════════════ Mijoz importi: filial ══════════════════════════

def test_customer_import_default_branch_and_filial_column(db, mk, client, world):
    w = world
    rows = [
        {'Ism': 'Birinchi', 'Telefon': '901000001'},                       # default filial
        {'Ism': 'Ikkinchi', 'Telefon': '901000002', 'Filial': 'yunusobod'},  # ustun ustun
        {'Ism': 'Uchinchi', 'Telefon': '901000003', 'Filial': 'Yo`q filial'},  # faqat shu qator xato
        {'Ism': 'To`rtinchi', 'Telefon': '901000004', 'Filial': w['bb'].name},  # begona korxona filiali
    ]
    r = client.login(w['admin']).post(f"{CUST_IMPORT_URL}?branch_id={w['a1'].id}", json=rows)
    assert r.status_code == 200, r.text
    assert r.json()['created'] == 2 and len(r.json()['errors']) == 2, r.json()
    got = {c.name: c.branch_id for c in db.query(Customer).filter(Customer.company_id == w['ca'].id)}
    assert got == {'Birinchi': w['a1'].id, 'Ikkinchi': w['a2'].id}

    # allow_update: default filial mavjud mijozga ham qo'llanadi
    r = client.login(w['admin']).post(
        f"{CUST_IMPORT_URL}?branch_id={w['a2'].id}&allow_update=true",
        json=[{'Ism': 'Birinchi', 'Telefon': '901000001'}])
    assert r.json()['updated'] == 1
    assert db.query(Customer).filter(Customer.name == 'Birinchi').one().branch_id == w['a2'].id


def test_customer_import_foreign_branch_id_404_and_nothing_created(db, mk, client, world):
    w = world
    r = client.login(w['admin']).post(f"{CUST_IMPORT_URL}?branch_id={w['bb'].id}",
                                      json=[{'Ism': 'Begona', 'Telefon': '901000009'}])
    assert r.status_code == 404, r.text
    assert db.query(Customer).filter(Customer.company_id == w['ca'].id).count() == 0


def test_customer_import_role_and_branch_permissions(db, mk, client, world):
    w = world
    manager = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    cashier = mk.user(w['ca'], role=UserRole.cashier, branch=w['a1'])
    cl = client.login(manager)
    # menejer: boshqa filialga -> 403; o'z filialiga -> ok
    r = cl.post(f"{CUST_IMPORT_URL}?branch_id={w['a2'].id}", json=[{'Ism': 'X', 'Telefon': '901000011'}])
    assert r.status_code == 403, r.text
    r = cl.post(f"{CUST_IMPORT_URL}?branch_id={w['a1'].id}", json=[{'Ism': 'Mening', 'Telefon': '901000012'}])
    assert r.status_code == 200 and r.json()['created'] == 1, r.text
    # ustun orqali boshqa filial -> shu qator xatosi
    r = cl.post(CUST_IMPORT_URL, json=[{'Ism': 'Ustun', 'Telefon': '901000013', 'Filial': 'Yunusobod'},
                                       {'Ism': 'Ustun2', 'Telefon': '901000014', 'Filial': 'Chilonzor'}])
    assert r.json()['created'] == 1 and len(r.json()['errors']) == 1, r.json()
    # kassir: filial belgilay olmaydi
    r = client.login(cashier).post(f"{CUST_IMPORT_URL}?branch_id={w['a1'].id}",
                                   json=[{'Ism': 'Kassir', 'Telefon': '901000015'}])
    assert r.status_code == 403, r.text
    # kassir filialsiz import qila oladi (eski xatti-harakat saqlanadi)
    r = client.login(cashier).post(CUST_IMPORT_URL, json=[{'Ism': 'Kassir 2', 'Telefon': '901000016'}])
    assert r.status_code == 200 and r.json()['created'] == 1, r.text


# ══════════════════════════ POST /branches/reassign ══════════════════════════

def test_reassign_300_customers(db, mk, client, world):
    w = world
    custs = [_customer(db, w['ca'], branch=w['a1']) for _ in range(300)]
    ids = [c.id for c in custs]
    r = client.login(w['admin']).post(REASSIGN_URL, json={'entity': 'customers', 'ids': ids, 'to_branch_id': w['a2'].id})
    assert r.status_code == 200, r.text
    assert r.json()['updated'] == 300 and r.json()['skipped'] == []
    db.expire_all()
    assert db.query(Customer).filter(Customer.id.in_(ids), Customer.branch_id == w['a2'].id).count() == 300

    # takroriy chaqiruv: hammasi allaqachon shu filialda -> skipped
    r = client.login(w['admin']).post(REASSIGN_URL, json={'entity': 'customers', 'ids': ids[:3], 'to_branch_id': w['a2'].id})
    assert r.json()['updated'] == 0 and len(r.json()['skipped']) == 3

    # audit: BULK_REASSIGN, ids va eski/yangi filial bilan
    log = db.query(AuditLog).filter(AuditLog.action == 'BULK_REASSIGN', AuditLog.entity_type == 'customers').first()
    assert log is not None and log.company_id == w['ca'].id
    assert log.new_values['to_branch_id'] == w['a2'].id and log.new_values['updated'] == 300
    assert log.old_values['branch_ids'][str(ids[0])] == w['a1'].id and len(log.old_values['branch_ids']) == 300 and log.old_values['count'] == 300


def test_reassign_foreign_id_404_and_nothing_changes(db, mk, client, world):
    w = world
    mine = [_customer(db, w['ca'], branch=w['a1']) for _ in range(3)]
    foreign = _customer(db, w['cb'])
    r = client.login(w['admin']).post(REASSIGN_URL, json={
        'entity': 'customers', 'ids': [c.id for c in mine] + [foreign.id], 'to_branch_id': w['a2'].id})
    assert r.status_code == 404, r.text
    db.expire_all()
    assert all(db.get(Customer, c.id).branch_id == w['a1'].id for c in mine)
    assert db.get(Customer, foreign.id).branch_id is None
    assert db.query(AuditLog).filter(AuditLog.action == 'BULK_REASSIGN').count() == 0


def test_reassign_isolation_target_branch_and_roles(db, mk, client, world):
    w = world
    c = _customer(db, w['ca'], branch=w['a1'])
    # begona korxona filialiga ko'chirish -> 404
    r = client.login(w['admin']).post(REASSIGN_URL, json={'entity': 'customers', 'ids': [c.id], 'to_branch_id': w['bb'].id})
    assert r.status_code == 404, r.text
    # B korxona admini A mijozini ko'chira olmaydi
    r = client.login(w['adminb']).post(REASSIGN_URL, json={'entity': 'customers', 'ids': [c.id], 'to_branch_id': w['bb'].id})
    assert r.status_code == 404, r.text
    # null faqat omborlar uchun
    r = client.login(w['admin']).post(REASSIGN_URL, json={'entity': 'customers', 'ids': [c.id], 'to_branch_id': None})
    assert r.status_code == 400, r.text
    # 1000 dan ortiq id
    r = client.login(w['admin']).post(REASSIGN_URL, json={'entity': 'customers', 'ids': list(range(1, 1002)),
                                                          'to_branch_id': w['a2'].id})
    assert r.status_code == 422, r.text
    # rol: menejer ruxsatsiz
    manager = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    r = client.login(manager).post(REASSIGN_URL, json={'entity': 'customers', 'ids': [c.id], 'to_branch_id': w['a2'].id})
    assert r.status_code == 403, r.text
    assert db.get(Customer, c.id).branch_id == w['a1'].id


def test_reassign_users_updates_membership_and_skips_super_admin(db, mk, client, world):
    w = world
    u1 = mk.user(w['ca'], role=UserRole.cashier, branch=w['a1'])
    u2 = mk.user(w['ca'], role=UserRole.manager, branch=w['a1'])
    sa = mk.user(w['ca'], role=UserRole.super_admin)
    db.add(UserCompany(user_id=u1.id, company_id=w['ca'].id, role=UserRole.cashier, branch_id=w['a1'].id))
    db.flush()
    r = client.login(w['admin']).post(REASSIGN_URL, json={
        'entity': 'users', 'ids': [u1.id, u2.id, sa.id], 'to_branch_id': w['a2'].id})
    assert r.status_code == 200, r.text
    assert r.json()['updated'] == 2
    assert [s['id'] for s in r.json()['skipped']] == [sa.id]
    db.expire_all()
    assert db.get(User, u1.id).branch_id == w['a2'].id and db.get(User, u2.id).branch_id == w['a2'].id
    uc = db.query(UserCompany).filter(UserCompany.user_id == u1.id).one()
    assert uc.branch_id == w['a2'].id
    assert db.get(User, sa.id).branch_id is None
    # begona korxona xodimi -> 404
    ub = mk.user(w['cb'], role=UserRole.cashier, branch=w['bb'])
    r = client.login(w['admin']).post(REASSIGN_URL, json={'entity': 'users', 'ids': [u1.id, ub.id], 'to_branch_id': w['a1'].id})
    assert r.status_code == 404, r.text
    assert db.get(User, u1.id).branch_id == w['a2'].id


def test_reassign_self_gives_warning(db, mk, client, world):
    w = world
    me = mk.user(w['ca'], role=UserRole.admin, branch=w['a1'])
    r = client.login(me).post(REASSIGN_URL, json={'entity': 'users', 'ids': [me.id], 'to_branch_id': w['a2'].id})
    assert r.status_code == 200 and r.json()['updated'] == 1, r.text
    assert r.json()['warnings']


def test_reassign_wallets_open_shift_409_and_closed_ok(db, mk, client, world):
    w = world
    closed = _wallet(db, w['ca'], w['a1'], name='Yopiq')
    opened = _wallet(db, w['ca'], w['a1'], name='Ochiq', is_open=True)
    cl = client.login(w['admin'])
    r = cl.post(REASSIGN_URL, json={'entity': 'wallets', 'ids': [closed.id, opened.id], 'to_branch_id': w['a2'].id})
    assert r.status_code == 409, r.text
    db.expire_all()
    assert db.get(Wallet, closed.id).branch_id == w['a1'].id and db.get(Wallet, opened.id).branch_id == w['a1'].id
    r = cl.post(REASSIGN_URL, json={'entity': 'wallets', 'ids': [closed.id], 'to_branch_id': w['a2'].id})
    assert r.status_code == 200 and r.json()['updated'] == 1, r.text
    assert db.get(Wallet, closed.id).branch_id == w['a2'].id
    # begona kassa -> 404
    wb_wallet = _wallet(db, w['cb'], w['bb'])
    assert cl.post(REASSIGN_URL, json={'entity': 'wallets', 'ids': [wb_wallet.id], 'to_branch_id': w['a2'].id}).status_code == 404


def test_reassign_warehouse_needs_sale_snapshot_409_then_ok(db, mk, client, world):
    w = world
    wh = mk.warehouse(w['ca'], w['a1'], name='Ko`chadigan')
    s = Sale(number='S-T45-1', cashier_id=w['admin'].id, total_amount=Decimal('100'), paid_amount=Decimal('100'),
             payment_type=PaymentType.cash, company_id=w['ca'].id, warehouse_id=wh.id)
    db.add(s)
    db.flush()
    assert s.branch_id == w['a1'].id                           # snapshot to'ldirildi
    db.execute(text('UPDATE sales SET branch_id = NULL WHERE id = :i'), {'i': s.id})
    cl = client.login(w['admin'])
    r = cl.post(REASSIGN_URL, json={'entity': 'warehouses', 'ids': [wh.id], 'to_branch_id': w['a2'].id})
    assert r.status_code == 409, r.text
    assert 'snapshot' in r.json()['detail']
    db.expire_all()
    assert db.get(Warehouse, wh.id).branch_id == w['a1'].id
    # snapshot bor bo'lsa ko'chadi
    db.execute(text('UPDATE sales SET branch_id = :b WHERE id = :i'), {'b': w['a1'].id, 'i': s.id})
    r = cl.post(REASSIGN_URL, json={'entity': 'warehouses', 'ids': [wh.id], 'to_branch_id': w['a2'].id})
    assert r.status_code == 200 and r.json()['updated'] == 1, r.text
    db.expire_all()
    assert db.get(Warehouse, wh.id).branch_id == w['a2'].id
    assert db.get(Sale, s.id).branch_id == w['a1'].id          # o'tmishdagi sotuv filiali o'zgarmadi
    # filialdan ajratish (null) ruxsat
    r = cl.post(REASSIGN_URL, json={'entity': 'warehouses', 'ids': [wh.id], 'to_branch_id': None})
    assert r.status_code == 200 and r.json()['updated'] == 1, r.text
    db.expire_all()
    assert db.get(Warehouse, wh.id).branch_id is None
    # begona ombor -> 404
    assert cl.post(REASSIGN_URL, json={'entity': 'warehouses', 'ids': [w['wb'].id], 'to_branch_id': w['a2'].id}).status_code == 404


# ══════════════════════════ PATCH /warehouses/{id} ══════════════════════════

def test_warehouse_detach_and_reject_null_required_fields(db, mk, client, world):
    w = world
    wh = mk.warehouse(w['ca'], w['a1'], name='Ajratiladi')
    cl = client.login(w['admin'])
    r = cl.patch(f'/api/warehouses/{wh.id}', json={'name': None})
    assert r.status_code in (400, 422), r.text
    r = cl.patch(f'/api/warehouses/{wh.id}', json={'is_active': None})
    assert r.status_code in (400, 422), r.text
    db.expire_all()
    got = db.get(Warehouse, wh.id)
    assert got.name == 'Ajratiladi' and got.is_active is True and got.branch_id == w['a1'].id

    r = cl.patch(f'/api/warehouses/{wh.id}', json={'branch_id': None})
    assert r.status_code == 200, r.text
    assert r.json()['branch_id'] is None
    db.expire_all()
    assert db.get(Warehouse, wh.id).branch_id is None
    # name yuborilmasa boshqa maydonlar o'zgarmaydi
    assert db.get(Warehouse, wh.id).name == 'Ajratiladi'

    # begona korxona filiali / begona korxona ombori
    assert cl.patch(f'/api/warehouses/{wh.id}', json={'branch_id': w['bb'].id}).status_code in (400, 404)
    assert cl.patch(f"/api/warehouses/{w['wb'].id}", json={'branch_id': None}).status_code == 404
    assert db.get(Warehouse, w['wb'].id).branch_id == w['bb'].id


# ══════════════════════════ POST /kassa/bulk ══════════════════════════

def test_kassa_bulk_creates_wallets_with_opening_movements(db, mk, client, world):
    w = world
    existing = _wallet(db, w['ca'], w['a1'], name='Mavjud', balance='777')
    body = [
        {'name': 'Chilonzor kassa', 'type': 'cash', 'currency': 'UZS', 'branch_id': w['a1'].id, 'opening_balance': 150000},
        {'name': 'Yunusobod kassa', 'type': 'cash', 'currency': 'UZS', 'branch_id': w['a2'].id, 'opening_balance': 0},
        {'name': 'Begona filial', 'type': 'cash', 'branch_id': w['bb'].id, 'opening_balance': 10},
        {'name': '  ', 'type': 'cash', 'branch_id': w['a1'].id},
    ]
    r = client.login(w['admin']).post('/api/kassa/bulk', json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out['created'] == 2 and sorted(e['row'] for e in out['errors']) == [3, 4], out

    wa = db.query(Wallet).filter(Wallet.name == 'Chilonzor kassa').one()
    assert wa.branch_id == w['a1'].id and wa.company_id == w['ca'].id
    assert Decimal(str(wa.balance)) == Decimal('150000') and Decimal(str(wa.opening_balance)) == Decimal('150000')
    mv = db.query(KassaMovement).filter(KassaMovement.wallet_id == wa.id).all()
    assert len(mv) == 1 and mv[0].reference_type == 'opening' and mv[0].direction == 'in'
    assert Decimal(str(mv[0].amount)) == Decimal('150000')
    wb_ = db.query(Wallet).filter(Wallet.name == 'Yunusobod kassa').one()
    assert wb_.branch_id == w['a2'].id and db.query(KassaMovement).filter(KassaMovement.wallet_id == wb_.id).count() == 0
    assert db.query(Wallet).filter(Wallet.name == 'Begona filial').count() == 0
    # mavjud kassa balansi o'zgarmaydi
    db.expire_all()
    assert Decimal(str(db.get(Wallet, existing.id).balance)) == Decimal('777')


def test_kassa_bulk_limits_and_roles(db, mk, client, world):
    w = world
    cl = client.login(w['admin'])
    assert cl.post('/api/kassa/bulk', json=[]).status_code == 400
    many = [{'name': f'K{i}', 'type': 'cash', 'branch_id': w['a1'].id} for i in range(101)]
    assert cl.post('/api/kassa/bulk', json=many).status_code == 400
    assert db.query(Wallet).filter(Wallet.company_id == w['ca'].id).count() == 0
    cashier = mk.user(w['ca'], role=UserRole.cashier, branch=w['a1'])
    r = client.login(cashier).post('/api/kassa/bulk', json=[{'name': 'X', 'type': 'cash', 'branch_id': w['a1'].id}])
    assert r.status_code == 403, r.text


# ══════════════════════════ Frontend i18n (pending) ══════════════════════════

def test_pending_i18n_keys_consistent_and_used():
    path = os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T4.5.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en']) and data['uz']
    assert all(str(v).strip() for lang in data.values() for v in lang.values())
    src = ''
    for rel in ('Customers.jsx', 'Filiallar.jsx', 'Ombor.jsx', 'Products.jsx'):
        with open(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', rel), encoding='utf-8') as f:
            src += f.read()
    missing = [k for k in data['uz'] if k not in src]
    assert not missing, missing
