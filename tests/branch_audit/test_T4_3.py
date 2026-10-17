"""T4.3 — Filial narxlari, filial aksiyalari, aksiyani serverda qo'llash, xaridda narx auditi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T4_3.py -q -p no:cacheprovider
"""
import itertools
import json
import os
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.branch_price import BranchProductPrice
from app.models.customer import Customer
from app.models.customer_prices import CustomerPrice
from app.models.inventory import StockLevel
from app.models.moliya import KassaSession, Wallet
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.promotion import Promotion, PromotionBranch, PromotionProduct
from app.models.sale import SaleItem
from app.models.user import UserRole, UserWallet
from app.services.branch_price_service import get_branch_prices, pick_branch_price, resolve_price_branch_id
from app.services.promotion_service import (
    PROMO_NOT_APPLICABLE, apply_item_promotion, best_promotion, calc_promo_discount,
    get_active_promotions, promo_is_current,
)
from app.services.sale_helpers import resolve_item_pricing, resolve_price

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
BP = '/api/branch-prices'
PR = '/api/promotions'


# ── Yordamchilar ──────────────────────────────────────────────────────────────

def _product(db, company, sale='410000', wholesale='400000', wh=None, qty=100, **kw):
    n = next(_seq)
    p = Product(name=kw.pop('name', f'Un {n}'), sku=f'T43-{n}', barcode=f'B43-{n}', company_id=company.id,
                cost_price=Decimal('100'), sale_price=Decimal(sale),
                wholesale_price=Decimal(wholesale) if wholesale else None, **kw)
    db.add(p)
    db.flush()
    for w in ([wh] if wh is not None and not isinstance(wh, (list, tuple)) else (wh or [])):
        db.add(StockLevel(product_id=p.id, warehouse_id=w.id, quantity=Decimal(qty)))
    db.flush()
    return p


def _customer(db, company, **kw):
    n = next(_seq)
    c = Customer(name=f'Mijoz {n}', company_id=company.id, phone=f'99893{n:07d}',
                 debt_balance=Decimal('0'), debt_balances={}, **kw)
    db.add(c)
    db.flush()
    return c


def _bp(db, company, branch, product, sale=None, wholesale=None, variant_id=None):
    row = BranchProductPrice(company_id=company.id, branch_id=branch.id, product_id=product.id,
                             variant_id=variant_id,
                             sale_price=Decimal(sale) if sale is not None else None,
                             wholesale_price=Decimal(wholesale) if wholesale is not None else None)
    db.add(row)
    db.flush()
    return row


def _promo(db, company, name='Aksiya', dtype='percent', value='10', branches=(), products=(), **kw):
    p = Promotion(company_id=company.id, name=name, discount_type=dtype, discount_value=Decimal(value),
                  applies_to='products' if products else 'all', **kw)
    db.add(p)
    db.flush()
    for b in branches:
        db.add(PromotionBranch(promotion_id=p.id, branch_id=b.id))
    for pr in products:
        db.add(PromotionProduct(promotion_id=p.id, product_id=pr.id))
    db.flush()
    db.refresh(p)
    return p


def _wallet(db, company, branch):
    w = Wallet(name=f'Kassa {next(_seq)}', type='cash', balance=Decimal('0'), company_id=company.id,
               branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status='open'))
    db.flush()
    return w


def _item(**kw):
    from app.schemas.sale import SaleItemCreate
    kw.setdefault('product_id', 1)
    kw.setdefault('quantity', Decimal('1'))
    return SaleItemCreate(**kw)


def _sale_body(p, wh, qty=1, price=None, **item):
    it = {'product_id': p.id, 'quantity': qty}
    it.update(item)
    total = (price if price is not None else 0) * qty
    body = {'items': [it], 'payment_type': 'cash', 'paid_amount': total, 'paid_cash': total,
            'payments': [{'type': 'cash', 'amount': total}] if total else [], 'warehouse_id': wh.id}
    return body


@pytest.fixture
def world(db, mk):
    ca = mk.company()
    bs, bt = mk.branch(ca, name='Samarqand'), mk.branch(ca, name='Toshkent')
    ws, wt = mk.warehouse(ca, bs), mk.warehouse(ca, bt)
    admin = mk.user(ca, role=UserRole.admin, branch=bt)
    director = mk.user(ca, role=UserRole.director, branch=None)
    manager_s = mk.user(ca, role=UserRole.manager, branch=bs)
    cashier = mk.user(ca, role=UserRole.cashier, branch=bs)
    _wallet(db, ca, bs)
    cb, bb, wb, admin_b = mk.tenant(UserRole.admin)
    return SimpleNamespace(ca=ca, bs=bs, bt=bt, ws=ws, wt=wt, admin=admin, director=director,
                           manager_s=manager_s, cashier=cashier, cb=cb, bb=bb, wb=wb, admin_b=admin_b)


# ── resolve_price / resolve_item_pricing ustuvorligi (1, 3-mezon) ─────────────

