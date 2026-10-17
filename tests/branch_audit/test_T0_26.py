"""T0.26 — Mijoz moliyaviy maydonlari: rol, qisman PUT, lost update, o'chirish.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T0_26.py -q -p no:cacheprovider
"""
import itertools
import os
from decimal import Decimal

import pytest
from sqlalchemy.orm import Query

from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.customer_document import CustomerDocument
from app.models.customer_prices import CustomerPrice
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.user import UserRole

_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _cust(db, company, branch=None, **kw):
    n = next(_seq)
    c = Customer(name=kw.pop('name', f'Mijoz {n}'), company_id=company.id,
                 branch_id=branch.id if branch else None,
                 phone=kw.pop('phone', f'99890{n:07d}'), **kw)
    db.add(c)
    db.flush()
    return c


def _product(db, company):
    n = next(_seq)
    p = Product(name=f'Tovar {n}', sku=f'T026-{n}', barcode=f'B026-{n}', company_id=company.id,
                sale_price=Decimal('1000'))
    db.add(p)
    db.flush()
    return p


def _sale(db, company, user, customer, status=SaleStatus.completed):
    n = next(_seq)
    s = Sale(number=f'T026-{n:06d}', cashier_id=user.id, total_amount=Decimal('1000'),
             paid_amount=Decimal('1000'), payment_type=PaymentType.cash, status=status,
             company_id=company.id, customer_id=customer.id)
    db.add(s)
    db.flush()
    return s


def _order(db, company, branch, customer, product, status=OrderStatus.pending):
    o = Order(company_id=company.id, customer_id=customer.id, branch_id=branch.id, product_id=product.id,
              quantity=1, unit_price=Decimal('1000'), total_amount=Decimal('1000'), status=status)
    db.add(o)
    db.flush()
    return o


def _actions(db, action):
    return db.query(AuditLog).filter(AuditLog.action == action).all()


@pytest.fixture
def world(db, mk):
    """Korxona A (admin, kassir, omborchi, manager, buxgalter) va korxona B (admin)."""
    ca, ba, wa, admin = mk.tenant(UserRole.admin)
    cashier = mk.user(ca, role=UserRole.cashier, branch=ba)
    storekeeper = mk.user(ca, role=UserRole.warehouse, branch=ba)
    manager = mk.user(ca, role=UserRole.manager, branch=ba)
    accountant = mk.user(ca, role=UserRole.accountant, branch=ba)
    # T2.6: qarz to'lovi ochiq kassasiz endi 400 — korxona A ga ochiq kassa beramiz
    from app.models.moliya import Wallet
    db.add(Wallet(name='Kassa A', company_id=ca.id, branch_id=ba.id, is_active=True, is_open=True))
    db.flush()
    cb, bb, wb, admin_b = mk.tenant(UserRole.admin)
    return dict(ca=ca, ba=ba, wa=wa, admin=admin, cashier=cashier, storekeeper=storekeeper,
                manager=manager, accountant=accountant, cb=cb, bb=bb, admin_b=admin_b)


# ── 1. Rol: kassir shartlar maydonini o'zgartira olmaydi ─────────────────────

def test_cashier_cannot_change_terms_via_put(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], cashback_percent=Decimal('3'), price_type='sale', debt_limit=Decimal('1000'))
    cl = client.login(w['cashier'])
    r = cl.put(f'/api/customers/{c.id}', json={'name': c.name, 'cashback_percent': 50})
    assert r.status_code == 403 and 'cashback_percent' in r.json()['detail']
    r = cl.put(f'/api/customers/{c.id}', json={'name': c.name, 'price_type': 'cost'})
    assert r.status_code == 403
    r = cl.put(f'/api/customers/{c.id}', json={'name': c.name, 'debt_limit': 99999999})
    assert r.status_code == 403
    db.refresh(c)
    assert c.cashback_percent == Decimal('3') and c.price_type == 'sale' and c.debt_limit == Decimal('1000')


def test_cashier_resending_same_terms_is_ok(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], cashback_percent=Decimal('3'), price_type='wholesale',
              debt_limit=Decimal('1000'), discount_percent=Decimal('5'))
    cl = client.login(w['cashier'])
    r = cl.put(f'/api/customers/{c.id}', json={
        'name': 'Yangi ism', 'phone': c.phone, 'cashback_percent': 3, 'price_type': 'wholesale',
        'debt_limit': 1000, 'discount_percent': 5})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.name == 'Yangi ism' and c.cashback_percent == Decimal('3') and c.price_type == 'wholesale'
    assert not _actions(db, 'CUSTOMER_TERMS')


