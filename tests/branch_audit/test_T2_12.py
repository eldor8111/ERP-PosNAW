"""T2.12 — Sodiqlik/keshbek va kredit limit qoidalari.

Qamrov: keshbek/ball yig'ish va sarflash (ball qiymati, sarflash chegarasi, filial o'chirilgan),
qarzli sotuvni 3 marta tahrirlash (balans ikki baravar o'smaydi, ishlatilgan ball yo'qolmaydi),
o'chirish sotuv snapshot'i bo'yicha, POS "Vazvrat" (asl sotuvli va asl sotuvsiz), qisman qaytarishlar
yig'indisi = to'liq qaytarish, pending sotuvni yakunlash (PUT va status-only), kredit limit (create_sale,
to'liq tahrir, status-only, scope='all', debt_limit=0, qulf), karta bo'yicha server qidiruvi va
`29…` karta formati, cashback_percent 0..100 (422), sozlamalar API (rol, validatsiya, ikki korxona izolyatsiyasi),
companies.credit_limit_scope, migratsiya fayli.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T2_12.py -q -p no:cacheprovider
"""
import itertools
import json
import os
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.company import Company
from app.models.customer import Customer
from app.models.loyalty import LoyaltyBranchRule, LoyaltySettings
from app.models.moliya import Wallet
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.user import UserRole, UserWallet
from app.schemas.sale import SaleCreate, SaleReturnRequest, SaleUpdate
from app.services.credit_service import check_credit_limit
from app.services.loyalty_service import (
    DEFAULT_TIERS, apply_sale_loyalty, get_loyalty_rules, reverse_sale_loyalty, tier_for,
)
from app.services.sale_create import create_pending_sale, create_sale
from app.services.sale_delete import delete_sale
from app.services.sale_partial_return import process_partial_return
from app.services.sale_return import create_return_sale
from app.services.sale_update import update_sale
from app.utils.loyalty_card import generate_card_number, normalize_card

_seq = itertools.count(1)
D = Decimal


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _cust(db, company, branch=None, **kw):
    n = next(_seq)
    c = Customer(name=kw.pop('name', f'Mijoz {n}'), company_id=company.id,
                 branch_id=branch.id if branch else None,
                 phone=kw.pop('phone', f'99891{n:07d}'), **kw)
    db.add(c)
    db.flush()
    return c


def _product(db, company, price='1000'):
    n = next(_seq)
    p = Product(name=f'Tovar {n}', sku=f'T212-{n}', barcode=f'B212-{n}', company_id=company.id,
                sale_price=D(price), cost_price=D('500'))
    db.add(p)
    db.flush()
    return p


