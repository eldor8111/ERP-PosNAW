"""T1.19 — Ombor va moliya operatsiyalari auditi.

Qamrov: log_action/log_action_for company_id/branch_id, GET /audit-logs (izolyatsiya, rol, sahifalash),
transfer cancel/DELETE storno (harakatlar o'chmaydi), revizya revert storno va completed o'chirish 400,
chiqim bekor qilish (storno + takror 400), qaytarishni bekor qilish idempotentligi, sotuv o'chirishda storno,
kassa va Moliya xarajati / tranzaksiyasini void qilish (hamyon, ro'yxat, kassa balansi, cash-balance),
Transaction.user_id, ombor/filial/smena/kassa/ishlab chiqarish auditi.
"""
import itertools
from datetime import datetime
from decimal import Decimal

from app.core.audit import log_action, log_action_for
from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.customer import Customer
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.inventory_count import CountStatus, InventoryCount
from app.models.moliya import (
    Expense, ExpenseCategory, KassaMovement, Transaction, Wallet,
)
from app.models.product import Product
from app.models.transfer import StockTransfer, TransferStatus
from app.models.user import UserRole

_seq = itertools.count(1)


# ─── yordamchilar ───

def _product(db, company, name=None):
    n = next(_seq)
    p = Product(name=name or f'Mahsulot {n}', sku=f'SKU-T119-{n}', barcode=f'BC-T119-{n}',
                company_id=company.id, cost_price=0, sale_price=0, product_type='simple')
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
        StockLevel.product_id == product.id, StockLevel.warehouse_id == warehouse.id,
        StockLevel.variant_id.is_(None),
    ).first()
    return float(s.quantity) if s else None


def _audit(db, action, entity_id=None):
    q = db.query(AuditLog).filter(AuditLog.action == action)
    if entity_id is not None:
        q = q.filter(AuditLog.entity_id == entity_id)
    return q.all()


def _tenant(db, mk, qty=100):
    """Korxona: wh1 (mahsulot `qty` dona), wh2, admin."""
    c, b, wh1, u = mk.tenant()
    wh2 = mk.warehouse(c, b, name='Yunusobod')
    p = _product(db, c, name='Sut')
    _stock(db, p, wh1, qty)
    return dict(c=c, b=b, wh1=wh1, wh2=wh2, p=p, u=u)


def _wallet(db, company, branch, balance=1000, is_open=True):
    w = Wallet(name='Asosiy kassa', type='cash', company_id=company.id, branch_id=branch.id,
               balance=Decimal(balance), is_open=is_open, is_active=True)
    db.add(w)
    db.flush()
    return w


def _category(db, company):
    cat = ExpenseCategory(name='Ijara', company_id=company.id)
    db.add(cat)
    db.flush()
    return cat


# ─── 1. log_action / log_action_for ───

def test_log_action_for_fills_company_and_branch(db, mk):
    c, b, wh, u = mk.tenant()
    log_action_for(db, u, 'TEST_ACTION', 'thing', 5, new_values={'a': 1})
    log = _audit(db, 'TEST_ACTION')[0]
    assert (log.company_id, log.branch_id, log.user_id, log.entity_id) == (c.id, b.id, u.id, 5)

    # aniq branch_id ustun turadi
    other = mk.branch(c)
    log_action_for(db, u, 'TEST_ACTION2', 'thing', 6, branch_id=other.id)
    assert _audit(db, 'TEST_ACTION2')[0].branch_id == other.id


def test_log_action_derives_company_from_user_id(db, mk):
    c, b, wh, u = mk.tenant()
    log_action(db, 'OLD_STYLE', 'thing', 1, user_id=u.id)          # eski imzo ishlayveradi
    log = _audit(db, 'OLD_STYLE')[0]
    assert log.company_id == c.id and log.branch_id == b.id
    # aniq company_id/branch_id berilsa — foydalanuvchidan olinmaydi
    c2 = mk.company()
    log_action(db, 'EXPLICIT', 'thing', 1, user_id=u.id, company_id=c2.id)
    assert _audit(db, 'EXPLICIT')[0].company_id == c2.id


def test_log_action_trims_long_lists(db, mk):
    c, b, wh, u = mk.tenant()
    log_action_for(db, u, 'BIG', 'thing', 1, new_values={'items': [{'i': i} for i in range(80)]})
    items = _audit(db, 'BIG')[0].new_values['items']
    assert len(items) == 51 and items[-1] == {'_truncated': 30}


# ─── 2. GET /audit-logs ───

def test_audit_logs_company_isolation_and_positive(client, db, mk):
    a = mk.tenant()
    bb = mk.tenant()
    log_action_for(db, a[3], 'A_ACTION', 'thing', 1)
    log_action_for(db, bb[3], 'B_ACTION', 'thing', 2)
    db.flush()

    r = client.login(a[3]).get('/api/audit-logs')
    assert r.status_code == 200, r.text
    actions = {i['action'] for i in r.json()['items']}
    assert 'A_ACTION' in actions and 'B_ACTION' not in actions
    item = [i for i in r.json()['items'] if i['action'] == 'A_ACTION'][0]
    assert item['user_name'] == a[3].name and item['branch_name'] == a[1].name

    r = client.login(bb[3]).get('/api/audit-logs')
    assert {i['action'] for i in r.json()['items']} == {'B_ACTION'}