def test_manager_can_change_terms_and_it_is_logged(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'])
    r = client.login(w['manager']).put(f'/api/customers/{c.id}', json={'name': c.name, 'cashback_percent': 5})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.cashback_percent == Decimal('5')
    logs = _actions(db, 'CUSTOMER_TERMS')
    assert len(logs) == 1 and logs[0].user_id == w['manager'].id
    assert logs[0].new_values['cashback_percent'] and logs[0].old_values['cashback_percent'] is not None


# ── 2. Boshqa endpointlarda rol ──────────────────────────────────────────────

def test_cashier_forbidden_on_privileged_endpoints(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'])
    p = _product(db, w['ca'])
    cl = client.login(w['cashier'])
    assert cl.post('/api/customers/recalc-debts').status_code == 403
    assert cl.post(f'/api/customers/{c.id}/adjust-points', json={'delta': 5, 'reason': 'sabab bor'}).status_code == 403
    assert cl.post(f'/api/customers/{c.id}/adjust-debt',
                   json={'reason': 'sabab', 'changes': [{'currency': 'UZS', 'delta': '10'}]}).status_code == 403
    assert cl.delete(f'/api/customers/{c.id}').status_code == 403
    assert cl.post(f'/api/customers/{c.id}/prices', json={'product_id': p.id, 'price': 1}).status_code == 403
    assert cl.put(f'/api/customers/{c.id}/assign-branch', params={'branch_id': w['ba'].id}).status_code == 403
    assert db.query(Customer).filter(Customer.id == c.id).count() == 1


def test_pay_debt_cashier_ok_warehouse_forbidden(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('100000'), debt_balances={'UZS': 100000.0})
    r = client.login(w['storekeeper']).post(f'/api/customers/{c.id}/pay-debt',
                                            json={'amount': 1000, 'reason': 'to\'lov'})
    assert r.status_code == 403
    r = client.login(w['cashier']).post(f'/api/customers/{c.id}/pay-debt',
                                        json={'amount': 40000, 'reason': "to'lov", 'payment_type': 'cash'})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.debt_balances['UZS'] == 60000.0 and c.debt_balance == Decimal('60000')


def test_pay_debt_invalid_payment_type_400(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('1000'), debt_balances={'UZS': 1000.0})
    r = client.login(w['cashier']).post(f'/api/customers/{c.id}/pay-debt',
                                        json={'amount': 500, 'reason': 'x', 'payment_type': 'debt'})
    assert r.status_code == 400
    r = client.login(w['cashier']).post(f'/api/customers/{c.id}/pay-debt',
                                        json={'amount': 500, 'reason': 'x', 'payment_type': 'cashback'})
    assert r.status_code == 400


def test_assign_branch_manager_ok(client, db, world):
    w = world
    c = _cust(db, w['ca'])
    r = client.login(w['manager']).put(f'/api/customers/{c.id}/assign-branch', params={'branch_id': w['ba'].id})
    assert r.status_code == 200
    db.refresh(c)
    assert c.branch_id == w['ba'].id


def test_custom_price_manager_logged_and_cashier_delete_forbidden(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'])
    p = _product(db, w['ca'])
    cl = client.login(w['manager'])
    assert cl.post(f'/api/customers/{c.id}/prices', json={'product_id': p.id, 'price': 777}).status_code == 201
    assert cl.post(f'/api/customers/{c.id}/prices', json={'product_id': p.id, 'price': 800}).status_code == 201
    assert len(_actions(db, 'CUSTOMER_PRICE')) == 2
    assert client.login(w['cashier']).delete(f'/api/customers/{c.id}/prices/{p.id}').status_code == 403
    assert client.login(w['manager']).delete(f'/api/customers/{c.id}/prices/{p.id}').status_code == 204
    assert db.query(CustomerPrice).filter(CustomerPrice.customer_id == c.id).count() == 0


# ── 3, 4. Qisman PUT ─────────────────────────────────────────────────────────

def test_partial_put_keeps_everything(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], card_number='8888 1111', debt_balance=Decimal('1000000'),
              debt_balances={'UZS': 1000000.0}, debt_limit=Decimal('5000000'), loyalty_points=300,
              cashback_percent=Decimal('2.5'), price_type='wholesale', customer_type='distributor',
              territory='Sergeli')
    phone = c.phone
    r = client.login(w['admin']).put(f'/api/customers/{c.id}', json={'name': 'X'})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.name == 'X' and c.phone == phone and c.card_number == '8888 1111'
    assert c.debt_balances == {'UZS': 1000000.0} and c.debt_balance == Decimal('1000000')
    assert c.debt_limit == Decimal('5000000') and c.loyalty_points == 300
    assert c.cashback_percent == Decimal('2.5') and c.price_type == 'wholesale'
    assert c.customer_type == 'distributor' and c.territory == 'Sergeli'
    assert not c.debt_edited


def test_put_with_different_debt_400_and_db_untouched(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('1000000'), debt_balances={'UZS': 1000000.0},
              loyalty_points=10)
    cl = client.login(w['admin'])
    r = cl.put(f'/api/customers/{c.id}', json={'name': c.name, 'debt_balances': {'UZS': 0}})
    assert r.status_code == 400 and 'adjust-debt' in r.json()['detail']
    r = cl.put(f'/api/customers/{c.id}', json={'name': c.name, 'debt_balance': 5})
    assert r.status_code == 400
    r = cl.put(f'/api/customers/{c.id}', json={'name': c.name, 'loyalty_points': 99999})
    assert r.status_code == 400
    db.refresh(c)
    assert c.debt_balances == {'UZS': 1000000.0} and c.debt_balance == Decimal('1000000') and c.loyalty_points == 10


def test_put_with_same_debt_is_ignored(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('1000000'), debt_balances={'UZS': 1000000.0},
              loyalty_points=10)
    r = client.login(w['admin']).put(f'/api/customers/{c.id}', json={
        'name': 'Y', 'debt_balance': 1000000, 'debt_currency': 'UZS',
        'debt_balances': {'UZS': 1000000}, 'loyalty_points': 10})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.name == 'Y' and c.debt_balances == {'UZS': 1000000.0} and not c.debt_edited


# ── 5. adjust-debt ───────────────────────────────────────────────────────────

def test_adjust_debt_applies_delta_logs_and_audits(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('100000'), debt_balances={'UZS': 100000.0})
    r = client.login(w['accountant']).post(f'/api/customers/{c.id}/adjust-debt', json={
        'reason': 'Kassa xatosi tuzatildi', 'changes': [{'currency': 'UZS', 'delta': '-50000'}]})
    assert r.status_code == 200, r.text
    assert r.json()['debt_balances']['UZS'] == 50000.0
    db.refresh(c)
    assert c.debt_balances['UZS'] == 50000.0 and c.debt_balance == Decimal('50000')
    last = c.debt_edited[-1]
    assert last['edited_by']['id'] == w['accountant'].id and last['reason'] == 'Kassa xatosi tuzatildi'
    assert last['branch_id'] == w['ba'].id
    assert last['edited_from'] == {'UZS': 100000.0} and last['edited_to'] == {'UZS': 50000.0}
    logs = _actions(db, 'ADJUST_DEBT')
    assert len(logs) == 1 and logs[0].entity_id == c.id and logs[0].user_id == w['accountant'].id
    # tarix endpointi kim va sababni qaytaradi
    h = client.login(w['admin']).get(f'/api/customers/{c.id}/history').json()
    edit = [x for x in h if x['op_type'] == 'debt_edit' and x.get('reason')]
    assert edit and edit[0]['edited_by']['id'] == w['accountant'].id and edit[0]['branch_id'] == w['ba'].id


def test_adjust_debt_validation(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('1000'), debt_balances={'UZS': 1000.0})
    cl = client.login(w['admin'])
    url = f'/api/customers/{c.id}/adjust-debt'
    ok = {'currency': 'UZS', 'delta': '-10'}
    assert cl.post(url, json={'reason': '  ', 'changes': [ok]}).status_code == 400
    assert cl.post(url, json={'changes': [ok]}).status_code == 400
    assert cl.post(url, json={'reason': 'sabab', 'changes': []}).status_code == 400
    assert cl.post(url, json={'reason': 'sabab', 'changes': [{'currency': 'UZS', 'delta': '0'}]}).status_code == 400
    assert cl.post(url, json={'reason': 'sabab', 'changes': [{'currency': 'UZS', 'delta': '-5000'}]}).status_code == 400
    assert cl.post(url, json={'reason': 'sabab', 'changes': [{'currency': 'XYZ', 'delta': '5'}]}).status_code == 400
    db.refresh(c)
    assert c.debt_balances == {'UZS': 1000.0} and not c.debt_edited
    assert not _actions(db, 'ADJUST_DEBT')


def test_adjust_debt_foreign_company_404_and_increase(client, db, world):
    w = world
    mine = _cust(db, w['ca'], w['ba'])
    theirs = _cust(db, w['cb'], w['bb'], debt_balance=Decimal('10'), debt_balances={'UZS': 10.0})
    cl = client.login(w['admin'])
    body = {'reason': 'sabab bor', 'changes': [{'currency': 'UZS', 'delta': '2500'}]}
    assert cl.post(f'/api/customers/{theirs.id}/adjust-debt', json=body).status_code == 404
    r = cl.post(f'/api/customers/{mine.id}/adjust-debt', json=body)
    assert r.status_code == 200 and r.json()['debt_balances']['UZS'] == 2500.0
    db.refresh(theirs)
    assert theirs.debt_balances == {'UZS': 10.0}


# ── adjust-points ────────────────────────────────────────────────────────────

def test_adjust_points_requires_reason_and_logs(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], loyalty_points=10)
    cl = client.login(w['admin'])
    url = f'/api/customers/{c.id}/adjust-points'
    assert cl.post(url, json={'delta': 5}).status_code == 422
    assert cl.post(url, json={'delta': 5, 'reason': 'ab'}).status_code == 422
    assert cl.post(url, json={'delta': -50, 'reason': 'xato ball'}).status_code == 400
    r = cl.post(url, json={'delta': 5, 'reason': "Aksiya uchun qo'shildi"})
    assert r.status_code == 200 and r.json()['loyalty_points'] == 15
    log = _actions(db, 'ADJUST_POINTS')
    assert len(log) == 1 and log[0].new_values['reason'] == "Aksiya uchun qo'shildi"
    assert log[0].old_values['loyalty_points'] == 10 and log[0].new_values['delta'] == 5


# ── 6, 7. Lost update va parallel amallar ────────────────────────────────────

def _debt_sale_data(product, warehouse, customer, amount):
    from app.schemas.sale import SaleCreate
    return SaleCreate(items=[{"product_id": product.id, "quantity": 1, "unit_price": amount}],
                      payment_type="debt", paid_amount=Decimal("0"), warehouse_id=warehouse.id,
                      customer_id=customer.id)


def test_stale_form_put_does_not_wipe_new_sale_debt(client, db, world):
    """Forma ochilgandagi qarz 1 000 000; keyin 500 000 nasiya; faqat telefon o'zgartirib PUT."""
    from app.services.sale_create import create_sale
    w = world
    p = _product(db, w['ca'])
    c = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('1000000'), debt_balances={'UZS': 1000000.0})
    create_sale(db, _debt_sale_data(p, w['wa'], c, 500000), w['admin'])
    db.refresh(c)
    assert c.debt_balances['UZS'] == 1500000.0
    r = client.login(w['admin']).put(f'/api/customers/{c.id}', json={'name': c.name, 'phone': '998901112233'})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.phone == '998901112233'
    assert c.debt_balances['UZS'] == 1500000.0 and c.debt_balance == Decimal('1500000')
    # Eskirgan forma (qarz 1 000 000) to'liq payload yuborsa — jimgina yozilmaydi, 400
    r = client.login(w['admin']).put(f'/api/customers/{c.id}', json={
        'name': c.name, 'debt_balance': 1000000, 'debt_balances': {'UZS': 1000000}})
    assert r.status_code == 400
    db.refresh(c)
    assert c.debt_balances['UZS'] == 1500000.0