def test_resolve_price_priority(db, world):
    w = world
    p = _product(db, w.ca, sale='410000', wholesale='400000')
    bp = _bp(db, w.ca, w.bs, p, sale='390000', wholesale='380000')
    cp = SimpleNamespace(price=Decimal('370000'))
    no_unit = SimpleNamespace(unit_price=None)
    # unit_price > mijoz narxi > filial narxi > price_type > sale_price
    assert resolve_price(SimpleNamespace(unit_price=Decimal('1')), p, cp, None, bp) == Decimal('1')
    assert resolve_price(no_unit, p, cp, None, bp) == Decimal('370000')
    assert resolve_price(no_unit, p, None, None, bp) == Decimal('390000')
    assert resolve_price(no_unit, p, None, SimpleNamespace(price_type='wholesale'), bp) == Decimal('380000')
    assert resolve_price(no_unit, p, None, None, None) == Decimal('410000')
    # eski chaqiruv imzosi buzilmaydi
    assert resolve_price(no_unit, p, None) == Decimal('410000')


def test_item_pricing_branch_rules(db, world):
    w = world
    p = _product(db, w.ca, sale='410000', wholesale='400000')
    bp = _bp(db, w.ca, w.bs, p, sale='390000')            # faqat chakana
    unit, _d, src = resolve_item_pricing(_item(product_id=p.id), p, None, None, w.admin, branch_price=bp)
    assert unit == Decimal('390000') and src == 'branch_price'
    # wholesale turi: filialda ulgurji narx yo'q -> korxona ulgurji narxi
    ws = _customer(db, w.ca, price_type='wholesale')
    unit, _d, src = resolve_item_pricing(_item(product_id=p.id), p, None, ws, w.admin, branch_price=bp)
    assert unit == Decimal('400000') and src == 'price_type'
    bp.wholesale_price = Decimal('380000')
    unit, _d, src = resolve_item_pricing(_item(product_id=p.id), p, None, ws, w.admin, branch_price=bp)
    assert unit == Decimal('380000') and src == 'branch_price'
    # tannarx turi: filial narxi qo'llanmaydi
    cost = _customer(db, w.ca, price_type='cost')
    unit, _d, src = resolve_item_pricing(_item(product_id=p.id), p, None, cost, w.admin, branch_price=bp)
    assert unit == Decimal('100')
    # mijoz individual narxi filial narxidan ustun
    cp = CustomerPrice(company_id=w.ca.id, customer_id=ws.id, product_id=p.id, price=Decimal('370000'))
    unit, _d, src = resolve_item_pricing(_item(product_id=p.id), p, cp, ws, w.admin, branch_price=bp)
    assert unit == Decimal('370000') and src == 'customer_price'
    # qo'lda narx (price_manual) hamon eng yuqori
    unit, _d, src = resolve_item_pricing(
        _item(product_id=p.id, unit_price=Decimal('1234'), price_manual=True), p, None, None, w.admin, branch_price=bp)
    assert unit == Decimal('1234') and src == 'manual'
    # eski klient korxona narxini yuborgan (price_manual yo'q) -> filial narxi
    unit, _d, src = resolve_item_pricing(
        _item(product_id=p.id, unit_price=Decimal('410000')), p, None, None, w.cashier, branch_price=bp)
    assert unit == Decimal('390000')


# ── get_branch_prices / noyoblik (variant NULL) ───────────────────────────────

def test_get_branch_prices_and_variant_pick(db, world):
    w = world
    p = _product(db, w.ca)
    v = ProductVariant(product_id=p.id, name='XL')
    db.add(v)
    db.flush()
    base = _bp(db, w.ca, w.bs, p, sale='390000')
    var = _bp(db, w.ca, w.bs, p, sale='395000', variant_id=v.id)
    _bp(db, w.ca, w.bt, p, sale='1')
    m = get_branch_prices(db, w.ca.id, w.bs.id, [p.id])
    assert set(m) == {(p.id, None), (p.id, v.id)}
    assert pick_branch_price(m, p.id, v.id) is var
    assert pick_branch_price(m, p.id, None) is base
    assert pick_branch_price(m, p.id, 999) is base            # variantning o'zi yo'q -> mahsulotniki
    assert get_branch_prices(db, w.ca.id, None, [p.id]) == {}
    assert get_branch_prices(db, w.cb.id, w.bs.id, [p.id]) == {}   # begona korxona


def test_resolve_price_branch_no_first_branch_fallback(db, mk, world):
    w = world
    nobranch = mk.user(w.ca, role=UserRole.cashier, branch=None)
    assert resolve_price_branch_id(db, nobranch, None) is None              # "birinchi filial" fallbacki yo'q
    assert resolve_price_branch_id(db, nobranch, w.ws.id) == w.bs.id
    assert resolve_price_branch_id(db, nobranch, w.wb.id) is None           # begona korxona ombori


# ── /branch-prices API (4, 11-mezon + validatsiya) ────────────────────────────