def test_audit_logs_role_restriction(client, db, mk):
    c, b, wh, admin = mk.tenant()
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    manager = mk.user(c, role=UserRole.manager, branch=b)
    director = mk.user(c, role=UserRole.director, branch=b)
    assert client.login(cashier).get('/api/audit-logs').status_code == 403
    assert client.login(manager).get('/api/audit-logs').status_code == 403
    assert client.login(director).get('/api/audit-logs').status_code == 200
    assert client.login(admin).get('/api/audit-logs').status_code == 200


def test_audit_logs_pagination_filters_and_limit(client, db, mk):
    c, b, wh, admin = mk.tenant()
    b2 = mk.branch(c)
    for i in range(5):
        log_action_for(db, admin, 'PAGED', 'thing', i)
    log_action_for(db, admin, 'OTHER', 'widget', 99, branch_id=b2.id)
    db.flush()
    cl = client.login(admin)

    r = cl.get('/api/audit-logs', params={'action': 'PAGED', 'limit': 2, 'skip': 0})
    assert r.json()['total'] == 5 and len(r.json()['items']) == 2
    r2 = cl.get('/api/audit-logs', params={'action': 'PAGED', 'limit': 2, 'skip': 4})
    assert len(r2.json()['items']) == 1

    assert cl.get('/api/audit-logs', params={'limit': 201}).status_code == 422      # 200 dan oshmaydi
    r = cl.get('/api/audit-logs', params={'entity_type': 'widget'})
    assert [i['entity_id'] for i in r.json()['items']] == [99]
    r = cl.get('/api/audit-logs', params={'branch_id': b2.id})
    assert [i['action'] for i in r.json()['items']] == ['OTHER']
    r = cl.get('/api/audit-logs', params={'user_id': admin.id, 'entity_id': 3, 'action': 'PAGED'})
    assert r.json()['total'] == 1

    today = datetime.utcnow().strftime('%Y-%m-%d')
    assert cl.get('/api/audit-logs', params={'date_from': today, 'date_to': today}).json()['total'] >= 6
    assert cl.get('/api/audit-logs', params={'date_from': '2999-01-01'}).json()['total'] == 0
    r = cl.get('/api/audit-logs', params={'date_from': 'notadate'})
    assert r.status_code == 400


def test_audit_logs_super_admin_company_param(client, db, mk):
    a = mk.tenant()
    bb = mk.tenant()
    su = mk.user(None, role=UserRole.super_admin)
    log_action_for(db, a[3], 'SA_A', 'thing', 1)
    log_action_for(db, bb[3], 'SA_B', 'thing', 2)
    db.flush()
    r = client.login(su).get('/api/audit-logs', params={'company_id': a[0].id})
    assert {i['action'] for i in r.json()['items']} == {'SA_A'}
    r = client.login(su).get('/api/audit-logs')
    assert {'SA_A', 'SA_B'} <= {i['action'] for i in r.json()['items']}


# ─── 3. Transfer: storno ───

def _make_transfer(client, t, qty=10):
    r = client.login(t['u']).post('/api/transfers', json={
        'from_warehouse_id': t['wh1'].id, 'to_warehouse_id': t['wh2'].id,
        'items': [{'product_id': t['p'].id, 'quantity': qty}]})
    assert r.status_code == 200, r.text
    return r.json()['id']


def _tmoves(db, tid, ref='stock_transfer'):
    return db.query(StockMovement).filter(
        StockMovement.reference_type == ref, StockMovement.reference_id == tid).order_by(StockMovement.id).all()


def test_transfer_cancel_writes_storno_keeps_history(client, db, mk):
    t = _tenant(db, mk)
    tid = _make_transfer(client, t, 10)
    assert _qty(db, t['p'], t['wh1']) == 90.0 and _qty(db, t['p'], t['wh2']) == 10.0
    originals = [m.id for m in _tmoves(db, tid)]
    assert len(originals) == 2
    assert _audit(db, 'TRANSFER_CREATE', tid)

    r = client.login(t['u']).post(f'/api/transfers/{tid}/cancel')
    assert r.status_code == 200, r.text
    assert _qty(db, t['p'], t['wh1']) == 100.0 and _qty(db, t['p'], t['wh2']) == 0.0
    # asl qatorlar saqlangan
    assert [m.id for m in _tmoves(db, tid)] == originals
    storno = _tmoves(db, tid, 'stock_transfer_revert')
    assert len(storno) == 2
    by_wh = {m.warehouse_id: m for m in storno}
    assert by_wh[t['wh1'].id].type == MovementType.IN and float(by_wh[t['wh1'].id].quantity) == 10.0
    assert by_wh[t['wh2'].id].type == MovementType.OUT
    assert all(m.user_id == t['u'].id for m in storno)
    assert db.get(StockTransfer, tid).status == TransferStatus.cancelled

    log = _audit(db, 'TRANSFER_CANCEL', tid)[0]
    assert log.company_id == t['c'].id and log.user_id == t['u'].id
    assert log.old_values['status'] == 'received' and log.old_values['items'][0]['quantity'] == 10.0

    # takroriy bekor qilish — 400, qoldiq ikki marta qaytmaydi
    assert client.login(t['u']).post(f'/api/transfers/{tid}/cancel').status_code == 400
    assert _qty(db, t['p'], t['wh1']) == 100.0