def test_sale_then_pay_debt_equals_sequential_result(client, db, world):
    from app.services.sale_create import create_sale
    w = world
    p = _product(db, w['ca'])
    c = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('100000'), debt_balances={'UZS': 100000.0})
    create_sale(db, _debt_sale_data(p, w['wa'], c, 50000), w['admin'])
    r = client.login(w['cashier']).post(f'/api/customers/{c.id}/pay-debt',
                                        json={'amount': 30000, 'reason': "to'lov"})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.debt_balances['UZS'] == 120000.0 and c.debt_balance == Decimal('120000')


def test_customer_row_locked_in_sale_pay_and_put(client, db, world, monkeypatch):
    """create_sale, pay_debt, PUT, adjust-debt mijoz qatorini FOR UPDATE bilan o'qiydi."""
    from app.services.sale_create import create_sale
    w = world
    calls = []
    orig = Query.with_for_update

    def spy(self, *a, **kw):
        try:
            ent = self.column_descriptions[0]['entity']
        except Exception:
            ent = None
        calls.append(ent)
        return orig(self, *a, **kw)

    monkeypatch.setattr(Query, 'with_for_update', spy)
    p = _product(db, w['ca'])
    c = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('1000'), debt_balances={'UZS': 1000.0})

    def locked():
        n = sum(1 for e in calls if e is Customer)
        calls.clear()
        return n

    create_sale(db, _debt_sale_data(p, w['wa'], c, 100), w['admin'])
    assert locked() >= 1
    client.login(w['cashier']).post(f'/api/customers/{c.id}/pay-debt', json={'amount': 10, 'reason': 'x'})
    assert locked() >= 1
    client.login(w['admin']).put(f'/api/customers/{c.id}', json={'name': 'Z'})
    assert locked() >= 1
    client.login(w['admin']).post(f'/api/customers/{c.id}/adjust-debt',
                                  json={'reason': 'abc', 'changes': [{'currency': 'UZS', 'delta': '1'}]})
    assert locked() >= 1