def test_put_upsert_twice_single_row_and_audit(client, db, world):
    w = world
    p = _product(db, w.ca)
    cl = client.login(w.admin)
    r = cl.put(f'{BP}/{w.bs.id}/{p.id}', json={'sale_price': 390000})
    assert r.status_code == 200, r.text
    r = cl.put(f'{BP}/{w.bs.id}/{p.id}', json={'sale_price': 391000})
    assert r.status_code == 200, r.text
    rows = db.query(BranchProductPrice).filter(BranchProductPrice.branch_id == w.bs.id).all()
    assert len(rows) == 1 and Decimal(str(rows[0].sale_price)) == Decimal('391000')
    # faqat ulgurji berilsa chakana narx saqlanadi
    r = cl.put(f'{BP}/{w.bs.id}/{p.id}', json={'wholesale_price': 380000})
    assert r.status_code == 200
    db.refresh(rows[0])
    assert Decimal(str(rows[0].sale_price)) == Decimal('391000') and Decimal(str(rows[0].wholesale_price)) == Decimal('380000')
    logs = db.query(AuditLog).filter(AuditLog.action == 'BRANCH_PRICE_SET').order_by(AuditLog.id).all()
    assert len(logs) == 3
    assert logs[1].old_values['sale_price'] is not None and logs[1].new_values['sale_price'].startswith('391000')


def test_put_validation(client, db, world):
    w = world
    p, p2 = _product(db, w.ca), _product(db, w.ca)
    v2 = ProductVariant(product_id=p2.id, name='L')
    db.add(v2)
    db.flush()
    cl = client.login(w.admin)
    assert cl.put(f'{BP}/{w.bs.id}/{p.id}', json={}).status_code == 400
    assert cl.put(f'{BP}/{w.bs.id}/{p.id}', json={'sale_price': None}).status_code == 400
    assert cl.put(f'{BP}/{w.bs.id}/{p.id}', json={'sale_price': -1}).status_code == 400
    assert cl.put(f'{BP}/{w.bs.id}/{p.id}', json={'wholesale_price': -5}).status_code == 400
    # variant boshqa mahsulotniki -> 404
    assert cl.put(f'{BP}/{w.bs.id}/{p.id}?variant_id={v2.id}', json={'sale_price': 5}).status_code == 404
    assert cl.put(f'{BP}/{w.bs.id}/999999', json={'sale_price': 5}).status_code == 404
    assert db.query(BranchProductPrice).count() == 0
    # nol narx ruxsat
    assert cl.put(f'{BP}/{w.bs.id}/{p.id}', json={'sale_price': 0}).status_code == 200


def test_cross_company_isolation_404(client, db, world, mk):
    w = world
    p_a = _product(db, w.ca)
    p_b = _product(db, w.cb)
    _bp(db, w.cb, w.bb, p_b, sale='5')
    cl = client.login(w.admin)
    # A foydalanuvchisi B filial/mahsulotiga tegolmaydi
    assert cl.put(f'{BP}/{w.bb.id}/{p_a.id}', json={'sale_price': 1}).status_code == 404
    assert cl.put(f'{BP}/{w.bs.id}/{p_b.id}', json={'sale_price': 1}).status_code == 404
    assert cl.delete(f'{BP}/{w.bb.id}/{p_b.id}').status_code == 404
    assert cl.get(f'{BP}?branch_id={w.bb.id}').status_code == 404
    assert cl.post(f'{BP}/{w.bb.id}/bulk', json={'items': []}).status_code == 404
    assert cl.post(f'{BP}/{w.bs.id}/copy-from/{w.bb.id}').status_code == 404
    assert cl.post(f'{BP}/{w.bb.id}/copy-from/{w.bs.id}').status_code == 404
    assert db.query(BranchProductPrice).filter(BranchProductPrice.company_id == w.cb.id).count() == 1
    # ijobiy yo'l: o'z resursi ishlaydi
    assert cl.put(f'{BP}/{w.bs.id}/{p_a.id}', json={'sale_price': 1}).status_code == 200
    r = cl.get(f'{BP}?branch_id={w.bs.id}')
    assert r.status_code == 200 and [i['product_id'] for i in r.json()['items']] == [p_a.id]


def test_delete_returns_to_company_price_and_404(client, db, world):
    w = world
    p = _product(db, w.ca)
    cl = client.login(w.admin)
    assert cl.delete(f'{BP}/{w.bs.id}/{p.id}').status_code == 404       # yozuv yo'q
    cl.put(f'{BP}/{w.bs.id}/{p.id}', json={'sale_price': 390000})
    assert cl.delete(f'{BP}/{w.bs.id}/{p.id}').status_code == 200
    assert db.query(BranchProductPrice).count() == 0
    log = db.query(AuditLog).filter(AuditLog.action == 'BRANCH_PRICE_DELETE').one()
    assert log.old_values['sale_price'].startswith('390000')


def test_list_shows_company_and_branch_price_and_diff(client, db, world):
    w = world
    p = _product(db, w.ca, name='Un 50 kg')
    q = _product(db, w.ca, name='Shakar')
    _bp(db, w.ca, w.bs, p, sale='390000')
    cl = client.login(w.admin)
    r = cl.get(f'{BP}?branch_id={w.bs.id}&search=Un')
    assert r.status_code == 200
    items = r.json()['items']
    assert len(items) == 1 and items[0]['product_id'] == p.id
    assert float(items[0]['branch_sale_price']) == 390000 and float(items[0]['sale_price']) == 410000
    assert float(items[0]['diff_sale']) == -20000 and items[0]['has_override'] is True
    r = cl.get(f'{BP}?branch_id={w.bs.id}&only_overridden=true')
    assert [i['product_id'] for i in r.json()['items']] == [p.id]
    r = cl.get(f'{BP}?branch_id={w.bt.id}')
    assert all(i['has_override'] is False for i in r.json()['items']) and r.json()['total'] == 2