def test_transfer_delete_is_soft_and_keeps_movements(client, db, mk):
    t = _tenant(db, mk)
    tid = _make_transfer(client, t, 25)
    before_count = db.query(StockMovement).count()

    r = client.login(t['u']).delete(f'/api/transfers/{tid}')
    assert r.status_code == 200, r.text
    assert r.json()['message'] == 'Transfer bekor qilindi'
    assert _qty(db, t['p'], t['wh1']) == 100.0 and _qty(db, t['p'], t['wh2']) == 0.0
    assert db.query(StockMovement).count() == before_count + 2          # kamaymadi, storno qo'shildi
    tr = db.get(StockTransfer, tid)
    assert tr is not None and tr.status == TransferStatus.cancelled     # transfer o'chmaydi
    assert _audit(db, 'TRANSFER_DELETE', tid)

    # takroriy DELETE — hech narsa o'zgarmaydi
    assert client.login(t['u']).delete(f'/api/transfers/{tid}').status_code == 200
    assert db.query(StockMovement).count() == before_count + 2


def test_transfer_update_then_cancel_no_double_revert(client, db, mk):
    t = _tenant(db, mk)
    tid = _make_transfer(client, t, 10)
    cl = client.login(t['u'])
    for qty in (20, 30):      # ikki marta tahrir: har safar faqat amaldagi ta'sir qaytariladi
        r = cl.put(f'/api/transfers/{tid}', json={
            'from_warehouse_id': t['wh1'].id, 'to_warehouse_id': t['wh2'].id,
            'items': [{'product_id': t['p'].id, 'quantity': qty}]})
        assert r.status_code == 200, r.text
        assert _qty(db, t['p'], t['wh1']) == 100.0 - qty and _qty(db, t['p'], t['wh2']) == float(qty)
    assert len(_audit(db, 'TRANSFER_UPDATE', tid)) == 2

    assert cl.post(f'/api/transfers/{tid}/cancel').status_code == 200
    assert _qty(db, t['p'], t['wh1']) == 100.0 and _qty(db, t['p'], t['wh2']) == 0.0
    # tarixda eski + storno + yangi qatorlar: 3 ta "create/update" juftligi (6) + 3 ta storno juftligi (6)
    assert len(_tmoves(db, tid)) == 6 and len(_tmoves(db, tid, 'stock_transfer_revert')) == 6


def test_transfer_isolation_other_company(client, db, mk):
    a = _tenant(db, mk)
    bb = _tenant(db, mk)
    tid = _make_transfer(client, a, 5)
    cl = client.login(bb['u'])
    assert cl.post(f'/api/transfers/{tid}/cancel').status_code == 404
    assert cl.delete(f'/api/transfers/{tid}').status_code == 404
    assert _qty(db, a['p'], a['wh2']) == 5.0


# ─── 4. Revizya ───

def _count_to_completed(client, db, t, counted):
    cl = client.login(t['u'])
    r = cl.post('/api/inventory-counts', json={'warehouse_id': t['wh1'].id})
    assert r.status_code == 200, r.text
    cid = r.json()['id']
    assert cl.post(f'/api/inventory-counts/{cid}/start').status_code == 200
    r = cl.post(f'/api/inventory-counts/{cid}/items', json=[{'product_id': t['p'].id, 'counted_qty': counted}])
    assert r.status_code == 200, r.text
    r = cl.post(f'/api/inventory-counts/{cid}/finalize')
    assert r.status_code == 200, r.text
    return cid