def _wallet(db, company, branch, user):
    w = Wallet(name=f'Kassa {next(_seq)}', type='cash', balance=D('0'), company_id=company.id,
               branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(UserWallet(user_id=user.id, wallet_id=w.id, is_default=True, company_id=company.id))
    db.flush()
    return w


def _data(p, wh, customer=None, qty=1, price=100000, paid=0, ptype='debt', **extra):
    body = dict(items=[{"product_id": p.id, "quantity": qty, "unit_price": price}], payment_type=ptype,
                paid_amount=D(paid), warehouse_id=wh.id, customer_id=customer.id if customer else None)
    body.update(extra)
    return SaleCreate(**body)


def _state(c):
    return (D(str(c.bonus_balance or 0)), int(c.loyalty_points or 0), D(str(c.total_spent or 0)))


@pytest.fixture
def w(db, mk):
    """Korxona A: admin + 2 filial; korxona B: admin."""
    ca, ba, wa, admin = mk.tenant(UserRole.admin)
    ba2 = mk.branch(ca, name='Filial A2')
    wa2 = mk.warehouse(ca, ba2, name='Ombor A2')
    cashier = mk.user(ca, role=UserRole.cashier, branch=ba)
    manager = mk.user(ca, role=UserRole.manager, branch=ba)
    cb, bb, wb, admin_b = mk.tenant(UserRole.admin)
    p = _product(db, ca)
    return dict(ca=ca, ba=ba, wa=wa, ba2=ba2, wa2=wa2, admin=admin, cashier=cashier, manager=manager,
                cb=cb, bb=bb, wb=wb, admin_b=admin_b, p=p)


def _set(db, company, **kw):
    st = LoyaltySettings(company_id=company.id, **kw)
    db.add(st)
    db.flush()
    return st


# ── 11. Sozlama yo'q: bugungi qiymatlar ──────────────────────────────────────

def test_default_rules_equal_todays_values(db, w):
    r = get_loyalty_rules(db, w['ca'].id, warehouse_id=w['wa'].id)
    assert r.enabled and r.points_percent == 1 and r.point_value == 1
    assert r.tiers == DEFAULT_TIERS == (1000, 5000, 10000)
    assert r.max_redeem_percent == 100 and r.accrue_on_unpaid is True and r.return_reverses_loyalty is True
    assert [tier_for(x, r) for x in (0, 999, 1000, 5000, 10000)] == ['Standard', 'Standard', 'Bronze', 'Silver', 'Gold']
    c = _cust(db, w['ca'])
    c.loyalty_points = 5000
    assert c.tier == 'Silver'                   # Customer.tier sukut chegaralarni saqlaydi


def test_earn_default(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    s = create_sale(db, _data(w['p'], w['wa'], c, price=100000), w['admin'])
    db.refresh(c)
    assert _state(c) == (D('5000'), 1000, D('100000'))
    assert s.cashback_earned == D('5000') and s.loyalty_points_earned == 1000 and s.loyalty_base == D('100000')


# ── 1. Keshbek/ball sarflash ─────────────────────────────────────────────────

def test_redeem_cashback(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'), bonus_balance=D('350000'))
    s = create_sale(db, _data(w['p'], w['wa'], c, price=300000, paid_cashback=D('200000')), w['admin'])
    db.refresh(c)
    # 350 000 - 200 000 + 5% * (300 000 - 200 000)
    assert c.bonus_balance == D('155000')
    assert s.paid_cashback == D('200000') and s.total_amount == D('100000')
    assert s.cashback_earned == D('5000')
    with pytest.raises(HTTPException) as e:
        create_sale(db, _data(w['p'], w['wa'], c, price=500000, paid_cashback=D('999999')), w['admin'])
    assert e.value.status_code == 400 and "Bonus hisobida yetarli" in e.value.detail


def test_redeem_requires_customer(db, w):
    with pytest.raises(HTTPException) as e:
        create_sale(db, _data(w['p'], w['wa'], None, price=1000, paid_cashback=D('100')), w['admin'])
    assert e.value.status_code == 400 and 'mijozni tanlash majburiy' in e.value.detail


def test_redeem_points_with_point_value(db, w):
    _set(db, w['ca'], point_value=D('10'), points_percent=D('2'))
    c = _cust(db, w['ca'], loyalty_points=500)
    s = create_sale(db, _data(w['p'], w['wa'], c, price=50000, loyalty_points_used=100), w['admin'])
    db.refresh(c)
    # 100 ball = 1000 so'm; jami 49 000; 2% = 980 ball
    assert s.total_amount == D('49000') and s.loyalty_points_used == 100
    assert c.loyalty_points == 500 - 100 + 980
    assert s.loyalty_points_earned == 980
    with pytest.raises(HTTPException):
        create_sale(db, _data(w['p'], w['wa'], c, price=50000, loyalty_points_used=99999), w['admin'])


def test_max_redeem_percent(db, w):
    _set(db, w['ca'], max_redeem_percent=D('50'))
    c = _cust(db, w['ca'], bonus_balance=D('100000'))
    with pytest.raises(HTTPException) as e:
        create_sale(db, _data(w['p'], w['wa'], c, price=100000, paid_cashback=D('60000')), w['admin'])
    assert e.value.status_code == 400 and '50%' in e.value.detail
    s = create_sale(db, _data(w['p'], w['wa'], c, price=100000, paid_cashback=D('50000')), w['admin'])
    assert s.paid_cashback == D('50000')


def test_branch_disabled_no_earn_no_redeem(db, w):
    db.add(LoyaltyBranchRule(company_id=w['ca'].id, branch_id=w['ba'].id, is_enabled=False))
    db.flush()
    c = _cust(db, w['ca'], cashback_percent=D('5'), bonus_balance=D('1000'), loyalty_points=100)
    s = create_sale(db, _data(w['p'], w['wa'], c, price=100000), w['admin'])
    db.refresh(c)
    assert s.cashback_earned == 0 and s.loyalty_points_earned == 0
    assert c.bonus_balance == D('1000') and c.loyalty_points == 100 and c.total_spent == D('100000')
    with pytest.raises(HTTPException) as e:
        create_sale(db, _data(w['p'], w['wa'], c, price=100000, paid_cashback=D('500')), w['admin'])
    assert e.value.status_code == 400 and "o'chirilgan" in e.value.detail
    # boshqa filialda ishlaydi
    s2 = create_sale(db, _data(w['p'], w['wa2'], c, price=100000), w['admin'])
    assert s2.cashback_earned == D('5000')


def test_branch_cashback_override(db, w):
    db.add(LoyaltyBranchRule(company_id=w['ca'].id, branch_id=w['ba2'].id, is_enabled=True,
                             cashback_percent_override=D('2')))
    db.flush()
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    s = create_sale(db, _data(w['p'], w['wa2'], c, price=100000), w['admin'])
    assert s.cashback_earned == D('2000')


def test_company_disabled(db, w):
    _set(db, w['ca'], is_enabled=False)
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    s = create_sale(db, _data(w['p'], w['wa'], c, price=100000), w['admin'])
    assert s.cashback_earned == 0 and s.loyalty_points_earned == 0


def test_accrue_on_unpaid_false(db, w):
    _set(db, w['ca'], accrue_on_unpaid=False)
    _wallet(db, w['ca'], w['ba'], w['admin'])
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    s = create_sale(db, _data(w['p'], w['wa'], c, price=100000, paid=40000, ptype='cash', paid_cash=D('40000')),
                    w['admin'])
    db.refresh(c)
    assert s.cashback_earned == D('2000') and s.loyalty_points_earned == 400
    assert c.total_spent == D('100000') and s.loyalty_base == D('100000')


def test_tier_from_settings_via_api(client, db, w):
    _set(db, w['ca'], tier_bronze=10, tier_silver=20, tier_gold=30)
    c = _cust(db, w['ca'], loyalty_points=25)
    r = client.login(w['admin']).get(f'/api/customers/{c.id}/cashback')
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['tier'] == 'Silver' and j['loyalty_enabled'] is True and j['point_value'] == 1
    assert c.tier == 'Standard'                  # property sukut chegaralarni saqlaydi (25 < 1000)
    c2 = _cust(db, w['ca'], loyalty_points=3000)
    assert c2.tier == 'Bronze'
    r = client.login(w['admin']).get(f'/api/customers/{c2.id}/cashback')
    assert r.json()['tier'] == 'Gold'


# ── 4. Qarzli sotuvni 3 marta tahrirlash ─────────────────────────────────────

def _edit(db, w, sale, c, price=100000, **kw):
    body = dict(items=[{"product_id": w['p'].id, "quantity": 1, "unit_price": price}], payment_type='debt',
                paid_amount=D('0'), customer_id=c.id)
    body.update(kw)
    return update_sale(db, sale.id, SaleUpdate(**body), w['admin'])


def test_edit_debt_sale_three_times_idempotent(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'), loyalty_points=100, bonus_balance=D('10'))
    s = create_sale(db, _data(w['p'], w['wa'], c, price=100000), w['admin'])
    db.refresh(c)
    once = _state(c)
    assert once == (D('5010'), 1100, D('100000'))
    for _ in range(3):
        _edit(db, w, s, c)
        db.refresh(c)
        assert _state(c) == once
    db.refresh(s)
    assert s.cashback_earned == D('5000') and s.loyalty_points_earned == 1000
    # narx o'zgarsa — oxirgi tahrir qiymati
    _edit(db, w, s, c, price=200000)
    db.refresh(c)
    db.refresh(s)
    assert _state(c) == (D('10010'), 2100, D('200000')) and s.cashback_earned == D('10000')


def test_edit_keeps_redeemed_points(db, w):
    c = _cust(db, w['ca'], loyalty_points=500, bonus_balance=D('30000'))
    s = create_sale(db, _data(w['p'], w['wa'], c, price=100000, loyalty_points_used=200,
                              paid_cashback=D('10000')), w['admin'])
    db.refresh(c)
    first = _state(c)
    assert c.bonus_balance == D('20000') and c.loyalty_points == 500 - 200 + int(D('89800') * D('0.01'))
    for _ in range(2):
        _edit(db, w, s, c)
        db.refresh(c)
        db.refresh(s)
        assert _state(c) == first
        assert s.loyalty_points_used == 200 and s.paid_cashback == D('10000') and s.total_amount == D('89800')


def test_edit_fails_when_redeemed_no_longer_available(db, w):
    c = _cust(db, w['ca'], bonus_balance=D('50000'))
    s = create_sale(db, _data(w['p'], w['wa'], c, price=100000, paid_cashback=D('40000')), w['admin'])
    # yangi jami summa sarflangan keshbekdan kichik
    with pytest.raises(HTTPException) as e:
        _edit(db, w, s, c, price=30000)
    assert e.value.status_code == 400 and 'oshib' in e.value.detail


# ── 5. O'chirish sotuv snapshot'i bo'yicha ───────────────────────────────────

def test_delete_uses_sale_snapshot(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'), bonus_balance=D('7'))
    s = create_sale(db, _data(w['p'], w['wa'], c, price=100000), w['admin'])
    c.cashback_percent = D('50')                 # keyin o'zgardi
    db.flush()
    delete_sale(db, s.id, w['admin'])
    db.refresh(c)
    assert _state(c) == (D('7'), 0, D('0'))


def test_delete_restores_redeemed(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'), bonus_balance=D('20000'), loyalty_points=50)
    s = create_sale(db, _data(w['p'], w['wa'], c, price=100000, paid_cashback=D('10000'), loyalty_points_used=20),
                    w['admin'])
    delete_sale(db, s.id, w['admin'])
    db.refresh(c)
    assert _state(c) == (D('20000'), 50, D('0'))


def test_usd_sale_snapshot_no_double_multiplication(db, w):
    from app.models.currency import Currency
    usd = Currency(name='US Dollar', code='USD', rate=D('12000'), company_id=w['ca'].id)
    db.add(usd)
    db.flush()
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    data = SaleCreate(items=[{"product_id": w['p'].id, "quantity": 1, "unit_price": D('10'),
                              "currency_code": "USD", "exchange_rate": D('12000')}],
                      payment_type='debt', paid_amount=D('0'), warehouse_id=w['wa'].id, customer_id=c.id,
                      currency_id=usd.id)
    s = create_sale(db, data, w['admin'])
    db.refresh(c)
    assert s.total_amount == D('120000') and s.loyalty_base == D('120000')
    assert c.total_spent == D('120000') and c.bonus_balance == D('6000') and c.loyalty_points == 1200
    delete_sale(db, s.id, w['admin'])
    db.refresh(c)
    assert _state(c) == (D('0'), 0, D('0'))


# ── 6. POS "Vazvrat" va qisman qaytarish ─────────────────────────────────────

def _return_data(w, c, qty, price, original=None, **extra):
    return SaleCreate(items=[{"product_id": w['p'].id, "quantity": qty, "unit_price": price}],
                      payment_type='debt', paid_amount=D('0'), warehouse_id=w['wa'].id,
                      customer_id=c.id, original_sale_id=original.id if original else None, **extra)


def test_full_return_pos_vazvrat_with_original(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    s = create_sale(db, _data(w['p'], w['wa'], c, qty=1, price=10_000_000), w['admin'])
    db.refresh(c)
    assert c.bonus_balance == D('500000')
    create_return_sale(db, _return_data(w, c, 1, 10_000_000, original=s), w['admin'])
    db.refresh(c)
    assert _state(c) == (D('0'), 0, D('0'))


def test_return_without_original_reduces_by_amount(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    create_sale(db, _data(w['p'], w['wa'], c, qty=1, price=10_000_000), w['admin'])
    create_return_sale(db, _return_data(w, c, 1, 4_000_000), w['admin'])
    db.refresh(c)
    assert _state(c) == (D('300000'), 60000, D('6000000'))
    # hech qachon 0 dan pastga tushmaydi
    create_return_sale(db, _return_data(w, c, 1, 50_000_000), w['admin'])
    db.refresh(c)
    assert _state(c) == (D('0'), 0, D('0'))


def test_return_without_original_respects_setting(db, w):
    _set(db, w['ca'], return_reverses_loyalty=False)
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    create_sale(db, _data(w['p'], w['wa'], c, qty=1, price=1_000_000), w['admin'])
    create_return_sale(db, _return_data(w, c, 1, 1_000_000), w['admin'])
    db.refresh(c)
    assert _state(c) == (D('50000'), 10000, D('1000000'))


def test_partial_returns_sum_equals_full(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'), bonus_balance=D('1'), loyalty_points=3)
    s = create_sale(db, _data(w['p'], w['wa'], c, qty=7, price=14_285), w['admin'])
    db.refresh(c)
    assert c.total_spent == D('99995')
    item = s.items[0]
    for q in (2, 2, 3):
        process_partial_return(db, s.id, SaleReturnRequest(items=[{"sale_item_id": item.id, "quantity": q}],
                                                           payment_type='debt'), w['admin'])
        db.refresh(c)
    # barcha 7 ta qaytarildi -> boshlang'ich holat, hech narsa ikki marta ayirilmagan
    assert _state(c) == (D('1'), 3, D('0'))
    db.refresh(s)
    assert s.status == SaleStatus.refunded


def test_partial_return_is_proportional(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    s = create_sale(db, _data(w['p'], w['wa'], c, qty=4, price=25_000), w['admin'])
    item = s.items[0]
    process_partial_return(db, s.id, SaleReturnRequest(items=[{"sale_item_id": item.id, "quantity": 1}],
                                                       payment_type='debt'), w['admin'])
    db.refresh(c)
    assert _state(c) == (D('3750'), 750, D('75000'))


# ── 7. Pending sotuvni yakunlash ─────────────────────────────────────────────

def test_pending_complete_status_only_earns(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    s = create_pending_sale(db, _data(w['p'], w['wa'], c, price=100000), w['admin'])
    db.refresh(c)
    assert _state(c) == (D('0'), 0, D('0'))
    update_sale(db, s.id, SaleUpdate(status=SaleStatus.completed), w['admin'])
    db.refresh(c)
    db.refresh(s)
    assert _state(c) == (D('5000'), 1000, D('100000')) and s.cashback_earned == D('5000')
    # qaytadan pending -> completed ikki marta yig'masligi kerak
    update_sale(db, s.id, SaleUpdate(status=SaleStatus.pending), w['admin'])
    db.refresh(c)
    assert _state(c) == (D('0'), 0, D('0'))
    update_sale(db, s.id, SaleUpdate(status=SaleStatus.completed), w['admin'])
    db.refresh(c)
    assert _state(c) == (D('5000'), 1000, D('100000'))


def test_pending_complete_full_put_earns(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    s = create_pending_sale(db, _data(w['p'], w['wa'], c, price=100000), w['admin'])
    _edit(db, w, s, c, status=SaleStatus.completed)
    db.refresh(c)
    assert _state(c) == (D('5000'), 1000, D('100000'))


def test_pending_complete_with_paid_amount_path_earns(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'))
    s = create_pending_sale(db, _data(w['p'], w['wa'], c, price=100000), w['admin'])
    update_sale(db, s.id, SaleUpdate(status=SaleStatus.completed, paid_amount=D('0')), w['admin'])
    db.refresh(c)
    assert _state(c) == (D('5000'), 1000, D('100000'))


# ── 8. Kredit limit ──────────────────────────────────────────────────────────

def _distributor(db, w, limit=50_000_000, debt=48_000_000, **kw):
    return _cust(db, w['ca'], customer_type='distributor', debt_limit=D(limit), debt_balance=D(debt),
                 debt_balances={'UZS': float(debt)}, **kw)


def test_credit_limit_create_sale(db, w):
    c = _distributor(db, w)
    with pytest.raises(HTTPException) as e:
        create_sale(db, _data(w['p'], w['wa'], c, price=10_000_000), w['admin'])
    assert e.value.status_code == 400 and e.value.detail.startswith('Kredit limitidan oshadi: limit 50 000 000')
    assert "Qarzni yoping yoki limitni oshiring" in e.value.detail
    create_sale(db, _data(w['p'], w['wa'], c, price=2_000_000), w['admin'])     # limitgacha — o'tadi
    db.refresh(c)
    assert c.debt_balance == D('50000000')


def test_credit_limit_pending_complete_status_only(db, w):
    c = _distributor(db, w)
    s = create_pending_sale(db, _data(w['p'], w['wa'], c, price=10_000_000), w['admin'])
    with pytest.raises(HTTPException) as e:
        update_sale(db, s.id, SaleUpdate(status=SaleStatus.completed), w['admin'])
    assert e.value.status_code == 400 and 'Kredit limitidan oshadi' in e.value.detail
    db.refresh(c)
    assert c.debt_balance == D('48000000')


def test_credit_limit_pending_complete_with_paid_amount(db, w):
    c = _distributor(db, w)
    s = create_pending_sale(db, _data(w['p'], w['wa'], c, price=10_000_000), w['admin'])
    with pytest.raises(HTTPException) as e:
        update_sale(db, s.id, SaleUpdate(status=SaleStatus.completed, paid_amount=D('0')), w['admin'])
    assert e.value.status_code == 400 and 'Kredit limitidan oshadi' in e.value.detail


def test_credit_limit_pending_complete_full_edit_via_api(client, db, w):
    c = _distributor(db, w)
    s = create_pending_sale(db, _data(w['p'], w['wa'], c, price=10_000_000), w['admin'])
    r = client.login(w['admin']).put(f'/api/sales/{s.id}', json={
        "items": [{"product_id": w['p'].id, "quantity": 1, "unit_price": 10_000_000}],
        "status": "completed", "payment_type": "debt", "paid_amount": 0, "customer_id": c.id})
    assert r.status_code == 400 and 'Kredit limitidan oshadi' in r.json()['detail']
    # limit oshirilsa yakunlanadi
    c.debt_limit = D('100000000')
    db.flush()
    r = client.login(w['admin']).put(f'/api/sales/{s.id}', json={
        "items": [{"product_id": w['p'].id, "quantity": 1, "unit_price": 10_000_000}],
        "status": "completed", "payment_type": "debt", "paid_amount": 0, "customer_id": c.id})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.debt_balance == D('58000000')


def test_credit_limit_full_edit_of_completed_sale(db, w):
    c = _distributor(db, w, limit=50_000_000, debt=10_000_000)
    s = create_sale(db, _data(w['p'], w['wa'], c, price=5_000_000), w['admin'])
    _edit(db, w, s, c, price=30_000_000)          # 10 + 30 = 40 mln — o'tadi (eski 5 mln qaytariladi)
    db.refresh(c)
    assert c.debt_balance == D('40000000')
    with pytest.raises(HTTPException) as e:
        _edit(db, w, s, c, price=45_000_000)      # 10 + 45 = 55 mln > 50 mln
    assert e.value.status_code == 400 and 'Kredit limitidan oshadi' in e.value.detail


def test_credit_scope_all_blocks_retail(db, w):
    c = _cust(db, w['ca'], customer_type='retail', debt_limit=D('1000000'), debt_balance=D('900000'),
              debt_balances={'UZS': 900000.0})
    create_sale(db, _data(w['p'], w['wa'], c, price=2_000_000), w['admin'])       # sukut: faqat distribyutor
    c2 = _cust(db, w['ca'], customer_type='retail', debt_limit=D('1000000'), debt_balance=D('900000'),
               debt_balances={'UZS': 900000.0})
    w['ca'].credit_limit_scope = 'all'
    db.flush()
    with pytest.raises(HTTPException) as e:
        create_sale(db, _data(w['p'], w['wa'], c2, price=2_000_000), w['admin'])
    assert e.value.status_code == 400 and 'Kredit limitidan oshadi' in e.value.detail


def test_credit_limit_zero_means_unlimited(db, w):
    w['ca'].credit_limit_scope = 'all'
    c = _cust(db, w['ca'], customer_type='distributor', debt_limit=D('0'), debt_balance=D('999999999'),
              debt_balances={'UZS': 999999999.0})
    create_sale(db, _data(w['p'], w['wa'], c, price=10_000_000), w['admin'])
    check_credit_limit(db, c, D('1e12'))          # cheklov yo'q


def test_credit_limit_second_request_sees_first(db, w, monkeypatch):
    """Parallel so'rovlar: mijoz qatori qulflanadi, ikkinchisi birinchisining qarzini ko'radi."""
    import app.services.sale_create as sc
    locked = []
    orig = sc.lock_customer
    monkeypatch.setattr(sc, 'lock_customer', lambda *a, **k: (locked.append(a[1]), orig(*a, **k))[1])
    c = _distributor(db, w, limit=50_000_000, debt=40_000_000)
    create_sale(db, _data(w['p'], w['wa'], c, price=6_000_000), w['admin'])
    with pytest.raises(HTTPException):
        create_sale(db, _data(w['p'], w['wa'], c, price=6_000_000), w['admin'])
    assert locked == [c.id, c.id]


# ── 2/3. Karta bo'yicha qidiruv va format ────────────────────────────────────

def test_card_lookup_normalization(client, db, w):
    c = _cust(db, w['ca'], card_number='8888123456789012')
    old = _cust(db, w['ca'], card_number='7777 1234 5678 9012')
    other = _cust(db, w['cb'], card_number='9999123456789012')
    cl = client.login(w['admin'])
    for q in ('8888123456789012', '8888 1234 5678 9012', '8888-1234-5678-9012'):
        r = cl.get('/api/customers', params={'card': q})
        assert r.status_code == 200 and [x['id'] for x in r.json()] == [c.id], q
    assert [x['id'] for x in cl.get('/api/customers', params={'card': '7777123456789012'}).json()] == [old.id]
    assert cl.get('/api/customers', params={'card': '9999123456789012'}).json() == []     # boshqa korxona
    assert cl.get('/api/customers', params={'card': '000'}).json() == []
    assert cl.get('/api/customers', params={'card': 'abc'}).json() == []
    # ikkinchi korxona o'z kartasini topadi
    assert [x['id'] for x in client.login(w['admin_b']).get('/api/customers', params={'card': '9999123456789012'}).json()] == [other.id]


def test_card_lookup_beyond_first_500(client, db, w):
    for i in range(30):
        _cust(db, w['ca'], name=f'A{i:03d}')
    z = _cust(db, w['ca'], name='Zzz oxirgi', card_number='2912345678901')
    r = client.login(w['admin']).get('/api/customers', params={'card': '2912345678901', 'limit': 5})
    assert [x['id'] for x in r.json()] == [z.id]


def test_generate_card_number_format_and_unique():
    taken = set()
    for _ in range(300):
        num = generate_card_number(taken)
        assert len(num) == 13 and num.isdigit() and num.startswith('29') and num not in taken
        taken.add(num)
    # mavjud kartalar (bo'shliq bilan ham) takrorlanmaydi
    assert normalize_card('8888 1234 5678 9012') == '8888123456789012'
    assert normalize_card(None) == ''


def test_telegram_and_shop_generators_use_29(db, w):
    from app.routers import shop, telegram
    a = telegram._generate_card_number(db, w['ca'].id)
    b = shop._generate_card_number_for_shop(db, w['ca'].id)
    assert a.startswith('29') and b.startswith('29') and len(a) == len(b) == 13


# ── 9. cashback_percent 0..100 ───────────────────────────────────────────────

def test_cashback_percent_range_422(client, db, w):
    cl = client.login(w['admin'])
    for bad in (150, -1, 100.5):
        r = cl.post('/api/customers', json={'name': 'X', 'phone': '998901110000', 'cashback_percent': bad})
        assert r.status_code == 422, bad
    c = _cust(db, w['ca'])
    r = cl.put(f'/api/customers/{c.id}', json={'name': c.name, 'cashback_percent': 101})
    assert r.status_code == 422
    r = cl.post('/api/customers', json={'name': 'OK', 'phone': '998901110001', 'cashback_percent': 100})
    assert r.status_code == 201
    from app.routers.customers import CustomerIn
    with pytest.raises(Exception):
        CustomerIn(name='x', cashback_percent=101)


def test_default_cashback_percent_on_create(client, db, w):
    _set(db, w['ca'], default_cashback_percent=D('3'))
    cl = client.login(w['admin'])
    r = cl.post('/api/customers', json={'name': 'Defolt', 'phone': '998901110002'})
    assert r.status_code == 201 and float(r.json()['cashback_percent']) == 3.0
    r = cl.post('/api/customers', json={'name': 'Aniq', 'phone': '998901110003', 'cashback_percent': 0})
    assert float(r.json()['cashback_percent']) == 0.0


# ── Sozlamalar API ───────────────────────────────────────────────────────────

def test_settings_api_defaults_roles_and_validation(client, db, w):
    r = client.login(w['cashier']).get('/api/loyalty/settings')
    assert r.status_code == 200 and r.json()['exists'] is False and r.json()['tier_gold'] == 10000
    assert client.login(w['cashier']).put('/api/loyalty/settings', json={}).status_code == 403
    assert client.login(w['manager']).put('/api/loyalty/settings', json={}).status_code == 403
    adm = client.login(w['admin'])
    for bad in ({'points_percent': 101}, {'point_value': 0}, {'max_redeem_percent': -1},
                {'tier_bronze': 500, 'tier_silver': 400, 'tier_gold': 900},
                {'tier_bronze': 100, 'tier_silver': 100, 'tier_gold': 900}):
        assert adm.put('/api/loyalty/settings', json=bad).status_code == 422, bad
    r = adm.put('/api/loyalty/settings', json={'points_percent': 2, 'point_value': 10, 'tier_bronze': 10,
                                               'tier_silver': 20, 'tier_gold': 30, 'company_id': w['cb'].id})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['exists'] and j['points_percent'] == 2 and j['point_value'] == 10 and j['tier_gold'] == 30
    # body dagi company_id e'tiborsiz: faqat o'z korxonasi o'zgargan
    assert db.query(LoyaltySettings).filter(LoyaltySettings.company_id == w['cb'].id).count() == 0
    assert db.query(LoyaltySettings).filter(LoyaltySettings.company_id == w['ca'].id).count() == 1
    # ikkinchi PUT yangilaydi (ikkinchi qator yaratmaydi)
    adm.put('/api/loyalty/settings', json={'points_percent': 3})
    assert db.query(LoyaltySettings).filter(LoyaltySettings.company_id == w['ca'].id).count() == 1
    # B korxonasi o'z sukut qiymatlarini ko'radi
    rb = client.login(w['admin_b']).get('/api/loyalty/settings').json()
    assert rb['exists'] is False and rb['points_percent'] == 1


def test_new_settings_change_sale_calc(client, db, w):
    r = client.login(w['admin']).put('/api/loyalty/settings', json={
        'points_percent': 2, 'point_value': 10, 'tier_bronze': 100, 'tier_silver': 500, 'tier_gold': 900})
    assert r.status_code == 200
    c = _cust(db, w['ca'], loyalty_points=300)
    s = create_sale(db, _data(w['p'], w['wa'], c, price=50000, loyalty_points_used=100), w['admin'])
    db.refresh(c)
    assert s.total_amount == D('49000') and s.loyalty_points_earned == 980
    j = client.login(w['admin']).get(f'/api/customers/{c.id}/cashback').json()
    assert j['tier'] == 'Gold' and j['point_value'] == 10 and j['max_redeem_uzs'] == (0 + c.loyalty_points * 10)


def test_branch_rules_api_and_isolation(client, db, w):
    adm = client.login(w['admin'])
    r = adm.get('/api/loyalty/branch-rules')
    assert r.status_code == 200
    ids = {x['branch_id']: x for x in r.json()}
    assert set(ids) == {w['ba'].id, w['ba2'].id} and ids[w['ba'].id]['is_enabled'] is True
    r = adm.put(f"/api/loyalty/branch-rules/{w['ba2'].id}", json={'is_enabled': False, 'cashback_percent_override': 1.5})
    assert r.status_code == 200 and r.json()['is_enabled'] is False and r.json()['cashback_percent_override'] == 1.5
    assert adm.put(f"/api/loyalty/branch-rules/{w['ba2'].id}", json={'cashback_percent_override': 101}).status_code == 422
    # begona korxona filiali -> 404
    assert adm.put(f"/api/loyalty/branch-rules/{w['bb'].id}", json={'is_enabled': False}).status_code == 404
    assert db.query(LoyaltyBranchRule).filter(LoyaltyBranchRule.branch_id == w['bb'].id).count() == 0
    # kassir yoza olmaydi, o'qiy oladi
    assert client.login(w['cashier']).put(f"/api/loyalty/branch-rules/{w['ba'].id}", json={}).status_code == 403
    assert client.login(w['cashier']).get('/api/loyalty/branch-rules').status_code == 200
    # B korxonasi A filiallarini ko'rmaydi
    rb = client.login(w['admin_b']).get('/api/loyalty/branch-rules').json()
    assert {x['branch_id'] for x in rb} == {w['bb'].id}


def test_cashback_endpoint_isolation(client, db, w):
    c = _cust(db, w['ca'], bonus_balance=D('1000'))
    assert client.login(w['admin']).get(f'/api/customers/{c.id}/cashback').status_code == 200
    assert client.login(w['admin_b']).get(f'/api/customers/{c.id}/cashback').status_code == 404


# ── companies.credit_limit_scope ─────────────────────────────────────────────

def test_company_credit_limit_scope_api(client, db, w):
    adm = client.login(w['admin'])
    cid = w['ca'].id
    r = adm.put(f'/api/companies/{cid}', json={'credit_limit_scope': 'wrong'})
    assert r.status_code == 422
    r = adm.put(f'/api/companies/{cid}', json={'credit_limit_scope': 'all'})
    assert r.status_code == 200 and r.json()['credit_limit_scope'] == 'all'
    db.refresh(w['ca'])
    assert w['ca'].credit_limit_scope == 'all'
    # null yuborilsa e'tiborsiz (NOT NULL ustun)
    r = adm.put(f'/api/companies/{cid}', json={'credit_limit_scope': None, 'name': 'Yangi nom'})
    assert r.status_code == 200 and r.json()['credit_limit_scope'] == 'all'
    # begona korxonani o'zgartirib bo'lmaydi
    assert adm.put(f"/api/companies/{w['cb'].id}", json={'credit_limit_scope': 'all'}).status_code == 404
    # kassir o'zgartira olmaydi
    assert client.login(w['cashier']).put(f'/api/companies/{cid}', json={'credit_limit_scope': 'distributor'}).status_code == 403


# ── Migratsiya va model ──────────────────────────────────────────────────────

def test_migration_file_and_models():
    import importlib.util
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    path = os.path.join(root, 'alembic', 'versions', 't2_12_loyalty_settings_credit_scope.py')
    spec = importlib.util.spec_from_file_location('t2_12', path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.revision == 't2_12' and mig.down_revision == 't2_10'   # zanjirga ulangan
    src = open(path, encoding='utf-8').read()
    for needle in ('loyalty_settings', 'loyalty_branch_rules', 'uq_loyalty_branch_rule', 'ix_loyalty_branch_rules_company_id',
                   'loyalty_base', 'credit_limit_scope', 'ck_companies_credit_limit_scope', 'regexp_replace',
                   'cashback_percent', 'tier_bronze < tier_silver', 'DROP TABLE IF EXISTS loyalty_settings'):
        assert needle in src, needle
    assert Sale.__table__.c.loyalty_base.nullable is True
    assert Company.__table__.c.credit_limit_scope.nullable is False
    assert LoyaltySettings.__table__.c.company_id.unique is True


# ── i18n kalitlari (pending fayl) ────────────────────────────────────────────

KEYS_T2_12 = ["pos.payWithCashback", "pos.payWithPoints", "pos.cashbackAvailable", "pos.cashbackAndPoints", "pos.cardCustomerFound", "pos.cashbackNeedsInternet", "customer.creditLimitDistributorOnly", "settings.loyalty.title", "settings.loyalty.desc", "settings.loyalty.enabled", "settings.loyalty.enabledDesc", "settings.loyalty.pointsPercent", "settings.loyalty.pointValue", "settings.loyalty.maxRedeemPercent", "settings.loyalty.maxRedeemHint", "settings.loyalty.defaultCashback", "settings.loyalty.tierBronze", "settings.loyalty.tierSilver", "settings.loyalty.tierGold", "settings.loyalty.accrueOnUnpaid", "settings.loyalty.accrueOnUnpaidDesc", "settings.loyalty.returnReverses", "settings.loyalty.returnReversesDesc", "settings.loyalty.save", "settings.loyalty.saved", "settings.loyalty.creditScope", "settings.loyalty.creditScopeDesc", "settings.loyalty.creditScopeDistributor", "settings.loyalty.creditScopeAll", "settings.loyalty.branchRules", "settings.loyalty.branchEnabled", "settings.loyalty.branchCashback", "settings.loyalty.branchCashbackHint", "settings.loyalty.branchSaved"]


def _merged_i18n(keys):
    """T2.x i18n kalitlari uz/ru/en lug'atlariga birlashtirilgan (pending fayl o'chirilgan):
    {til: {kalit: qiymat}}; kalit lug'atda yo'q bo'lsa KeyError."""
    import re as _re
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'i18n'))
    out = {}
    for lang in ('uz', 'ru', 'en'):
        with open(os.path.join(base, lang + '.js'), encoding='utf-8') as f:
            txt = f.read()
        found = {m.group(1): m.group(2) for m in _re.finditer(r"^\s*'([^']+)':\s*(.+?),?\s*$", txt, _re.M)}
        out[lang] = {k: found[k] for k in keys}
    return out


def test_pending_i18n_keys_present_in_all_languages():
    data = _merged_i18n(KEYS_T2_12)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en']) and len(data['uz']) >= 20
    for key in ('pos.payWithCashback', 'pos.payWithPoints', 'pos.cashbackAvailable', 'pos.cardCustomerFound',
                'customer.creditLimitDistributorOnly', 'settings.loyalty.title'):
        assert key in data['uz'], key
    assert all(v for lang in data.values() for v in lang.values())


# ── POS yuboradigan payload shakllari (payment_type=cashback / mixed + payments) ──

def test_pos_payload_fully_paid_by_cashback_and_points(db, w):
    c = _cust(db, w['ca'], cashback_percent=D('5'), bonus_balance=D('350000'), loyalty_points=100)
    s = create_sale(db, _data(w['p'], w['wa'], c, price=200000, ptype='cashback', paid_cashback=D('200000')),
                    w['admin'])
    db.refresh(c)
    assert s.payment_type == PaymentType.cashback and s.status == SaleStatus.completed
    assert s.total_amount == 0 and s.paid_cashback == D('200000') and c.bonus_balance == D('150000')
    assert c.debt_balance in (None, 0)
    # ball + keshbek aralash, pul to'lovi payments ro'yxati bilan
    _wallet(db, w['ca'], w['ba'], w['admin'])
    s2 = create_sale(db, _data(w['p'], w['wa'], c, price=200000, ptype='mixed', paid=D('140000'),
                               paid_cashback=D('50000'), loyalty_points_used=100, paid_cash=D('140000'),
                               payments=[{"type": "cash", "amount": D('140000'), "currency": "UZS"}]), w['admin'])
    db.refresh(c)
    assert s2.total_amount == D('149900')            # 200 000 - 50 000 keshbek - 100 ball * 1 so'm
    assert s2.loyalty_points_used == 100 and c.loyalty_points == 0 + int(s2.total_amount * D('0.01'))
    assert c.bonus_balance == D('100000') + s2.cashback_earned