def test_roles(client, db, world):
    w = world
    p = _product(db, w.ca)
    body = {'sale_price': 5}
    assert client.login(w.cashier).put(f'{BP}/{w.bs.id}/{p.id}', json=body).status_code == 403
    assert client.login(w.cashier).get(f'{BP}?branch_id={w.bs.id}').status_code == 403
    # manager: o'z filialida ruxsat, boshqa filialda 403
    assert client.login(w.manager_s).put(f'{BP}/{w.bs.id}/{p.id}', json=body).status_code == 200
    assert client.login(w.manager_s).put(f'{BP}/{w.bt.id}/{p.id}', json=body).status_code == 403
    assert client.login(w.manager_s).delete(f'{BP}/{w.bt.id}/{p.id}').status_code == 403
    assert client.login(w.manager_s).post(f'{BP}/{w.bt.id}/bulk', json={'items': []}).status_code == 403
    # director / admin: hamma filialda
    assert client.login(w.director).put(f'{BP}/{w.bt.id}/{p.id}', json=body).status_code == 200
    assert client.login(w.admin).put(f'{BP}/{w.bs.id}/{p.id}', json=body).status_code == 200


def test_bulk_limit_savepoints_and_errors(client, db, world):
    w = world
    p1, p2 = _product(db, w.ca), _product(db, w.ca)
    p_b = _product(db, w.cb)
    cl = client.login(w.admin)
    too_many = {'items': [{'product_id': p1.id, 'sale_price': 1}] * 1001}
    assert cl.post(f'{BP}/{w.bs.id}/bulk', json=too_many).status_code == 400
    rows = [
        {'product_id': p1.id, 'sale_price': 100},
        {'product_id': p_b.id, 'sale_price': 100},            # begona mahsulot
        {'product_id': p2.id, 'sale_price': -1},              # manfiy
        {'product_id': p2.id},                                # narx yo'q
        {'product_id': p2.id, 'sale_price': 200, 'wholesale_price': 150},
        {'product_id': p1.id, 'sale_price': 100},             # o'zgarmagan -> skipped
    ]
    r = cl.post(f'{BP}/{w.bs.id}/bulk', json={'items': rows})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out['saved'] == 2 and out['skipped'] == 1
    assert [e['row'] for e in out['errors']] == [2, 3, 4]
    assert db.query(BranchProductPrice).filter(BranchProductPrice.branch_id == w.bs.id).count() == 2
    # 1000 qator chegarasi ruxsat
    ok = {'items': [{'product_id': p1.id, 'sale_price': 100}] * 1000}
    assert cl.post(f'{BP}/{w.bs.id}/bulk', json=ok).status_code == 200


def test_copy_from(client, db, world):
    w = world
    p1, p2 = _product(db, w.ca), _product(db, w.ca)
    _bp(db, w.ca, w.bs, p1, sale='390000')
    _bp(db, w.ca, w.bs, p2, sale='10', wholesale='9')
    _bp(db, w.ca, w.bt, p1, sale='1')                          # ustidan yoziladi
    cl = client.login(w.admin)
    assert cl.post(f'{BP}/{w.bs.id}/copy-from/{w.bs.id}').status_code == 400
    r = cl.post(f'{BP}/{w.bt.id}/copy-from/{w.bs.id}')
    assert r.status_code == 200 and r.json()['copied'] == 2
    got = {(r_.product_id): (r_.sale_price, r_.wholesale_price)
           for r_ in db.query(BranchProductPrice).filter(BranchProductPrice.branch_id == w.bt.id)}
    assert Decimal(str(got[p1.id][0])) == Decimal('390000')
    assert Decimal(str(got[p2.id][1])) == Decimal('9')


# ── AC1/AC4: sotuv narxi filial bo'yicha ──────────────────────────────────────

def test_sale_uses_branch_price_by_warehouse(client, db, world):
    w = world
    p = _product(db, w.ca, sale='410000', wholesale='400000', wh=[w.ws, w.wt])
    _bp(db, w.ca, w.bs, p, sale='390000')
    cl = client.login(w.admin)
    r = cl.post('/api/sales/', json=_sale_body(p, w.ws, price=390000))
    assert r.status_code == 200, r.text
    r = cl.post('/api/sales/', json=_sale_body(p, w.wt, price=410000))
    assert r.status_code == 200, r.text
    prices = {si.warehouse_id: Decimal(str(si.unit_price)) for si in db.query(SaleItem).filter(SaleItem.product_id == p.id)}
    assert prices[w.ws.id] == Decimal('390000') and prices[w.wt.id] == Decimal('410000')
    # filial narxi o'chirilgach Samarqand ham korxona narxini oladi
    assert cl.delete(f'{BP}/{w.bs.id}/{p.id}').status_code == 200
    r = cl.post('/api/sales/', json=_sale_body(p, w.ws, price=410000))
    assert r.status_code == 200, r.text
    last = db.query(SaleItem).filter(SaleItem.product_id == p.id).order_by(SaleItem.id.desc()).first()
    assert Decimal(str(last.unit_price)) == Decimal('410000')