def test_count_completed_delete_400_and_revert_storno(client, db, mk):
    t = _tenant(db, mk, qty=100)
    cid = _count_to_completed(client, db, t, 90)          # kamomad: 10
    assert _qty(db, t['p'], t['wh1']) == 90.0
    fin = _audit(db, 'COUNT_FINALIZE', cid)[0]
    assert fin.company_id == t['c'].id and fin.new_values['diffs'][0]['delta'] == -10.0

    cl = client.login(t['u'])
    r = cl.delete(f'/api/inventory-counts/{cid}')
    assert r.status_code == 400
    assert "Yakunlangan revizyani o'chirib bo'lmaydi" in r.json()['detail']
    assert db.get(InventoryCount, cid) is not None and _qty(db, t['p'], t['wh1']) == 90.0

    rev_before = db.query(StockMovement).filter(StockMovement.reference_type == 'revision').count()
    r = cl.post(f'/api/inventory-counts/{cid}/revert')
    assert r.status_code == 200, r.text
    assert _qty(db, t['p'], t['wh1']) == 100.0
    # asl harakat saqlangan, storno qo'shilgan
    assert db.query(StockMovement).filter(StockMovement.reference_type == 'revision').count() == rev_before
    st = db.query(StockMovement).filter(StockMovement.reference_type == 'revision_revert').all()
    assert len(st) == 1 and float(st[0].qty_after - st[0].qty_before) == 10.0 and st[0].user_id == t['u'].id
    assert _audit(db, 'COUNT_REVERT', cid)

    # takroriy revert (endi in_progress) — hech narsa o'zgarmaydi
    assert cl.post(f'/api/inventory-counts/{cid}/revert').status_code == 200
    assert _qty(db, t['p'], t['wh1']) == 100.0

    # qayta yakunlash va qayta revert — net ta'sir bilan, ikki marta qaytarilmaydi
    assert cl.post(f'/api/inventory-counts/{cid}/finalize').status_code == 200
    assert _qty(db, t['p'], t['wh1']) == 90.0
    assert cl.post(f'/api/inventory-counts/{cid}/revert').status_code == 200
    assert _qty(db, t['p'], t['wh1']) == 100.0


def test_count_draft_delete_allowed_and_audited(client, db, mk):
    t = _tenant(db, mk)
    cl = client.login(t['u'])
    cid = cl.post('/api/inventory-counts', json={'warehouse_id': t['wh1'].id}).json()['id']
    r = cl.delete(f'/api/inventory-counts/{cid}')
    assert r.status_code == 200, r.text
    assert db.get(InventoryCount, cid) is None
    log = _audit(db, 'COUNT_DELETE', cid)[0]
    assert log.company_id == t['c'].id and log.old_values['status'] == 'draft'


def test_count_isolation(client, db, mk):
    a = _tenant(db, mk)
    bb = _tenant(db, mk)
    cid = _count_to_completed(client, db, a, 90)
    cl = client.login(bb['u'])
    assert cl.delete(f'/api/inventory-counts/{cid}').status_code == 404
    assert cl.post(f'/api/inventory-counts/{cid}/revert').status_code == 404
    assert _qty(db, a['p'], a['wh1']) == 90.0


# ─── 5. Ombor: adjust, chiqim, ombor PATCH/DELETE ───

def test_adjust_stock_is_audited(client, db, mk):
    t = _tenant(db, mk, qty=50)
    r = client.login(t['u']).post('/api/inventory/adjust', json={
        'product_id': t['p'].id, 'warehouse_id': t['wh1'].id, 'new_quantity': 42, 'reason': 'Sanoq xatosi'})
    assert r.status_code == 200, r.text
    log = _audit(db, 'STOCK_ADJUST', t['p'].id)[0]
    assert log.old_values['quantity'] == 50.0 and log.new_values['quantity'] == 42.0
    assert log.company_id == t['c'].id and log.branch_id == t['b'].id and log.user_id == t['u'].id


def test_chiqim_create_delete_storno_and_idempotent(client, db, mk):
    t = _tenant(db, mk, qty=50)
    db.add(Batch(product_id=t['p'].id, warehouse_id=t['wh1'].id, company_id=t['c'].id, lot_number='L1',
                 initial_quantity=Decimal(50), quantity=Decimal(50), purchase_price=Decimal(100)))
    db.flush()
    cl = client.login(t['u'])
    r = cl.post('/api/inventory/chiqims', json={
        'warehouse_id': t['wh1'].id, 'items': [{'product_id': t['p'].id, 'quantity': 8, 'type': 'Brak'}]})
    assert r.status_code == 200, r.text
    ref = r.json()['reference_id']
    assert _qty(db, t['p'], t['wh1']) == 42.0
    assert _audit(db, 'CHIQIM_CREATE', ref)

    originals = _tmoves(db, ref, 'chiqim')
    assert len(originals) == 1
    r = cl.delete(f'/api/inventory/chiqims/{ref}')
    assert r.status_code == 200, r.text
    assert _qty(db, t['p'], t['wh1']) == 50.0
    assert len(_tmoves(db, ref, 'chiqim')) == 1                          # asl harakat o'chmadi
    assert len(_tmoves(db, ref, 'chiqim_revert')) == 1
    assert _audit(db, 'CHIQIM_DELETE', ref)

    # takroriy bekor qilish — 400, qoldiq oshmaydi
    r = cl.delete(f'/api/inventory/chiqims/{ref}')
    assert r.status_code == 400
    assert _qty(db, t['p'], t['wh1']) == 50.0