def test_distributor_limit_enforced_on_locked_value(db, world):
    from fastapi import HTTPException
    from app.services.sale_create import create_sale
    w = world
    p = _product(db, w['ca'])
    c = _cust(db, w['ca'], w['ba'], customer_type='distributor', debt_limit=Decimal('1000000'))
    create_sale(db, _debt_sale_data(p, w['wa'], c, 600000), w['admin'])
    with pytest.raises(HTTPException) as e:
        create_sale(db, _debt_sale_data(p, w['wa'], c, 600000), w['admin'])
    assert e.value.status_code == 400 and 'limit' in e.value.detail
    db.refresh(c)
    assert c.debt_balance == Decimal('600000')


# ── 8. Validatorlar ──────────────────────────────────────────────────────────

def test_validators_and_retail_normalization(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'])
    cl = client.login(w['admin'])
    assert cl.put(f'/api/customers/{c.id}', json={'name': 'A', 'cashback_percent': 150}).status_code == 422
    assert cl.put(f'/api/customers/{c.id}', json={'name': 'A', 'cashback_percent': -1}).status_code == 422
    assert cl.put(f'/api/customers/{c.id}', json={'name': 'A', 'price_type': 'xyz'}).status_code == 422
    assert cl.put(f'/api/customers/{c.id}', json={'name': 'A', 'debt_limit': -5}).status_code == 422
    assert cl.put(f'/api/customers/{c.id}', json={'name': 'A', 'loyalty_points': -1}).status_code == 422
    r = cl.put(f'/api/customers/{c.id}', json={'name': 'A', 'price_type': 'retail'})
    assert r.status_code == 200 and r.json()['price_type'] == 'sale'
    r = cl.post('/api/customers', json={'name': 'Yangi', 'price_type': 'retail', 'cashback_percent': 4})
    assert r.status_code == 201 and r.json()['price_type'] == 'sale' and float(r.json()['cashback_percent']) == 4.0


def test_create_customer_financial_fields_by_role(client, db, world):
    w = world
    body = {'name': 'Kassir yaratdi', 'debt_balances': {'UZS': 5000}, 'debt_limit': 777, 'loyalty_points': 50,
            'cashback_percent': 9, 'price_type': 'cost'}
    r = client.login(w['cashier']).post('/api/customers', json=body)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j['debt_balances'] == {} and float(j['debt_limit']) == 0 and j['loyalty_points'] == 0
    assert float(j['cashback_percent']) == 0 and j['price_type'] == 'sale'
    body['name'] = 'Admin yaratdi'
    r = client.login(w['admin']).post('/api/customers', json=body)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j['debt_balances'] == {'UZS': 5000.0} and float(j['debt_balance']) == 5000.0
    assert float(j['debt_limit']) == 777 and j['loyalty_points'] == 50 and j['price_type'] == 'cost'
    created = db.query(Customer).filter(Customer.id == j['id']).one()
    assert created.debt_edited[-1]['edited_by']['id'] == w['admin'].id
    # manager: shartlar ha, qarz/ball yo'q
    body['name'] = 'Manager yaratdi'
    j = client.login(w['manager']).post('/api/customers', json=body).json()
    assert j['debt_balances'] == {} and j['loyalty_points'] == 0
    assert float(j['debt_limit']) == 777 and j['price_type'] == 'cost'


# ── 9. O'chirish / arxivlash ─────────────────────────────────────────────────

def test_delete_with_debt_400(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('12000000'), debt_balances={'UZS': 12000000.0})
    r = client.login(w['admin']).delete(f'/api/customers/{c.id}')
    assert r.status_code == 400 and 'qarz' in r.json()['detail']
    assert db.query(Customer).filter(Customer.id == c.id, Customer.is_active.is_(True)).count() == 1


def test_delete_with_active_order_400_not_500(client, db, world):
    w = world
    p = _product(db, w['ca'])
    c = _cust(db, w['ca'], w['ba'])
    _order(db, w['ca'], w['ba'], c, p, OrderStatus.on_way)
    r = client.login(w['admin']).delete(f'/api/customers/{c.id}')
    assert r.status_code == 400
    assert db.query(Customer).filter(Customer.id == c.id).count() == 1


def test_delete_with_delivered_order_archives_not_500(client, db, world):
    w = world
    p = _product(db, w['ca'])
    c = _cust(db, w['ca'], w['ba'])
    o = _order(db, w['ca'], w['ba'], c, p, OrderStatus.delivered)
    r = client.login(w['admin']).delete(f'/api/customers/{c.id}')
    assert r.status_code == 204
    db.refresh(c)
    db.refresh(o)
    assert c.is_active is False and o.customer_id == c.id


def test_delete_with_pending_sale_400(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'])
    _sale(db, w['ca'], w['admin'], c, status=SaleStatus.pending)
    assert client.login(w['admin']).delete(f'/api/customers/{c.id}').status_code == 400


def test_delete_with_sales_history_archives(client, db, world):
    w = world
    p = _product(db, w['ca'])
    phone = '998907770000'
    c = _cust(db, w['ca'], w['ba'], phone=phone, card_number='CARD-26', tg_chat_id='555')
    s = _sale(db, w['ca'], w['admin'], c)
    db.add(CustomerPrice(company_id=w['ca'].id, customer_id=c.id, product_id=p.id, price=Decimal('5')))
    db.flush()
    cl = client.login(w['director'] if 'director' in w else w['admin'])
    assert cl.delete(f'/api/customers/{c.id}').status_code == 204
    db.refresh(c)
    db.refresh(s)
    assert c.is_active is False and c.deleted_at is not None
    assert c.phone is None and c.card_number is None and c.tg_chat_id is None
    assert c.deleted_meta['phone'] == phone and c.deleted_meta['card_number'] == 'CARD-26'
    assert c.deleted_meta['tg_chat_id'] == '555'
    assert s.customer_id == c.id                       # sotuvda mijoz saqlanadi
    assert len(_actions(db, 'DELETE_CUSTOMER')) == 1
    # ro'yxatlarda ko'rinmaydi
    ids = [x['id'] for x in cl.get('/api/customers').json()]
    assert c.id not in ids
    pag = cl.get('/api/customers/paginated').json()
    assert c.id not in [x['id'] for x in pag['items']]
    assert cl.get('/api/customers/summary-stats').json()['total_customers'] == 0
    # shu telefon bilan yangi mijoz yaratish mumkin
    r = cl.post('/api/customers', json={'name': 'Qayta', 'phone': phone, 'card_number': 'CARD-26'})
    assert r.status_code == 201, r.text
    # arxivdagi mijozni qayta o'chirib/tahrirlab bo'lmaydi
    assert cl.delete(f'/api/customers/{c.id}').status_code == 404
    assert cl.put(f'/api/customers/{c.id}', json={'name': 'Q'}).status_code == 400


def test_delete_without_history_physically_removes_with_files(client, db, world, tmp_path, monkeypatch):
    from app.routers import customer_profile as cp
    monkeypatch.setattr(cp, 'DOC_DIR', str(tmp_path))
    w = world
    p = _product(db, w['ca'])
    c = _cust(db, w['ca'], w['ba'])
    db.add(CustomerPrice(company_id=w['ca'].id, customer_id=c.id, product_id=p.id, price=Decimal('5')))
    fpath = tmp_path / 'doc1.pdf'
    fpath.write_bytes(b'%PDF-1.4')
    db.add(CustomerDocument(customer_id=c.id, company_id=w['ca'].id, file_path='doc1.pdf',
                            original_name='shartnoma.pdf', content_type='application/pdf', size=8))
    db.flush()
    cid = c.id
    r = client.login(w['admin']).delete(f'/api/customers/{cid}')
    assert r.status_code == 204, r.text
    db.expire_all()
    assert db.query(Customer).filter(Customer.id == cid).count() == 0
    assert db.query(CustomerPrice).filter(CustomerPrice.customer_id == cid).count() == 0
    assert db.query(CustomerDocument).filter(CustomerDocument.customer_id == cid).count() == 0
    assert not os.path.exists(fpath)
    assert _actions(db, 'DELETE_CUSTOMER')[0].new_values == {'mode': 'deleted'}


def test_delete_foreign_company_404_and_cashier_403(client, db, world):
    w = world
    theirs = _cust(db, w['cb'], w['bb'])
    assert client.login(w['admin']).delete(f'/api/customers/{theirs.id}').status_code == 404
    mine = _cust(db, w['ca'], w['ba'])
    assert client.login(w['cashier']).delete(f'/api/customers/{mine.id}').status_code == 403
    assert client.login(w['admin']).delete(f'/api/customers/{mine.id}').status_code == 204


def test_put_foreign_company_customer_404(client, db, world):
    w = world
    theirs = _cust(db, w['cb'], w['bb'])
    assert client.login(w['admin']).put(f'/api/customers/{theirs.id}', json={'name': 'Hack'}).status_code == 404
    db.refresh(theirs)
    assert theirs.name != 'Hack'


# ── 10. bulk-import ──────────────────────────────────────────────────────────

def _rows():
    return [{'Ism': 'Import Mijoz', 'Telefon': '998905550001', 'Qarz': 99000, 'Kredit limit': 5000,
             'Sodiqlik ballari': 40, 'Cashback': 7, 'Bonus': 100}]


def test_bulk_import_cashier_financial_columns_ignored_with_warning(client, db, world):
    w = world
    r = client.login(w['cashier']).post('/api/customers/bulk-import', json=_rows())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['created'] == 1 and j['warnings'] and 'Qarz' in j['warnings'][0]['warning']
    c = db.query(Customer).filter(Customer.phone == '998905550001').one()
    assert c.debt_balances == {} and c.debt_balance == 0 and c.debt_limit in (None, 0) and not c.loyalty_points
    assert not c.cashback_percent and not c.bonus_balance


def test_bulk_import_cashier_cannot_overwrite_existing_debt(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], phone='998905550001', debt_balance=Decimal('1000'), debt_balances={'UZS': 1000.0})
    r = client.login(w['cashier']).post('/api/customers/bulk-import', params={'allow_update': True}, json=_rows())
    assert r.status_code == 200 and r.json()['updated'] == 1 and r.json()['warnings']
    db.refresh(c)
    assert c.debt_balances == {'UZS': 1000.0} and not c.debt_edited


def test_bulk_import_admin_writes_financial_and_logs(client, db, world):
    w = world
    c = _cust(db, w['ca'], w['ba'], phone='998905550001', debt_balance=Decimal('1000'), debt_balances={'UZS': 1000.0})
    r = client.login(w['admin']).post('/api/customers/bulk-import', params={'allow_update': True}, json=_rows())
    assert r.status_code == 200 and r.json()['updated'] == 1 and not r.json()['warnings']
    db.refresh(c)
    assert c.debt_balances == {'UZS': 99000.0} and c.debt_limit == Decimal('5000') and c.cashback_percent == Decimal('7')
    assert c.debt_edited[-1]['reason'] == 'bulk-import' and c.debt_edited[-1]['edited_by']['id'] == w['admin'].id
    assert _actions(db, 'CUSTOMER_TERMS')
    # yangi mijoz ham qarz bilan yaratiladi va jurnalga tushadi
    rows = [{'Ism': 'Yangi Import', 'Telefon': '998905550002', 'Qarz': 500, 'Cashback': 150}]
    r = client.login(w['admin']).post('/api/customers/bulk-import', json=rows)
    assert r.json()['created'] == 1 and r.json()['warnings']      # cashback=150 chegaradan tashqari
    n = db.query(Customer).filter(Customer.phone == '998905550002').one()
    assert n.debt_balances == {'UZS': 500.0} and not n.cashback_percent
    assert n.debt_edited[-1]['reason'] == 'bulk-import'


# ── 11. Arxivlangan mijozga sotuv ────────────────────────────────────────────

def test_sale_to_archived_customer_400(client, db, world):
    from fastapi import HTTPException
    from app.services.sale_create import create_sale
    w = world
    p = _product(db, w['ca'])
    c = _cust(db, w['ca'], w['ba'], is_active=False)
    with pytest.raises(HTTPException) as e:
        create_sale(db, _debt_sale_data(p, w['wa'], c, 1000), w['admin'])
    assert e.value.status_code == 400 and 'arxiv' in e.value.detail
    # HTTP orqali ham 400
    r = client.login(w['admin']).post('/api/sales', json={
        "items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], "payment_type": "debt",
        "paid_amount": 0, "warehouse_id": w['wa'].id, "customer_id": c.id})
    assert r.status_code == 400


def test_sale_delete_of_archived_customer_still_restores(db, world):
    from app.services.sale_create import create_sale
    from app.services.sale_delete import delete_sale
    w = world
    p = _product(db, w['ca'])
    c = _cust(db, w['ca'], w['ba'])
    sale = create_sale(db, _debt_sale_data(p, w['wa'], c, 1000), w['admin'])
    db.refresh(c)
    assert c.debt_balance == Decimal('1000')
    c.is_active = False
    db.flush()
    delete_sale(db, sale.id, w['admin'])
    db.refresh(c)
    assert c.debt_balance == Decimal('0')


# ── Migratsiya va model ──────────────────────────────────────────────────────

def test_migration_file_and_model_columns():
    import importlib.util
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    spec = importlib.util.spec_from_file_location(
        't026', os.path.join(root, 'alembic', 'versions', 't026_customer_archive_and_checks.py'))
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.revision == 't0_26' and mig.down_revision == 't0_23'
    src = open(spec.origin, encoding='utf-8').read()
    for needle in ('is_active', 'deleted_at', 'deleted_meta', 'ix_customers_company_active',
                   'ck_customers_price_type', 'ck_customers_cashback_0_100', 'ck_customers_loyalty_nonneg',
                   "NOT IN ('sale', 'wholesale', 'cost')"):
        assert needle in src
    cols = Customer.__table__.c
    assert cols.is_active.nullable is False and cols.deleted_at.nullable and cols.deleted_meta.nullable
    names = {c.name for c in Customer.__table__.constraints if c.name}
    assert {'ck_customers_price_type', 'ck_customers_cashback_0_100', 'ck_customers_loyalty_nonneg'} <= names


def test_db_check_constraints_reject_bad_values(db, world):
    from sqlalchemy.exc import IntegrityError
    w = world
    for bad in (dict(price_type='xyz'), dict(cashback_percent=Decimal('150')), dict(loyalty_points=-1)):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                _cust(db, w['ca'], w['ba'], **bad)


def test_other_active_filters_orders_shop_notification(db, world):
    """Arxivlangan mijoz uchun buyurtma yaratilmaydi; qarz eslatmasi ro'yxatiga tushmaydi."""
    import asyncio
    from app.services.notification_service import notification_service
    w = world
    arch = _cust(db, w['ca'], w['ba'], is_active=False, debt_balance=Decimal('50000'), debt_balances={'UZS': 50000.0})
    act = _cust(db, w['ca'], w['ba'], debt_balance=Decimal('50000'), debt_balances={'UZS': 50000.0})
    seen = []

    async def fake(customer, db, company_id):
        seen.append(customer.id)
        return {"success": True}

    notification_service.send_debt_reminder = fake
    try:
        asyncio.run(notification_service.send_bulk_debt_reminders(w['ca'].id, db))
    finally:
        del notification_service.send_debt_reminder
    assert seen == [act.id] and arch.id not in seen