def test_customer_price_beats_branch_price_in_pending_sale(client, db, world):
    w = world
    p = _product(db, w.ca)
    _bp(db, w.ca, w.bs, p, sale='390000')
    cust = _customer(db, w.ca)
    db.add(CustomerPrice(company_id=w.ca.id, customer_id=cust.id, product_id=p.id, price=Decimal('370000')))
    db.flush()
    cl = client.login(w.admin)
    body = {'items': [{'product_id': p.id, 'quantity': 1}], 'payment_type': 'debt', 'paid_amount': 0,
            'customer_id': cust.id, 'warehouse_id': w.ws.id}
    r = cl.post('/api/sales/pending', json=body)
    assert r.status_code == 200, r.text
    it = db.query(SaleItem).filter(SaleItem.sale_id == r.json()['id']).one()
    assert Decimal(str(it.unit_price)) == Decimal('370000')
    # mijoz narxi yo'q mijoz uchun filial narxi
    other = _customer(db, w.ca)
    body['customer_id'] = other.id
    r = cl.post('/api/sales/pending', json=body)
    it = db.query(SaleItem).filter(SaleItem.sale_id == r.json()['id']).one()
    assert Decimal(str(it.unit_price)) == Decimal('390000')


# ── AC2: /products/pos-list ───────────────────────────────────────────────────

def test_pos_list_branch_price_and_source(client, db, world):
    w = world
    p = _product(db, w.ca, name='Un 50 kg', wh=[w.ws, w.wt])
    q = _product(db, w.ca, name='Shakar', wh=[w.ws])
    _bp(db, w.ca, w.bs, p, sale='390000')
    cl = client.login(w.admin)
    r = cl.get(f'/api/products/pos-list?branch_id={w.bs.id}&limit=50')
    assert r.status_code == 200, r.text
    by = {i['id']: i for i in r.json()}
    assert by[p.id]['sale_price'] == 390000 and by[p.id]['price_source'] == 'branch'
    assert by[p.id]['wholesale_price'] == 400000                  # ulgurji ustun NULL -> korxona narxi
    assert by[q.id]['sale_price'] == 410000 and by[q.id]['price_source'] == 'product'
    r = cl.get(f'/api/products/pos-list?branch_id={w.bt.id}&limit=50')
    assert {i['price_source'] for i in r.json()} == {'product'}
    # ombor orqali filial aniqlanadi
    r = cl.get(f'/api/products/pos-list?warehouse_id={w.ws.id}&limit=50')
    assert {i['id']: i['sale_price'] for i in r.json()}[p.id] == 390000
    # begona korxona filiali
    assert cl.get(f'/api/products/pos-list?branch_id={w.bb.id}').status_code == 404


# ── promotion_service (sana, universal, filial, eng katta chegirma) ───────────

def test_promo_date_boundaries(db, world):
    w = world
    d = datetime
    promo = _promo(db, w.ca, start_date=d(2026, 10, 15), end_date=d(2026, 10, 20))
    assert not promo_is_current(promo, d(2026, 10, 14, 23, 59))
    assert promo_is_current(promo, d(2026, 10, 15, 0, 0))
    assert promo_is_current(promo, d(2026, 10, 20, 0, 0))
    assert promo_is_current(promo, d(2026, 10, 20, 23, 59, 59))      # sana ko'rinishida -> kun oxirigacha
    assert not promo_is_current(promo, d(2026, 10, 21, 0, 0))
    timed = _promo(db, w.ca, end_date=d(2026, 10, 20, 12, 0))         # vaqt aniq berilgan
    assert promo_is_current(timed, d(2026, 10, 20, 12, 0))
    assert not promo_is_current(timed, d(2026, 10, 20, 12, 1))
    open_ended = _promo(db, w.ca)
    assert promo_is_current(open_ended, d(2030, 1, 1))
    off = _promo(db, w.ca, is_active=False)
    assert not promo_is_current(off, d(2026, 10, 16))


def test_promo_branch_product_filter_and_best(db, world):
    w = world
    p1, p2 = _product(db, w.ca), _product(db, w.ca)
    all_ = _promo(db, w.ca, 'Hamma', value='5')
    only_s = _promo(db, w.ca, 'Samarqand', value='10', branches=[w.bs])
    p1_only = _promo(db, w.ca, 'Faqat p1', dtype='amount', value='50000', products=[p1], branches=[w.bs, w.bt])
    now = datetime(2026, 10, 16)
    ids = lambda lst: {x.id for x in lst}
    assert ids(get_active_promotions(db, w.ca.id, w.bs.id, [p1.id], now)) == {all_.id, only_s.id, p1_only.id}
    assert ids(get_active_promotions(db, w.ca.id, w.bt.id, [p1.id], now)) == {all_.id, p1_only.id}
    assert ids(get_active_promotions(db, w.ca.id, w.bt.id, [p2.id], now)) == {all_.id}         # p1_only p2 ni qamramaydi
    assert ids(get_active_promotions(db, w.ca.id, None, None, now)) == {all_.id}              # filialsiz: faqat universal
    assert get_active_promotions(db, w.cb.id, w.bs.id, [p1.id], now) == []                    # begona korxona
    # eng katta chegirma: 10000 * 2 -> foiz 2000 / summa 100000 (narxdan oshmaydi: 10000*2=20000)
    promos = get_active_promotions(db, w.ca.id, w.bs.id, [p1.id], now)
    best, disc = best_promotion(promos, p1.id, Decimal('10000'), Decimal('2'))
    assert best.id == p1_only.id and disc == Decimal('20000.00')
    assert calc_promo_discount(only_s, Decimal('10000'), Decimal('2')) == Decimal('2000.00')
    assert calc_promo_discount(p1_only, Decimal('30000'), Decimal('2')) == Decimal('60000.00')   # summa narxdan oshmaydi