def test_warehouse_patch_delete_audited(client, db, mk):
    t = _tenant(db, mk)
    cl = client.login(t['u'])
    r = cl.patch(f"/api/warehouses/{t['wh2'].id}", json={'name': 'Yangi nom'})
    assert r.status_code == 200, r.text
    log = _audit(db, 'WAREHOUSE_UPDATE', t['wh2'].id)[0]
    assert log.old_values['name'] == 'Yunusobod' and log.new_values['name'] == 'Yangi nom'
    assert log.company_id == t['c'].id and log.branch_id == t['b'].id
    assert cl.delete(f"/api/warehouses/{t['wh2'].id}").status_code == 204
    assert _audit(db, 'WAREHOUSE_DELETE', t['wh2'].id)[0].new_values == {'is_active': False}


def test_branch_crud_audit_has_company_and_branch(client, db, mk):
    c, b, wh, u = mk.tenant()
    su = mk.user(None, role=UserRole.super_admin)
    # tarif limiti (1 filial) tufayli yangi filialni super_admin ochadi; log company_id ni filialdan oladi
    r = client.login(su).post('/api/branches', json={'name': 'Yangi filial', 'company_id': c.id})
    assert r.status_code in (200, 201), r.text
    cl = client.login(u)
    bid = r.json()['id']
    log = _audit(db, 'CREATE', bid)
    log = [l for l in log if l.entity_type == 'branch'][0]
    assert log.company_id == c.id and log.branch_id == bid
    assert cl.patch(f'/api/branches/{bid}', json={'name': 'Nomi'}).status_code == 200
    assert cl.delete(f'/api/branches/{bid}').status_code == 204
    kinds = {l.action for l in db.query(AuditLog).filter(AuditLog.entity_type == 'branch', AuditLog.entity_id == bid)}
    assert kinds == {'CREATE', 'UPDATE', 'DELETE'}


# ─── 6. Qaytarishni bekor qilish idempotentligi ───

def test_sale_refund_revert_keeps_movement_and_is_idempotent(client, db, mk):
    t = _tenant(db, mk, qty=10)
    m = StockMovement(product_id=t['p'].id, warehouse_id=t['wh1'].id, type=MovementType.RETURN,
                      qty_before=Decimal(10), qty_after=Decimal(15), quantity=Decimal(5),
                      reference_type='sale_refund', reference_id=1, user_id=t['u'].id)
    db.add(m)
    db.query(StockLevel).filter(StockLevel.product_id == t['p'].id).update({'quantity': Decimal(15)})
    db.flush()
    cl = client.login(t['u'])
    r = cl.delete(f'/api/inventory/movements/{m.id}')
    assert r.status_code == 200, r.text
    assert db.get(StockMovement, m.id) is not None                      # o'chmadi
    assert '[bekor qilingan]' in db.get(StockMovement, m.id).reason
    assert _qty(db, t['p'], t['wh1']) == 10.0
    assert _audit(db, 'RETURN_REVERT', m.id)
    # takroriy — 400, qoldiq qayta kamaymaydi
    r = cl.delete(f'/api/inventory/movements/{m.id}')
    assert r.status_code == 400
    assert _qty(db, t['p'], t['wh1']) == 10.0


# ─── 7. Kassa xarajati: void ───

def _kassa_balance_cash(client, user, wallet):
    r = client.login(user).get(f'/api/kassa/{wallet.id}/summary')
    assert r.status_code == 200, r.text
    items = r.json().get('cash', [])
    return sum(i['value'] for i in items if i['currency'] == 'UZS')


def test_kassa_expense_void(client, db, mk):
    c, b, wh, u = mk.tenant()
    w = _wallet(db, c, b, balance=1000)
    cat = _category(db, c)
    cl = client.login(u)
    r = cl.post('/api/kassa/do-expense', json={
        'wallet_id': w.id, 'category_id': cat.id, 'amount': 300, 'payment_type': 'cash', 'currency': 'UZS',
        'description': 'Svet'})
    assert r.status_code == 200, r.text
    eid = r.json()['expense_id']
    assert float(db.get(Wallet, w.id).balance) == 700.0
    tx = db.query(Transaction).filter(Transaction.reference_type == 'expense', Transaction.reference_id == eid).one()
    assert tx.user_id == u.id                                           # Transaction.user_id to'ldirilgan
    assert _audit(db, 'EXPENSE_CREATE', eid)
    assert _kassa_balance_cash(client, u, w) == -300.0

    r = cl.delete(f'/api/kassa/expense/{eid}')
    assert r.status_code == 200, r.text
    db.expire_all()
    exp = db.get(Expense, eid)
    assert exp is not None and exp.voided_at is not None and exp.voided_by == u.id      # bazada qoladi
    assert float(db.get(Wallet, w.id).balance) == 1000.0                                # hamyon qaytdi
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == 'expense').count() == 1   # asl harakat o'chmadi
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == 'expense_void').count() == 1
    tx = db.get(Transaction, tx.id)
    assert tx.voided_at is not None and tx.voided_by == u.id
    assert _kassa_balance_cash(client, u, w) == 0.0                                      # kassa balansi to'g'ri
    # ro'yxatda ko'rinmaydi
    items = cl.get(f'/api/kassa/{w.id}/expenses').json()['items']
    assert eid not in [i['id'] for i in items]
    items = cl.get(f'/api/kassa/{w.id}/expenses', params={'include_voided': 'true'}).json()['items']
    assert eid in [i['id'] for i in items]
    # tahrirlab bo'lmaydi, takroriy o'chirish 400
    assert cl.put(f'/api/kassa/expense/{eid}', json={'amount': 5}).status_code == 404
    assert cl.delete(f'/api/kassa/expense/{eid}').status_code == 400
    assert float(db.get(Wallet, w.id).balance) == 1000.0
    log = _audit(db, 'EXPENSE_VOID', eid)[0]
    assert log.user_id == u.id and log.company_id == c.id and log.old_values['amount'] == 300.0


