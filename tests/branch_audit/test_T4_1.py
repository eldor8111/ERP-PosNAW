"""T4.1 — Ikki bosqichli filiallararo transfer (yuborildi -> yo'lda -> qabul qilindi).

Qamrov: yuborishda faqat manba kamayishi, yo'ldagi tovar (in-transit-summary), to'liq/qisman qabul,
kamomad sababi va ortiqcha qabul 400, filial ruxsatlari (403), bekor qilish (yo'lda/qabul qilingan),
kompensatsion harakatlar, bir filial ichida bir bosqichli rejim, partiyalar, yo'nalish filtri,
ikki korxona izolyatsiyasi, parallel send, tahrir/o'chirish 409, migratsiya va i18n kalitlari.
"""
import importlib.util
import itertools
import json
import os
from decimal import Decimal

import pytest
from sqlalchemy import update
from sqlalchemy.orm.attributes import set_committed_value

from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product, ProductConversion
from app.models.transfer import StockTransfer, StockTransferBatch, StockTransferItem, TransferStatus
from app.models.user import UserRole

_seq = itertools.count(1)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


# ─── yordamchilar ───

def _product(db, company, name=None):
    n = next(_seq)
    p = Product(name=name or f'Un {n}', sku=f'SKU-T041-{n}', barcode=f'BC-T041-{n}',
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


def _batch(db, product, warehouse, qty, lot='LOT-1'):
    b = Batch(product_id=product.id, warehouse_id=warehouse.id, company_id=product.company_id,
              lot_number=lot, initial_quantity=Decimal(qty), quantity=Decimal(qty), purchase_price=Decimal('5000'))
    db.add(b)
    db.flush()
    return b


def _moves(db, transfer_id, ref='stock_transfer'):
    return db.query(StockMovement).filter(
        StockMovement.reference_type == ref, StockMovement.reference_id == transfer_id
    ).order_by(StockMovement.id).all()


@pytest.fixture
def w(db, mk):
    """Korxona A: Chilonzor (b1: w1, w1b), Yunusobod (b2: w2), Sergeli (b3: w3), filialsiz ombor (wn, wn2).
    Xodimlar: omborchi har filialda, admin. Korxona B: o'z omborlari va omborchisi."""
    c = mk.company()
    b1, b2, b3 = mk.branch(c, name='Chilonzor'), mk.branch(c, name='Yunusobod'), mk.branch(c, name='Sergeli')
    w1, w1b = mk.warehouse(c, b1, name='Chil-1'), mk.warehouse(c, b1, name='Chil-2')
    w2, w3 = mk.warehouse(c, b2, name='Yun-1'), mk.warehouse(c, b3, name='Ser-1')
    wn, wn2 = mk.warehouse(c, None, name='Markaz-1'), mk.warehouse(c, None, name='Markaz-2')
    admin = mk.user(c, UserRole.admin)
    u1 = mk.user(c, UserRole.warehouse, branch=b1)
    u2 = mk.user(c, UserRole.warehouse, branch=b2)
    u3 = mk.user(c, UserRole.warehouse, branch=b3)
    p = _product(db, c, name='Un')
    _stock(db, p, w1, 100)
    _stock(db, p, wn, 100)

    cb = mk.company()
    bb1, bb2 = mk.branch(cb), mk.branch(cb)
    wb1, wb2 = mk.warehouse(cb, bb1), mk.warehouse(cb, bb2)
    ub1 = mk.user(cb, UserRole.warehouse, branch=bb1)
    ub2 = mk.user(cb, UserRole.warehouse, branch=bb2)
    pb = _product(db, cb, name='Shakar')
    _stock(db, pb, wb1, 50)
    return dict(c=c, b1=b1, b2=b2, b3=b3, w1=w1, w1b=w1b, w2=w2, w3=w3, wn=wn, wn2=wn2,
                admin=admin, u1=u1, u2=u2, u3=u3, p=p, cb=cb, wb1=wb1, wb2=wb2, ub1=ub1, ub2=ub2, pb=pb)


def _body(frm, to, product, qty, **extra):
    d = {'from_warehouse_id': frm.id, 'to_warehouse_id': to.id,
         'items': [{'product_id': product.id, 'quantity': qty}]}
    d.update(extra)
    return d


def _send_cross(client, w, qty=50, user=None, **extra):
    """Chilonzor (w1) -> Yunusobod (w2), yuborilgan (in_transit)"""
    r = client.login(user or w['u1']).post('/api/transfers', json=_body(w['w1'], w['w2'], w['p'], qty, **extra))
    assert r.status_code == 200, r.text
    return r.json()


def _receive(client, user, tid, item_id, qty, reason=None, note=None):
    body = {'items': [{'item_id': item_id, 'qty_received': qty, 'reason': reason}]}
    if note:
        body['note'] = note
    return client.login(user).post(f'/api/transfers/{tid}/receive', json=body)


# ─── 1. Yuborish: faqat manba kamayadi (mezon 1, 2, 10) ───

def test_cross_branch_create_sends_and_only_source_decreases(client, db, w):
    body = _send_cross(client, w, 50)
    assert body['status'] == 'in_transit' and body['two_step'] is True
    assert body['sent_by'] == w['u1'].id and body['sent_at'] is not None
    assert body['from_branch_name'] == 'Chilonzor' and body['to_branch_name'] == 'Yunusobod'
    it = body['items'][0]
    assert float(it['qty_sent']) == 50 and it['qty_received'] is None
    assert _qty(db, w['p'], w['w1']) == 50.0
    assert _qty(db, w['p'], w['w2']) is None            # manzilda qator ham paydo bo'lmaydi

    ms = _moves(db, body['id'])
    assert [m.type for m in ms] == [MovementType.TRANSFER_OUT]
    assert ms[0].warehouse_id == w['w1'].id

    # yo'ldagi tovar alohida ko'rsatiladi
    r = client.login(w['u2']).get(f"/api/transfers/in-transit-summary?warehouse_id={w['w2'].id}")
    assert r.status_code == 200, r.text
    assert [(x['product_id'], x['variant_id'], float(x['qty'])) for x in r.json()] == [(w['p'].id, None, 50.0)]
    # boshqa ombor uchun bo'sh
    assert client.login(w['u2']).get(f"/api/transfers/in-transit-summary?warehouse_id={w['w3'].id}").json() == []


def test_draft_does_not_touch_stock_then_send(client, db, w):
    body = _send_cross(client, w, 30, send=False)
    assert body['status'] == 'pending' and body['can_send'] is True
    assert _qty(db, w['p'], w['w1']) == 100.0 and _moves(db, body['id']) == []
    r = client.login(w['u1']).post(f"/api/transfers/{body['id']}/send")
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'in_transit' and _qty(db, w['p'], w['w1']) == 70.0
    assert _qty(db, w['p'], w['w2']) is None


def test_send_insufficient_stock_400(client, db, w):
    r = client.login(w['u1']).post('/api/transfers', json=_body(w['w1'], w['w2'], w['p'], 500))
    assert r.status_code == 400, r.text
    assert _qty(db, w['p'], w['w1']) == 100.0
    assert db.query(StockTransfer).count() == 0 or all(
        t.status != TransferStatus.in_transit for t in db.query(StockTransfer).all())


# ─── 2. Qabul: to'liq, qisman, xatolar (mezon 3, 4) ───

def test_receive_partial_with_reason(client, db, w):
    body = _send_cross(client, w, 50)
    tid, item_id = body['id'], body['items'][0]['id']
    r = _receive(client, w['u2'], tid, item_id, 48, reason='2 qop yirtilgan', note='Mashina kech keldi')
    assert r.status_code == 200, r.text
    out = r.json()
    assert out['status'] == 'received' and out['confirmed_by'] == w['u2'].id
    assert out['confirmer_name'] == w['u2'].name and 'Mashina kech keldi' in out['note']
    it = out['items'][0]
    assert float(it['qty_sent']) == 50 and float(it['qty_received']) == 48
    assert it['discrepancy_reason'] == '2 qop yirtilgan'
    assert _qty(db, w['p'], w['w2']) == 48.0 and _qty(db, w['p'], w['w1']) == 50.0   # manbaga qo'shimcha o'zgarish yo'q
    ms = _moves(db, tid)
    assert {m.type: m for m in ms}[MovementType.TRANSFER_IN].warehouse_id == w['w2'].id
    assert float({m.type: m for m in ms}[MovementType.TRANSFER_IN].quantity) == 48.0
    log = db.query(AuditLog).filter(AuditLog.action == 'TRANSFER_RECEIVE', AuditLog.entity_id == tid).one()
    assert log.new_values['items'][0]['shortage'] == 2.0
    # yo'ldagi tovar endi qolmadi
    assert client.login(w['u2']).get(f"/api/transfers/in-transit-summary?warehouse_id={w['w2'].id}").json() == []


def test_receive_full_and_confirm_alias(client, db, w):
    body = _send_cross(client, w, 20)
    r = _receive(client, w['u2'], body['id'], body['items'][0]['id'], 20)
    assert r.status_code == 200 and _qty(db, w['p'], w['w2']) == 20.0
    # alias: /confirm hammasini to'liq qabul qiladi
    b2 = _send_cross(client, w, 10)
    r = client.login(w['u2']).post(f"/api/transfers/{b2['id']}/confirm")
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'received' and float(r.json()['items'][0]['qty_received']) == 10
    assert _qty(db, w['p'], w['w2']) == 30.0


def test_confirm_pending_400_and_receive_wrong_state_409(client, db, w):
    draft = _send_cross(client, w, 5, send=False)
    r = client.login(w['u2']).post(f"/api/transfers/{draft['id']}/confirm")
    assert r.status_code == 400 and 'yuboring' in r.json()['detail']
    r = _receive(client, w['u2'], draft['id'], draft['items'][0]['id'], 5)
    assert r.status_code == 409
    sent = _send_cross(client, w, 5)
    # ikkinchi marta yuborish 409
    assert client.login(w['u1']).post(f"/api/transfers/{sent['id']}/send").status_code == 409


def test_receive_validation_errors(client, db, w):
    body = _send_cross(client, w, 50)
    tid, item_id = body['id'], body['items'][0]['id']
    # kamomad, sabab yo'q
    r = _receive(client, w['u2'], tid, item_id, 40)
    assert r.status_code == 400, r.text
    r = _receive(client, w['u2'], tid, item_id, 40, reason='   ')
    assert r.status_code == 400
    # ortiqcha
    r = _receive(client, w['u2'], tid, item_id, 51, reason='ko\'p')
    assert r.status_code == 400
    # manfiy -> 422
    assert _receive(client, w['u2'], tid, item_id, -1, reason='x').status_code == 422
    # begona item_id
    assert _receive(client, w['u2'], tid, item_id + 999, 50).status_code == 400
    # hech narsa o'zgarmadi
    assert _qty(db, w['p'], w['w2']) is None
    assert db.get(StockTransfer, tid).status == TransferStatus.in_transit


def test_receive_zero_all_lost(client, db, w):
    body = _send_cross(client, w, 10)
    r = _receive(client, w['u2'], body['id'], body['items'][0]['id'], 0, reason='mashina yo\'qoldi')
    assert r.status_code == 200, r.text
    assert float(r.json()['items'][0]['qty_received']) == 0
    assert _qty(db, w['p'], w['w2']) is None
    assert [m.type for m in _moves(db, body['id'])] == [MovementType.TRANSFER_OUT]


# ─── 3. Filial ruxsatlari (mezon 5) ───

def test_source_branch_cannot_send_from_other_branch_warehouse(client, db, w):
    # Yunusobod omborchisi Chilonzor omboridan yaratib yubora olmaydi
    r = client.login(w['u2']).post('/api/transfers', json=_body(w['w1'], w['w2'], w['p'], 5))
    assert r.status_code == 403, r.text
    assert _qty(db, w['p'], w['w1']) == 100.0
    # qoralamani manzil filial yubora olmaydi (403), manba filial yuboradi
    draft = _send_cross(client, w, 5, send=False)
    assert client.login(w['u2']).post(f"/api/transfers/{draft['id']}/send").status_code == 403
    assert client.login(w['u3']).post(f"/api/transfers/{draft['id']}/send").status_code == 403
    assert db.get(StockTransfer, draft['id']).status == TransferStatus.pending
    assert client.login(w['u1']).post(f"/api/transfers/{draft['id']}/send").status_code == 200


def test_receive_only_destination_branch(client, db, w):
    body = _send_cross(client, w, 10)
    tid, iid = body['id'], body['items'][0]['id']
    assert _receive(client, w['u1'], tid, iid, 10).status_code == 403      # jo'natuvchi o'ziga qabul qila olmaydi
    assert _receive(client, w['u3'], tid, iid, 10).status_code == 403      # uchinchi filial
    assert db.get(StockTransfer, tid).status == TransferStatus.in_transit
    assert _receive(client, w['u2'], tid, iid, 10).status_code == 200      # manzil filial
    # admin istalgan tomondan qabul qila oladi
    b2 = _send_cross(client, w, 3)
    assert _receive(client, w['admin'], b2['id'], b2['items'][0]['id'], 3).status_code == 200


def test_flags_for_each_party(client, db, w):
    body = _send_cross(client, w, 10)
    tid = body['id']
    f1 = client.login(w['u1']).get(f'/api/transfers/{tid}').json()
    f2 = client.login(w['u2']).get(f'/api/transfers/{tid}').json()
    f3 = client.login(w['u3']).get(f'/api/transfers/{tid}').json()
    assert (f1['can_receive'], f1['can_cancel']) == (False, True)
    assert (f2['can_receive'], f2['can_cancel']) == (True, True)
    assert (f3['can_receive'], f3['can_cancel']) == (False, False)


# ─── 4. Bekor qilish (mezon 6) ───

def test_cancel_in_transit_restores_source_and_keeps_history(client, db, w):
    body = _send_cross(client, w, 50)
    tid = body['id']
    assert client.login(w['u3']).post(f'/api/transfers/{tid}/cancel').status_code == 403
    r = client.login(w['u2']).post(f'/api/transfers/{tid}/cancel', json={'reason': 'Mashina buzildi'})
    assert r.status_code == 200, r.text
    assert _qty(db, w['p'], w['w1']) == 100.0 and _qty(db, w['p'], w['w2']) is None
    t = db.get(StockTransfer, tid)
    assert t.status == TransferStatus.cancelled and t.cancel_reason == 'Mashina buzildi'
    # asl yozuv o'chmaydi, kompensatsion yozuv paydo bo'ladi
    orig = _moves(db, tid)
    assert [m.type for m in orig] == [MovementType.TRANSFER_OUT]
    rev = _moves(db, tid, 'stock_transfer_revert')
    assert len(rev) == 1 and rev[0].type == MovementType.IN and rev[0].warehouse_id == w['w1'].id
    assert 'Mashina buzildi' in rev[0].reason
    # ikkinchi marta bekor qilib bo'lmaydi, qoldiq ikki marta qaytmaydi
    assert client.login(w['u1']).post(f'/api/transfers/{tid}/cancel').status_code == 400
    assert _qty(db, w['p'], w['w1']) == 100.0


def test_cancel_pending_touches_no_stock(client, db, w):
    draft = _send_cross(client, w, 10, send=False)
    r = client.login(w['u1']).post(f"/api/transfers/{draft['id']}/cancel")
    assert r.status_code == 200, r.text
    assert _qty(db, w['p'], w['w1']) == 100.0 and _moves(db, draft['id'], 'stock_transfer_revert') == []
    assert db.get(StockTransfer, draft['id']).status == TransferStatus.cancelled


def test_cancel_received_admin_only_and_needs_dest_stock(client, db, w):
    body = _send_cross(client, w, 50)
    tid, iid = body['id'], body['items'][0]['id']
    assert _receive(client, w['u2'], tid, iid, 48, reason='yirtilgan').status_code == 200
    # omborchi qabul qilingan hujjatni bekor qila olmaydi
    assert client.login(w['u2']).post(f'/api/transfers/{tid}/cancel').status_code == 403
    # manzilda tovar sotilgan -> 400, hech narsa o'zgarmaydi
    dest = db.query(StockLevel).filter(StockLevel.warehouse_id == w['w2'].id).one()
    dest.quantity = Decimal(10)
    db.flush()
    r = client.login(w['admin']).post(f'/api/transfers/{tid}/cancel')
    assert r.status_code == 400, r.text
    assert db.get(StockTransfer, tid).status == TransferStatus.received
    assert _qty(db, w['p'], w['w1']) == 50.0 and _qty(db, w['p'], w['w2']) == 10.0
    # yetarli qoldiq bo'lsa bekor qilinadi
    dest.quantity = Decimal(48)
    db.flush()
    r = client.login(w['admin']).post(f'/api/transfers/{tid}/cancel')
    assert r.status_code == 200, r.text
    assert _qty(db, w['p'], w['w2']) == 0.0 and _qty(db, w['p'], w['w1']) == 100.0
    assert len(_moves(db, tid)) == 2                      # asl harakatlar saqlanadi


# ─── 5. Bir bosqichli rejim (mezon 7) ───

def test_same_branch_and_branchless_stay_one_step(client, db, w):
    # bir filial ichida
    r = client.login(w['u1']).post('/api/transfers', json=_body(w['w1'], w['w1b'], w['p'], 10))
    assert r.status_code == 200, r.text
    b = r.json()
    assert b['status'] == 'received' and b['two_step'] is False
    assert float(b['items'][0]['qty_sent']) == 10 and float(b['items'][0]['qty_received']) == 10
    assert _qty(db, w['p'], w['w1']) == 90.0 and _qty(db, w['p'], w['w1b']) == 10.0
    assert {m.type: m.warehouse_id for m in _moves(db, b['id'])} == {
        MovementType.TRANSFER_OUT: w['w1'].id, MovementType.TRANSFER_IN: w['w1b'].id}
    # filialsiz omborlar
    r = client.login(w['admin']).post('/api/transfers', json=_body(w['wn'], w['wn2'], w['p'], 7))
    assert r.json()['status'] == 'received' and _qty(db, w['p'], w['wn2']) == 7.0
    # filialli -> filialsiz ham bir bosqichli
    r = client.login(w['admin']).post('/api/transfers', json=_body(w['wn'], w['w2'], w['p'], 4))
    assert r.json()['status'] == 'received'
    # bir bosqichli hujjatni admin hanuz tahrirlay/bekor qila oladi
    tid = b['id']
    r = client.login(w['admin']).put(f'/api/transfers/{tid}', json=_body(w['w1'], w['w1b'], w['p'], 20))
    assert r.status_code == 200, r.text
    assert _qty(db, w['p'], w['w1']) == 80.0 and _qty(db, w['p'], w['w1b']) == 20.0


def test_two_step_override(client, db, w):
    # bir filial ichida majburan ikki bosqichli
    r = client.login(w['u1']).post('/api/transfers', json=_body(w['w1'], w['w1b'], w['p'], 10, two_step=True))
    assert r.json()['status'] == 'in_transit' and _qty(db, w['p'], w['w1b']) is None
    # farqli filiallar, majburan bir bosqichli
    r = client.login(w['admin']).post('/api/transfers', json=_body(w['w1'], w['w2'], w['p'], 5, two_step=False))
    assert r.json()['status'] == 'received' and _qty(db, w['p'], w['w2']) == 5.0


# ─── 6. Ro'yxat va yo'nalish (mezon 8) ───

def test_list_direction_and_isolation(client, db, w):
    out_t = _send_cross(client, w, 10)                                         # Chilonzor -> Yunusobod
    _stock(db, w['p'], w['w3'], 10)
    other = client.login(w['u3']).post('/api/transfers', json=_body(w['w3'], w['w1'], w['p'], 2))
    assert other.status_code == 200, other.text                                 # Sergeli -> Chilonzor
    foreign = client.login(w['ub1']).post('/api/transfers', json=_body(w['wb1'], w['wb2'], w['pb'], 5))
    assert foreign.status_code == 200, foreign.text

    def ids(user, qs=''):
        r = client.login(user).get('/api/transfers' + qs)
        assert r.status_code == 200, r.text
        return {x['id']: x for x in r.json()}

    inc2 = ids(w['u2'], '?direction=incoming')
    assert set(inc2) == {out_t['id']} and inc2[out_t['id']]['direction'] == 'incoming'
    assert inc2[out_t['id']]['can_receive'] is True
    assert float(inc2[out_t['id']]['total_qty']) == 10 and inc2[out_t['id']]['to_branch_name'] == 'Yunusobod'
    out1 = ids(w['u1'], '?direction=outgoing')
    assert set(out1) == {out_t['id']} and out1[out_t['id']]['direction'] == 'outgoing'
    inc1 = ids(w['u1'], '?direction=incoming')
    assert set(inc1) == {other.json()['id']}
    # korxonalar aralashmaydi
    allA = ids(w['admin'])
    assert foreign.json()['id'] not in allA and {out_t['id'], other.json()['id']} <= set(allA)
    allB = ids(w['ub2'])
    assert set(allB) == {foreign.json()['id']}
    assert out_t['id'] not in ids(w['ub2'], '?direction=incoming')
    # branch_id filtri
    assert set(ids(w['admin'], f"?branch_id={w['b2'].id}")) == {out_t['id']}
    assert client.login(w['u1']).get('/api/transfers?direction=sideways').status_code == 422
    # holat filtri
    assert set(ids(w['admin'], '?status=in_transit')) == {out_t['id'], other.json()['id']}


def test_company_isolation_on_actions(client, db, w):
    body = _send_cross(client, w, 10)
    tid, iid = body['id'], body['items'][0]['id']
    cb = client.login(w['ub2'])
    assert cb.get(f'/api/transfers/{tid}').status_code == 404
    assert cb.post(f'/api/transfers/{tid}/send').status_code == 404
    assert cb.post(f'/api/transfers/{tid}/cancel').status_code == 404
    assert _receive(client, w['ub2'], tid, iid, 10).status_code == 404
    assert cb.get(f"/api/transfers/in-transit-summary?warehouse_id={w['w2'].id}").status_code == 404
    # begona ombor bilan yaratish ham 404
    assert cb.post('/api/transfers', json=_body(w['w1'], w['wb2'], w['p'], 1)).status_code == 404
    assert db.get(StockTransfer, tid).status == TransferStatus.in_transit
    # o'z resursi ishlaydi
    r = client.login(w['ub1']).post('/api/transfers', json=_body(w['wb1'], w['wb2'], w['pb'], 5))
    assert r.status_code == 200 and r.json()['status'] == 'in_transit'
    assert _receive(client, w['ub2'], r.json()['id'], r.json()['items'][0]['id'], 5).status_code == 200
    assert _qty(db, w['pb'], w['wb2']) == 5.0


# ─── 7. Tahrir / o'chirish (409) ───

def test_update_delete_two_step_rules(client, db, w):
    draft = _send_cross(client, w, 10, send=False)
    admin = client.login(w['admin'])
    r = admin.put(f"/api/transfers/{draft['id']}", json=_body(w['w1'], w['w2'], w['p'], 25))
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'pending' and float(r.json()['items'][0]['quantity']) == 25
    assert _qty(db, w['p'], w['w1']) == 100.0
    assert admin.post(f"/api/transfers/{draft['id']}/send").status_code == 200
    assert _qty(db, w['p'], w['w1']) == 75.0

    # yo'lda: tahrir va o'chirish 409
    assert admin.put(f"/api/transfers/{draft['id']}", json=_body(w['w1'], w['w2'], w['p'], 5)).status_code == 409
    assert admin.delete(f"/api/transfers/{draft['id']}").status_code == 409
    # qabuldan keyin ham 409
    t = db.get(StockTransfer, draft['id'])
    assert _receive(client, w['u2'], t.id, t.items[0].id, 25).status_code == 200
    admin = client.login(w['admin'])
    assert admin.put(f"/api/transfers/{t.id}", json=_body(w['w1'], w['w2'], w['p'], 5)).status_code == 409
    assert admin.delete(f"/api/transfers/{t.id}").status_code == 409
    assert _qty(db, w['p'], w['w2']) == 25.0

    # qoralamani o'chirish ruxsat
    d2 = _send_cross(client, w, 3, send=False)
    assert client.login(w['admin']).delete(f"/api/transfers/{d2['id']}").status_code == 200
    assert db.get(StockTransfer, d2['id']).status == TransferStatus.cancelled


# ─── 8. Parallel send / konversiya ───

def test_double_send_deducts_once_even_with_stale_status(client, db, w):
    draft = _send_cross(client, w, 30, send=False)
    tid = draft['id']
    t = db.get(StockTransfer, tid)                       # sessiyada status=pending keshlangan
    assert t.status == TransferStatus.pending
    assert client.login(w['u1']).post(f'/api/transfers/{tid}/send').status_code == 200
    # "parallel" so'rov: sessiya keshida eski holat, bazada in_transit
    db.execute(update(StockTransfer).where(StockTransfer.id == tid).values(status=TransferStatus.in_transit))
    set_committed_value(t, 'status', TransferStatus.pending)   # eskirgan kesh (flush yo'q)
    r = client.login(w['u1']).post(f'/api/transfers/{tid}/send')
    assert r.status_code == 409, r.text
    assert _qty(db, w['p'], w['w1']) == 70.0             # ikki marta yechilmadi
    assert len(_moves(db, tid)) == 1


def test_conversion_product_cannot_be_transferred(client, db, w):
    sell = _product(db, w['c'], name='Dumba')
    sell.product_type = 'sell'
    db.flush()
    db.add(ProductConversion(sell_product_id=sell.id, source_product_id=w['p'].id, ratio=Decimal(1)))
    db.flush()
    r = client.login(w['u1']).post('/api/transfers', json=_body(w['w1'], w['w2'], sell, 1))
    assert r.status_code == 400, r.text
    assert _qty(db, w['p'], w['w1']) == 100.0


# ─── 9. Partiyalar ───

def test_batches_taken_on_send_landed_on_receive_returned_on_cancel(client, db, w):
    b = _batch(db, w['p'], w['w1'], 100)
    body = _send_cross(client, w, 50)
    tid, iid = body['id'], body['items'][0]['id']
    db.refresh(b)
    assert b.quantity == Decimal(50)                                         # yuborishda manba partiya kamaydi
    assert db.query(Batch).filter(Batch.warehouse_id == w['w2'].id).count() == 0   # manzilda hali yo'q
    link = db.query(StockTransferBatch).filter(StockTransferBatch.transfer_id == tid).one()
    assert link.dest_batch_id is None and link.item_id == iid

    assert _receive(client, w['u2'], tid, iid, 48, reason='yirtilgan').status_code == 200
    mirror = db.query(Batch).filter(Batch.warehouse_id == w['w2'].id).one()
    assert mirror.quantity == Decimal(48) and mirror.lot_number == 'LOT-1'
    links = db.query(StockTransferBatch).filter(StockTransferBatch.transfer_id == tid).order_by(StockTransferBatch.id).all()
    assert [(l.dest_batch_id is not None, float(l.quantity)) for l in links] == [(True, 48.0), (False, 2.0)]

    assert client.login(w['admin']).post(f'/api/transfers/{tid}/cancel').status_code == 200
    db.refresh(b)
    db.refresh(mirror)
    assert b.quantity == Decimal(100) and mirror.quantity == Decimal(0)
    assert db.query(StockTransferBatch).filter(StockTransferBatch.transfer_id == tid).count() == 0


def test_batches_returned_when_in_transit_cancelled(client, db, w):
    b = _batch(db, w['p'], w['w1'], 100)
    body = _send_cross(client, w, 40)
    db.refresh(b)
    assert b.quantity == Decimal(60)
    assert client.login(w['u1']).post(f"/api/transfers/{body['id']}/cancel").status_code == 200
    db.refresh(b)
    assert b.quantity == Decimal(100)
    assert db.query(StockTransferBatch).filter(StockTransferBatch.transfer_id == body['id']).count() == 0


# ─── 10. Migratsiya va i18n ───

def test_migration_file_shape():
    path = os.path.join(ROOT, 'alembic', 'versions', 't4_1_two_step_transfers.py')
    spec = importlib.util.spec_from_file_location('t4_1_mig', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == 't4_1' and mod.down_revision == 't3_19'
    src = open(path, encoding='utf-8').read()
    for needle in ('sent_by', 'sent_at', 'cancel_reason', 'qty_sent', 'qty_received', 'discrepancy_reason',
                   'ix_stock_transfers_status', 'dest_batch_id DROP NOT NULL', 'item_id'):
        assert needle in src, needle
    assert 'DROP COLUMN' in src.split('def downgrade')[1]


def test_models_have_new_columns():
    cols = StockTransfer.__table__.c
    assert {'sent_by', 'sent_at', 'cancel_reason'} <= set(cols.keys())
    icols = StockTransferItem.__table__.c
    assert {'qty_sent', 'qty_received', 'discrepancy_reason'} <= set(icols.keys())
    assert StockTransferBatch.__table__.c.dest_batch_id.nullable is True
    assert 'ix_stock_transfers_status' in {i.name for i in StockTransfer.__table__.indexes}


def test_i18n_pending_keys_in_all_languages():
    path = os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T4.1.json')
    data = json.load(open(path, encoding='utf-8'))
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en']) and data['uz']
    for k in ('transfers.send', 'transfers.receive', 'transfers.qtyReceived', 'transfers.shortage',
              'transfers.shortageReason', 'transfers.direction'):
        assert k in data['uz'], k
    # Frontendda ishlatilgan hamma 'transfers.*' kalitlari pending faylida bor
    import re
    used = set()
    for rel in ('Operations.jsx', 'Ombor.jsx'):
        src = open(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', rel), encoding='utf-8').read()
        used |= set(re.findall(r"'(transfers\.[A-Za-z.]+)'", src))
    assert used and used <= set(data['uz']), used - set(data['uz'])