def test_apply_item_promotion_rules(db, world):
    w = world
    p = _product(db, w.ca)
    promo = _promo(db, w.ca, value='10')
    promos = [promo]
    # promotion_id berilgan: chegirma o'zgarmaydi, ulush min(server, discount)
    assert apply_item_promotion(promos, p.id, promo.id, Decimal('10000'), Decimal('2'), Decimal('2000')) == \
        (Decimal('2000'), promo.id, Decimal('2000.00'))
    assert apply_item_promotion(promos, p.id, promo.id, Decimal('10000'), Decimal('2'), Decimal('500'))[2] == Decimal('500')
    assert apply_item_promotion(promos, p.id, promo.id, Decimal('10000'), Decimal('2'), Decimal('9000'))[2] == Decimal('2000.00')
    with pytest.raises(HTTPException) as ei:
        apply_item_promotion(promos, p.id, 999999, Decimal('10000'), Decimal('1'), Decimal('0'))
    assert ei.value.status_code == 400 and ei.value.detail == PROMO_NOT_APPLICABLE
    # auto: o'chiq bo'lsa o'zgarmaydi, yoqilsa eng yaxshi aksiya
    assert apply_item_promotion(promos, p.id, None, Decimal('10000'), Decimal('2'), Decimal('0')) == (Decimal('0'), None, None)
    assert apply_item_promotion(promos, p.id, None, Decimal('10000'), Decimal('2'), Decimal('0'), auto_apply=True) == \
        (Decimal('2000.00'), promo.id, Decimal('2000.00'))
    # mavjud chegirma kattaroq bo'lsa aksiya qo'llanmaydi (ikki marta chegirma yo'q)
    assert apply_item_promotion(promos, p.id, None, Decimal('10000'), Decimal('2'), Decimal('5000'), auto_apply=True) == \
        (Decimal('5000'), None, None)


# ── /promotions API: branch_ids, active, rol (5, 8, 9, 11-mezon) ──────────────

def test_promotions_branch_ids_crud_and_isolation(client, db, world):
    w = world
    cl = client.login(w.manager_s)
    r = cl.post(PR + '/', json={'name': 'Sergeli', 'discount_type': 'percent', 'discount_value': 10,
                                'branch_ids': [w.bs.id]})
    assert r.status_code == 201, r.text
    pid = r.json()['id']
    assert r.json()['branch_ids'] == [w.bs.id]
    # begona filial -> 404, aksiya yaratilmaydi
    n = db.query(Promotion).count()
    r = cl.post(PR + '/', json={'name': 'X', 'discount_type': 'percent', 'discount_value': 10, 'branch_ids': [w.bb.id]})
    assert r.status_code == 404 and db.query(Promotion).count() == n
    assert cl.put(f'{PR}/{pid}', json={'branch_ids': [w.bb.id]}).status_code == 404
    # yangilash: almashtirish, [] = hamma, berilmasa o'zgarmaydi
    assert sorted(cl.put(f'{PR}/{pid}', json={'branch_ids': [w.bt.id, w.bs.id]}).json()['branch_ids']) == sorted([w.bt.id, w.bs.id])
    assert sorted(cl.put(f'{PR}/{pid}', json={'name': 'Y'}).json()['branch_ids']) == sorted([w.bt.id, w.bs.id])
    assert cl.put(f'{PR}/{pid}', json={'branch_ids': []}).json()['branch_ids'] == []
    # begona korxona aksiyasi
    assert client.login(w.admin_b).put(f'{PR}/{pid}', json={'name': 'Z'}).status_code == 404
    # kassir yozolmaydi
    assert client.login(w.cashier).post(PR + '/', json={'name': 'X', 'discount_value': 1}).status_code == 403
    assert client.login(w.cashier).put(f'{PR}/{pid}', json={'name': 'Q'}).status_code == 403
    assert client.login(w.cashier).delete(f'{PR}/{pid}').status_code == 403
    # o'chirilganda promotion_branches ham ketadi
    cl2 = client.login(w.admin)
    cl2.put(f'{PR}/{pid}', json={'branch_ids': [w.bs.id]})
    assert cl2.delete(f'{PR}/{pid}').status_code == 204
    assert db.query(PromotionBranch).count() == 0