def test_kassa_expense_void_other_company_404(client, db, mk):
    a = mk.tenant()
    bb = mk.tenant()
    w = _wallet(db, a[0], a[1])
    cat = _category(db, a[0])
    eid = client.login(a[3]).post('/api/kassa/do-expense', json={
        'wallet_id': w.id, 'category_id': cat.id, 'amount': 10}).json()['expense_id']
    assert client.login(bb[3]).delete(f'/api/kassa/expense/{eid}').status_code == 404
    assert db.get(Expense, eid).voided_at is None


def test_kassa_operations_are_audited(client, db, mk):
    c, b, wh, u = mk.tenant()
    cl = client.login(u)
    r = cl.post('/api/kassa', json={'name': 'Yangi kassa', 'branch_id': b.id, 'opening_balance': 0})
    assert r.status_code == 200, r.text
    wid = r.json()['id']
    assert _audit(db, 'WALLET_CREATE', wid)
    assert cl.post(f'/api/kassa/{wid}/open', json={'opening_balance': 100}).status_code == 200
    assert _audit(db, 'KASSA_OPEN', wid)
    assert cl.post(f'/api/kassa/{wid}/invest', json={'amount': 500}).status_code == 200
    assert cl.post(f'/api/kassa/{wid}/withdraw', json={'amount': 200}).status_code == 200
    inv = _audit(db, 'KASSA_INVEST', wid)[0]
    assert inv.new_values['amount'] == 500.0 and inv.company_id == c.id and inv.branch_id == b.id
    assert _audit(db, 'KASSA_WITHDRAW', wid)
    assert cl.post(f'/api/kassa/{wid}/close', json={'actual_amounts': {'cash': {'UZS': 400}}}).status_code == 200
    cl_log = _audit(db, 'KASSA_CLOSE', wid)[0]
    assert cl_log.user_id == u.id
    assert cl.patch(f'/api/kassa/{wid}', json={'name': 'Nom2'}).status_code == 200
    assert _audit(db, 'WALLET_UPDATE', wid)
    assert cl.delete(f'/api/kassa/{wid}').status_code == 200
    assert _audit(db, 'WALLET_DELETE', wid)


# ─── 8. Moliya: xarajat va tranzaksiya void ───

def test_finance_expense_void_and_reports(client, db, mk):
    c, b, wh, u = mk.tenant()
    w = _wallet(db, c, b, balance=1000)
    cat = _category(db, c)
    cl = client.login(u)
    r = cl.post('/api/finance/expenses', json={'category_id': cat.id, 'amount': 200, 'wallet_id': w.id})
    assert r.status_code == 201, r.text
    eid = r.json()['id']
    tx = db.query(Transaction).filter(Transaction.reference_type == 'expense', Transaction.reference_id == eid).one()
    assert tx.user_id == u.id
    assert float(db.get(Wallet, w.id).balance) == 800.0
    assert cl.get('/api/finance/cash-balance').json()['total_expense'] == 200.0

    r = cl.delete(f'/api/finance/expenses/{eid}')
    assert r.status_code == 204, r.text
    db.expire_all()
    exp = db.get(Expense, eid)
    assert exp.voided_at is not None and exp.voided_by == u.id
    assert float(db.get(Wallet, w.id).balance) == 1000.0
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == 'expense').count() == 1
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == 'expense_void').count() == 1
    assert db.get(Transaction, tx.id).voided_at is not None
    assert _kassa_balance_cash(client, u, w) == 0.0

    # ro'yxatlar va hisobotlar void yozuvni hisobga olmaydi
    assert eid not in [e['id'] for e in cl.get('/api/finance/expenses').json()]
    assert eid in [e['id'] for e in cl.get('/api/finance/expenses', params={'include_voided': 'true'}).json()]
    cb = cl.get('/api/finance/cash-balance').json()
    assert cb['total_expense'] == 0.0 and cb['total_income'] == 0.0
    assert cl.get('/api/finance/transactions').json() == []
    assert len(cl.get('/api/finance/transactions', params={'include_voided': 'true'}).json()) == 2
    # cashier include_voided ko'ra olmaydi (rol cheklovi: manager ham admin/director emas)
    acc = mk.user(c, role=UserRole.accountant, branch=b)
    assert eid not in [e['id'] for e in client.login(acc).get(
        '/api/finance/expenses', params={'include_voided': 'true'}).json()]

    assert cl.delete(f'/api/finance/expenses/{eid}').status_code == 400
    assert float(db.get(Wallet, w.id).balance) == 1000.0
    assert _audit(db, 'EXPENSE_VOID', eid)