def test_promotions_active_endpoint(client, db, world):
    w = world
    _promo(db, w.ca, 'Hamma')
    _promo(db, w.ca, 'Samarqand', branches=[w.bs])
    _promo(db, w.ca, 'Tugagan', end_date=datetime(2020, 1, 1))
    _promo(db, w.ca, 'Nofaol', is_active=False)
    _promo(db, w.cb, 'Begona')
    cl = client.login(w.cashier)                                   # kassir filiali = Samarqand
    names = lambda r: sorted(x['name'] for x in r.json())
    assert names(cl.get(PR + '/active')) == ['Hamma', 'Samarqand']
    assert names(cl.get(f'{PR}/active?branch_id={w.bt.id}')) == ['Hamma']
    assert cl.get(f'{PR}/active?branch_id={w.bb.id}').status_code == 404


def test_promotion_auto_apply_setting_endpoint(client, db, world):
    w = world
    assert client.login(w.cashier).get(PR + '/settings').json() == {'auto_apply': False}
    assert client.login(w.cashier).put(PR + '/settings', json={'auto_apply': True}).status_code == 403
    assert client.login(w.manager_s).put(PR + '/settings', json={'auto_apply': True}).status_code == 403
    assert client.login(w.admin).put(PR + '/settings', json={'auto_apply': True}).json() == {'auto_apply': True}
    db.refresh(w.ca)
    assert w.ca.promotions_auto_apply is True
    assert client.login(w.admin_b).get(PR + '/settings').json() == {'auto_apply': False}


# ── Sotuvda aksiya (5, 6, 7, 9-mezon) ─────────────────────────────────────────

def _promo_sale(client, user, p, wh, promo_id, qty=2, discount=2000, price=10000):
    total = price * qty - discount
    body = _sale_body(p, wh, qty=qty, price=total, promotion_id=promo_id, discount=discount)
    return client.login(user).post('/api/sales/', json=body)


def test_sale_promotion_branch_validation(client, db, world):
    w = world
    p = _product(db, w.ca, sale='10000', wholesale=None, wh=[w.ws, w.wt])
    promo = _promo(db, w.ca, 'Faqat Samarqand', value='10', branches=[w.bs])
    r = _promo_sale(client, w.admin, p, w.wt, promo.id)
    assert r.status_code == 400 and r.json()['detail'] == PROMO_NOT_APPLICABLE
    assert db.query(SaleItem).count() == 0
    r = _promo_sale(client, w.admin, p, w.ws, promo.id)
    assert r.status_code == 200, r.text
    it = db.query(SaleItem).one()
    assert it.promotion_id == promo.id and Decimal(str(it.promotion_discount)) == Decimal('2000')
    assert Decimal(str(it.discount)) == Decimal('2000')                   # ikki marta chegirma yo'q


def test_sale_promotion_expired_inactive_and_dateonly_last_day(client, db, world):
    w = world
    p = _product(db, w.ca, sale='10000', wholesale=None, wh=[w.ws])
    expired = _promo(db, w.ca, end_date=datetime(2020, 1, 1))
    inactive = _promo(db, w.ca, is_active=False)
    future = _promo(db, w.ca, start_date=datetime(2999, 1, 1))
    for pr in (expired, inactive, future):
        r = _promo_sale(client, w.admin, p, w.ws, pr.id)
        assert r.status_code == 400 and r.json()['detail'] == PROMO_NOT_APPLICABLE
    # sana ko'rinishidagi end_date = bugun (00:00) -> bugun kun oxirigacha amal qiladi
    from app.services.promotion_service import local_now
    today = local_now().replace(hour=0, minute=0, second=0, microsecond=0)
    last_day = _promo(db, w.ca, end_date=today)
    assert _promo_sale(client, w.admin, p, w.ws, last_day.id).status_code == 200


def test_sale_promotion_universal_and_product_scope(client, db, world):
    w = world
    p1 = _product(db, w.ca, sale='10000', wholesale=None, wh=[w.ws])
    p2 = _product(db, w.ca, sale='10000', wholesale=None, wh=[w.ws])
    universal = _promo(db, w.ca, 'Universal')
    scoped = _promo(db, w.ca, 'Faqat p1', products=[p1])
    assert _promo_sale(client, w.admin, p2, w.ws, universal.id).status_code == 200        # universal -> hamma mahsulot
    r = _promo_sale(client, w.admin, p2, w.ws, scoped.id)
    assert r.status_code == 400 and r.json()['detail'] == PROMO_NOT_APPLICABLE
    assert _promo_sale(client, w.admin, p1, w.ws, scoped.id).status_code == 200


def test_sale_promotion_discount_capped_by_item_discount(client, db, world):
    w = world
    p = _product(db, w.ca, sale='10000', wholesale=None, wh=[w.ws])
    promo = _promo(db, w.ca, value='10')
    # klient 500 chegirma yubordi (aksiya 2000 hisoblaydi) -> ulush 500, qo'shimcha chegirma yo'q
    r = _promo_sale(client, w.admin, p, w.ws, promo.id, discount=500)
    assert r.status_code == 200, r.text
    it = db.query(SaleItem).one()
    assert Decimal(str(it.promotion_discount)) == Decimal('500') and Decimal(str(it.discount)) == Decimal('500')