def test_finance_transaction_void(client, db, mk):
    c, b, wh, u = mk.tenant()
    w = _wallet(db, c, b, balance=500)
    cl = client.login(u)
    r = cl.post('/api/finance/transactions', json={
        'type': 'income', 'amount': 250, 'wallet_id': w.id, 'reference_type': 'other_income'})
    assert r.status_code == 201, r.text
    txid = r.json()['id']
    assert r.json()['user_id'] == u.id
    assert float(db.get(Wallet, w.id).balance) == 750.0
    assert _audit(db, 'TRANSACTION_CREATE', txid)

    r = cl.put(f'/api/finance/transactions/{txid}', json={'amount': 300, 'wallet_id': w.id})
    assert r.status_code == 200, r.text
    assert _audit(db, 'TRANSACTION_UPDATE', txid)[0].old_values['amount'] == 250.0
    assert float(db.get(Wallet, w.id).balance) == 800.0

    r = cl.delete(f'/api/finance/transactions/{txid}')
    assert r.status_code == 204, r.text
    db.expire_all()
    tx = db.get(Transaction, txid)
    assert tx is not None and tx.voided_at is not None and tx.voided_by == u.id
    assert float(db.get(Wallet, w.id).balance) == 500.0
    assert _kassa_balance_cash(client, u, w) == 0.0
    assert cl.get('/api/finance/cash-balance').json()['total_income'] == 0.0
    assert txid not in [t['id'] for t in cl.get('/api/finance/transactions').json()]
    # void tranzaksiyani tahrirlash/qayta o'chirish mumkin emas
    assert cl.put(f'/api/finance/transactions/{txid}', json={'amount': 1, 'wallet_id': w.id}).status_code == 404
    assert cl.delete(f'/api/finance/transactions/{txid}').status_code == 400
    assert float(db.get(Wallet, w.id).balance) == 500.0
    assert _audit(db, 'TRANSACTION_VOID', txid)


def test_finance_transaction_void_other_company_404(client, db, mk):
    a = mk.tenant()
    bb = mk.tenant()
    w = _wallet(db, a[0], a[1])
    txid = client.login(a[3]).post('/api/finance/transactions', json={
        'type': 'expense', 'amount': 10, 'wallet_id': w.id, 'reference_type': 'other_expense'}).json()['id']
    assert client.login(bb[3]).delete(f'/api/finance/transactions/{txid}').status_code == 404
    assert db.get(Transaction, txid).voided_at is None


# ─── 9. Transaction.user_id: mijoz qarzi to'lovi ───

def test_customer_debt_payments_set_user_id_and_audit(client, db, mk):
    c, b, wh, u = mk.tenant()
    w = _wallet(db, c, b, balance=0)
    cust = Customer(name='Qarzdor', company_id=c.id, branch_id=b.id, debt_balance=Decimal(1000),
                    debt_balances={'UZS': 1000.0})
    db.add(cust)
    db.flush()
    cl = client.login(u)

    r = cl.post(f'/api/customers/{cust.id}/pay-debt', json={'amount': 100, 'reason': "Qarz to'lovi", 'wallet_id': w.id})
    assert r.status_code == 200, r.text
    tx = db.query(Transaction).filter(Transaction.reference_type == 'customer_payment').one()
    assert tx.user_id == u.id
    log = _audit(db, 'CUSTOMER_DEBT_PAY', cust.id)[0]
    assert log.company_id == c.id and log.user_id == u.id and log.old_values['debt_balance'] == 1000.0

    r = cl.post(f'/api/finance/customer-debts/{cust.id}/pay', json={'amount': 50, 'wallet_id': w.id})
    assert r.status_code == 200, r.text
    txs = db.query(Transaction).filter(Transaction.reference_type == 'customer_payment').all()
    assert len(txs) == 2 and all(t.user_id == u.id for t in txs)
    assert len(_audit(db, 'CUSTOMER_DEBT_PAY', cust.id)) == 2


# ─── 10. Smena ───

def test_shift_open_close_audited(client, db, mk):
    c, b, wh, u = mk.tenant(role=UserRole.cashier)
    cl = client.login(u)
    r = cl.post('/api/shifts/open', json={'opening_cash': 100})
    assert r.status_code == 201, r.text
    sid = r.json()['id']
    log = _audit(db, 'SHIFT_OPEN', sid)[0]
    assert log.company_id == c.id and log.branch_id == b.id and log.user_id == u.id
    r = cl.post('/api/shifts/close', json={'closing_cash': 100})
    assert r.status_code == 200, r.text
    log = _audit(db, 'SHIFT_CLOSE', sid)[0]
    assert log.company_id == c.id and log.new_values['closing_cash'] is not None


# ─── 11. Sotuv o'chirish: storno ───

def test_sale_delete_keeps_movement_and_writes_storno(db, mk):
    from app.models.sale import Sale, SaleItem, SaleStatus
    from app.services.sale_delete import delete_sale

    t = _tenant(db, mk, qty=100)
    sale = Sale(number='S-T119-1', company_id=t['c'].id, status=SaleStatus.completed, total_amount=Decimal(0), paid_amount=Decimal(0), payment_type='cash',
                warehouse_id=t['wh1'].id, cashier_id=t['u'].id)
    db.add(sale)
    db.flush()
    db.add(SaleItem(sale_id=sale.id, product_id=t['p'].id, quantity=Decimal(7), unit_price=Decimal(0),
                    cost_price=Decimal(0), subtotal=Decimal(0), warehouse_id=t['wh1'].id))
    db.query(StockLevel).filter(StockLevel.product_id == t['p'].id).update({'quantity': Decimal(93)})
    db.add(StockMovement(product_id=t['p'].id, warehouse_id=t['wh1'].id, type=MovementType.OUT,
                         qty_before=Decimal(100), qty_after=Decimal(93), quantity=Decimal(7),
                         reference_type='sale', reference_id=sale.id, user_id=t['u'].id))
    db.flush()
    sid = sale.id

    delete_sale(db, sid, t['u'])
    assert _qty(db, t['p'], t['wh1']) == 100.0
    assert len(_tmoves(db, sid, 'sale')) == 1                            # asl harakat saqlandi
    st = _tmoves(db, sid, 'sale_delete_revert')
    assert len(st) == 1 and st[0].type == MovementType.IN and float(st[0].quantity) == 7.0
    log = _audit(db, 'SALE_DELETE', sid)[0]
    assert log.company_id == t['c'].id


# ─── 12. Ishlab chiqarish ───

def test_production_audit_helper_branch_and_values(db, mk):
    from app.models.production_order import ProductionOrderStatus
    from app.routers.production import _audit_order

    t = _tenant(db, mk)

    class _Order:
        id = 11
        number = 'PO-1'
        product_id = t['p'].id
        warehouse_id = t['wh1'].id
        target_warehouse_id = t['wh2'].id
        status = ProductionOrderStatus.completed

    _audit_order(db, t['u'], 'PRODUCTION_COMPLETE', _Order, old_status='in_progress',
                 extra={'unit_cost': 12.5, 'produced_quantity': 4.0})
    log = _audit(db, 'PRODUCTION_COMPLETE', 11)[0]
    assert log.company_id == t['c'].id and log.branch_id == t['b'].id
    assert log.new_values['unit_cost'] == 12.5 and log.new_values['status'] == 'completed'
    assert log.old_values == {'status': 'in_progress'}


def test_production_start_complete_cancel_api_audited(client, db, mk):
    from app.models.bom import BOM, BOMItem
    from app.models.production_order import ProductionOrder, ProductionOrderStatus

    t = _tenant(db, mk, qty=100)                       # xom ashyo (Sut) wh1 da
    t['c'].manufacturing_enabled = True
    fin = _product(db, t['c'], name='Pishloq')
    bom = BOM(product_id=fin.id, name='Retsept', company_id=t['c'].id)
    db.add(bom)
    db.flush()
    db.add(BOMItem(bom_id=bom.id, component_product_id=t['p'].id, quantity_per_unit=Decimal(2)))

    def _order(n):
        o = ProductionOrder(number=f'PRD-T119-{n}', bom_id=bom.id, product_id=fin.id, planned_quantity=Decimal(5),
                            warehouse_id=t['wh1'].id, target_warehouse_id=t['wh2'].id,
                            created_by=t['u'].id, company_id=t['c'].id, status=ProductionOrderStatus.draft)
        db.add(o)
        db.flush()
        return o

    o1, o2 = _order(1), _order(2)
    cl = client.login(t['u'])
    assert cl.post(f'/api/production/orders/{o1.id}/start').status_code == 200
    assert _audit(db, 'PRODUCTION_START', o1.id)
    r = cl.post(f'/api/production/orders/{o1.id}/complete', json={'produced_quantity': 5, 'costs': []})
    assert r.status_code == 200, r.text
    log = _audit(db, 'PRODUCTION_COMPLETE', o1.id)[0]
    assert log.company_id == t['c'].id and log.branch_id == t['b'].id
    assert log.new_values['produced_quantity'] == 5.0 and 'unit_cost' in log.new_values

    r = cl.post(f'/api/production/orders/{o2.id}/cancel')
    assert r.status_code == 200, r.text
    log = _audit(db, 'PRODUCTION_CANCEL', o2.id)[0]
    assert log.old_values == {'status': 'draft'} and log.new_values['status'] == 'cancelled'