def test_sale_auto_apply_toggle(client, db, world):
    w = world
    p = _product(db, w.ca, sale='10000', wholesale=None, wh=[w.ws], qty=100)
    promo = _promo(db, w.ca, value='10')
    small = _promo(db, w.ca, 'Kichik', value='1')
    # o'chiq: chegirma o'zgarmaydi
    body = _sale_body(p, w.ws, qty=2, price=20000)
    assert client.login(w.admin).post('/api/sales/', json=body).status_code == 200
    it = db.query(SaleItem).one()
    assert Decimal(str(it.discount)) == 0 and it.promotion_id is None
    # yoqilgan: eng katta chegirmali aksiya avtomatik
    w.ca.promotions_auto_apply = True
    db.flush()
    body = _sale_body(p, w.ws, qty=2, price=18000)
    r = client.login(w.admin).post('/api/sales/', json=body)
    assert r.status_code == 200, r.text
    it = db.query(SaleItem).order_by(SaleItem.id.desc()).first()
    assert it.promotion_id == promo.id and Decimal(str(it.discount)) == Decimal('2000')
    assert Decimal(str(it.promotion_discount)) == Decimal('2000')
    assert small.id != it.promotion_id


def test_pending_sale_promotion_checked_and_saved(client, db, world):
    w = world
    p = _product(db, w.ca, sale='10000', wholesale=None)
    cust = _customer(db, w.ca)
    promo = _promo(db, w.ca, value='10', branches=[w.bs])

    def body(wh, pid):
        return {'items': [{'product_id': p.id, 'quantity': 2, 'discount': 2000, 'promotion_id': pid}],
                'payment_type': 'debt', 'paid_amount': 0, 'customer_id': cust.id, 'warehouse_id': wh.id}
    cl = client.login(w.admin)
    assert cl.post('/api/sales/pending', json=body(w.wt, promo.id)).status_code == 400
    r = cl.post('/api/sales/pending', json=body(w.ws, promo.id))
    assert r.status_code == 200, r.text
    it = db.query(SaleItem).filter(SaleItem.sale_id == r.json()['id']).one()
    assert it.promotion_id == promo.id and Decimal(str(it.promotion_discount)) == Decimal('2000')


# ── Xaridda narx o'zgarishi auditi (10-mezon) ─────────────────────────────────

def test_receipt_price_change_audited(db, world):
    from app.services.purchase_order_service import _update_product_on_receipt
    w = world
    p = _product(db, w.ca, sale='410000', wholesale='400000')
    item = SimpleNamespace(unit_cost=Decimal('150'), variant_id=None, variant=None, po_id=1,
                           new_sale_price=Decimal('420000'), new_wholesale_price=None)
    _update_product_on_receipt(db, p, item, w.ca.id, w.admin, branch_id=w.bs.id)
    log = db.query(AuditLog).filter(AuditLog.action == 'PRICE_CHANGE').one()
    assert log.entity_type == 'product' and log.entity_id == p.id and log.branch_id == w.bs.id
    assert log.old_values['sale_price'].startswith('410000') and log.new_values['sale_price'].startswith('420000')
    assert log.old_values['cost_price'].startswith('100') and log.new_values['cost_price'].startswith('150')
    assert 'wholesale_price' not in log.new_values
    # hech narx o'zgarmasa log yozilmaydi
    item2 = SimpleNamespace(unit_cost=Decimal('150'), variant_id=None, variant=None, po_id=1,
                            new_sale_price=None, new_wholesale_price=None)
    _update_product_on_receipt(db, p, item2, w.ca.id, w.admin)
    assert db.query(AuditLog).filter(AuditLog.action == 'PRICE_CHANGE').count() == 1


# ── Migratsiya, model, frontend ───────────────────────────────────────────────

def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def test_migration_matches_models():
    src = _read('alembic/versions/t4_3_branch_prices_promotions.py')
    assert "revision: str = 't4_3'" in src and "down_revision: Union[str, None] = 't4_2'" in src
    for token in ('branch_product_prices', 'uq_branch_product_price', 'COALESCE(variant_id, 0)', 'promotion_branches',
                  'ix_promotion_branches_branch', 'promotion_discount', 'ix_sale_items_promotion',
                  'promotions_auto_apply', 'ON DELETE CASCADE', 'ON DELETE SET NULL', 'DROP TABLE IF EXISTS'):
        assert token in src, token
    idx = {i.name for i in BranchProductPrice.__table__.indexes}
    assert 'uq_branch_product_price' in idx
    assert PromotionBranch.__table__.c.promotion_id.primary_key and PromotionBranch.__table__.c.branch_id.primary_key
    assert {'promotion_id', 'promotion_discount'} <= set(SaleItem.__table__.c.keys())


def test_pending_i18n_keys_in_all_languages():
    with open(os.path.join(ROOT, 'tests/branch_audit/i18n_pending/T4.3.json'), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    for k in ('promotion.allBranches', 'branchPrices.title', 'promotion.autoApply'):
        assert k in data['uz']


def test_frontend_wiring():
    ul = _read('frontend/src/pages/admin/UlgurjiSotuv.jsx')
    assert '/promotions/active' in ul and 'promotion_id' in ul
    pr = _read('frontend/src/pages/admin/Promotions.jsx')
    assert 'branch_ids' in pr and '/promotions/settings' in pr
    pos = _read('frontend/src/pages/admin/PosKassa.jsx')
    assert 'price_source' in pos and 'branch_id' in pos
    prods = _read('frontend/src/pages/admin/Products.jsx')
    assert '/branch-prices' in prods
