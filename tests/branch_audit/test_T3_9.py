"""T3.9 — Tarif: filial/ombor limitlari, foydalanish endpointi, downgrade ogohlantirishi, tariff_guard yagonalashtirish."""
import importlib.util
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Query

from app.config import settings
from app.models.billing import Tariff
from app.models.branch import Branch
from app.models.company import Company
from app.models.courier import Courier
from app.models.user import User, UserRole, UserStatus
from app.models.user_company import UserCompany
from app.models.warehouse import Warehouse
from app.services import tariff_guard as tg

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FE = os.path.join(ROOT, 'frontend', 'src')


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def _tariff(db, company=None, ends='future', **kw):
    """Tarif yaratadi; `None` qiymatlar (NULL) xom SQL bilan yoziladi (ustun defaultlari almashtirmasligi uchun)."""
    nulls = [k for k, v in kw.items() if v is None]
    kw = {k: v for k, v in kw.items() if v is not None}
    kw.setdefault('name', "Test tarif")
    t = Tariff(**kw)
    db.add(t)
    db.flush()
    for k in nulls:
        db.execute(text(f"UPDATE tariffs SET {k} = NULL WHERE id = :i"), {"i": t.id})
    if nulls:
        db.expire(t)
    if company is not None:
        company.tariff_id = t.id
        company.subscription_ends_at = {
            'future': datetime.now(timezone.utc) + timedelta(days=10),
            'past': datetime.now(timezone.utc) - timedelta(days=10),
            'null': None,
        }[ends]
        db.flush()
        db.refresh(company)
    return t


def _active_branches(db, company):
    return db.query(Branch).filter(Branch.company_id == company.id, Branch.is_active == True).count()  # noqa: E712


# ───────────────────────── get_active_tariff / get_limits ─────────────────────────

def test_get_active_tariff_policy(db, mk):
    c = mk.company()
    assert tg.get_active_tariff(db, c.id) is None                       # tarif yo'q
    assert tg.get_active_tariff(db, None) is None
    t = _tariff(db, c, ends='past')
    assert tg.get_active_tariff(db, c.id) is None                       # muddati o'tgan
    c.subscription_ends_at = None
    db.flush()
    assert tg.get_active_tariff(db, c.id).id == t.id                    # NULL muddat + tarif -> tarif
    c.subscription_ends_at = datetime.now(timezone.utc) + timedelta(days=1)
    db.flush()
    assert tg.get_active_tariff(db, c.id).id == t.id                    # naive datetime ham ishlaydi
    c.subscription_ends_at = (datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None)
    db.flush()
    assert tg.get_active_tariff(db, c.id).id == t.id
    assert tg.get_company_tariff(db, c.id).id == t.id                   # eski nom bir xil siyosat


def test_get_limits_unlimited_rules(db):
    assert tg.get_limits(None) == {
        'max_branches': 1, 'max_warehouses': 1, 'max_users': 5, 'max_products': None,
        'max_agents': None, 'max_couriers': None, 'max_production_orders': None,
    }
    t = _tariff(db, max_branches=9999, max_warehouses=3, max_users=9999, max_products=700,
                max_agents=None, max_couriers=None, has_distribution=True)
    lim = tg.get_limits(t)
    assert lim['max_branches'] is None and lim['max_users'] is None
    assert lim['max_warehouses'] == 3 and lim['max_products'] == 700
    assert lim['max_agents'] is None and lim['max_couriers'] is None     # cheksiz
    t2 = _tariff(db, max_agents=5, max_couriers=2, has_distribution=False)
    lim2 = tg.get_limits(t2)
    assert lim2['max_agents'] == 0 and lim2['max_couriers'] == 0         # modul tarifda yo'q


# ───────────────────────── count_usage ─────────────────────────

def test_count_usage_active_only_and_user_company(db, mk):
    a, ba, wa, admin_a = mk.tenant()
    b, bb, wb, admin_b = mk.tenant()
    mk.branch(a, is_active=False)
    mk.warehouse(a, ba, is_active=False)
    mk.user(a, role=UserRole.cashier, branch=ba, status=UserStatus.inactive)       # sanalmaydi
    mk.user(a, role=UserRole.marketplace_agent)                                    # sanalmaydi
    sa = mk.user(None, role=UserRole.super_admin)
    db.add(UserCompany(user_id=sa.id, company_id=a.id, role=UserRole.admin, is_active=True))  # super_admin sanalmaydi
    # B korxona xodimi A ga faol UserCompany orqali qo'shilgan -> A xodimlariga kiradi
    shared = mk.user(b, role=UserRole.cashier, branch=bb)
    db.add(UserCompany(user_id=shared.id, company_id=a.id, role=UserRole.cashier, is_active=True))
    # nofaol a'zolik sanalmaydi
    other = mk.user(b, role=UserRole.cashier, branch=bb)
    db.add(UserCompany(user_id=other.id, company_id=a.id, role=UserRole.cashier, is_active=False))
    # xodimning ikkala yo'li (company_id + UserCompany) bitta bo'lib sanaladi (distinct)
    db.add(UserCompany(user_id=admin_a.id, company_id=a.id, role=UserRole.admin, is_active=True))
    db.flush()

    u = tg.count_usage(db, a.id)
    assert u['branches'] == 1
    assert u['warehouses'] == 1
    assert u['users'] == 2                       # admin_a + shared
    ub = tg.count_usage(db, b.id)
    assert ub['users'] == 3 and ub['branches'] == 1   # B: admin_b, shared, other (asosiy korxonasi B)


def test_count_usage_ignores_other_company_resources(db, mk):
    a, *_ = mk.tenant()
    b, bb, wb, _ = mk.tenant()
    mk.branch(b)
    mk.warehouse(b, bb)
    assert tg.count_usage(db, a.id)['branches'] == 1
    assert tg.count_usage(db, a.id)['warehouses'] == 1


# ───────────────────────── check_branch_limit / check_warehouse_limit ─────────────────────────

def test_check_branch_limit_boundaries(db, mk):
    c, b1, _, u = mk.tenant()
    _tariff(db, c, max_branches=2)
    tg.check_branch_limit(db, c.id, u)               # 1 < 2 -> ruxsat
    mk.branch(c)
    with pytest.raises(HTTPException) as e:
        tg.check_branch_limit(db, c.id, u)           # 2 >= 2
    assert e.value.status_code == 403 and e.value.code == 'TARIFF_LIMIT'
    assert "maksimal filiallar soni: 2" in e.value.detail and "Hozir: 2" in e.value.detail
    tg.check_branch_limit(db, c.id, u, exclude_branch_id=b1.id)      # qayta yoqiladigan filial sanalmaydi
    sa = mk.user(None, role=UserRole.super_admin)
    tg.check_branch_limit(db, c.id, sa)              # super_admin o'tkaziladi


def test_check_branch_limit_unlimited_and_no_lock(db, mk, monkeypatch):
    c, _, _, u = mk.tenant()
    _tariff(db, c, max_branches=9999)
    mk.branch(c)
    tg.check_branch_limit(db, c.id, u)               # cheksiz
    calls = []
    orig = Query.with_for_update
    monkeypatch.setattr(Query, 'with_for_update', lambda self, *a, **k: (calls.append(1), orig(self, *a, **k))[1])
    tg.check_branch_limit(db, c.id, u)
    assert calls                                     # lock=True (standart) FOR UPDATE ishlatadi
    calls.clear()
    tg.check_branch_limit(db, c.id, u, lock=False)
    assert not calls


def test_check_warehouse_limit_modes(db, mk, monkeypatch, caplog):
    c, b, w, u = mk.tenant()                         # 1 ta faol ombor
    _tariff(db, c, max_warehouses=1)
    sa = mk.user(None, role=UserRole.super_admin)

    monkeypatch.setattr(settings, 'TARIFF_WAREHOUSE_LIMIT_MODE', 'off')
    tg.check_warehouse_limit(db, c.id, u)

    monkeypatch.setattr(settings, 'TARIFF_WAREHOUSE_LIMIT_MODE', 'warn')
    with caplog.at_level(logging.WARNING):
        tg.check_warehouse_limit(db, c.id, u)        # xato yo'q, faqat log
    assert any('Ombor limiti oshdi' in r.getMessage() for r in caplog.records)

    monkeypatch.setattr(settings, 'TARIFF_WAREHOUSE_LIMIT_MODE', 'enforce')
    with pytest.raises(HTTPException) as e:
        tg.check_warehouse_limit(db, c.id, u)
    assert e.value.status_code == 403 and "maksimal omborlar soni: 1" in e.value.detail
    tg.check_warehouse_limit(db, c.id, u, exclude_warehouse_id=w.id)    # qayta yoqiladigan ombor sanalmaydi
    tg.check_warehouse_limit(db, c.id, sa)                              # super_admin o'tkaziladi
    # noto'g'ri rejim qiymati "warn" ga tushadi
    monkeypatch.setattr(settings, 'TARIFF_WAREHOUSE_LIMIT_MODE', 'xato')
    assert tg.warehouse_limit_mode() == 'warn'


def test_default_warehouse_mode_is_warn():
    from app.config import Settings
    assert Settings.model_fields['TARIFF_WAREHOUSE_LIMIT_MODE'].default == 'warn'


# ───────────────────────── POST/PATCH /branches ─────────────────────────

def test_post_branches_sequential_only_first_succeeds_and_locks(client, db, mk, monkeypatch):
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    _tariff(db, c, max_branches=1)
    calls = []
    orig = Query.with_for_update
    monkeypatch.setattr(Query, 'with_for_update', lambda self, *a, **k: (calls.append(1), orig(self, *a, **k))[1])
    r1 = client.login(u).post('/api/branches', json={'name': 'F1'})
    r2 = client.login(u).post('/api/branches', json={'name': 'F2'})
    assert (r1.status_code, r2.status_code) == (200, 403)
    assert calls                                      # korxona qatori FOR UPDATE bilan qulflandi
    assert _active_branches(db, c) == 1


def test_patch_branch_reactivate_respects_limit(client, db, mk):
    c, b1, _, u = mk.tenant()
    _tariff(db, c, max_branches=1)
    off = mk.branch(c, is_active=False)
    r = client.login(u).patch(f'/api/branches/{off.id}', json={'is_active': True})
    assert r.status_code == 403 and 'maksimal filiallar soni' in r.json()['detail']
    assert db.get(Branch, off.id).is_active is False
    # limit ichida ishlaydi (b1 ni o'chirgach)
    assert client.login(u).patch(f'/api/branches/{b1.id}', json={'is_active': False}).status_code == 200
    assert client.login(u).patch(f'/api/branches/{off.id}', json={'is_active': True}).status_code == 200
    # is_active=false doim ishlaydi
    assert client.login(u).patch(f'/api/branches/{off.id}', json={'is_active': False}).status_code == 200


def test_patch_branch_reactivate_expired_tariff_uses_default(client, db, mk):
    c, b1, _, u = mk.tenant()
    _tariff(db, c, ends='past', max_branches=5)
    off = mk.branch(c, is_active=False)
    assert client.login(u).patch(f'/api/branches/{off.id}', json={'is_active': True}).status_code == 403


def test_branch_limit_isolation_between_companies(client, db, mk):
    a, ba, _, ua = mk.tenant()
    b, bb, _, ub = mk.tenant()
    _tariff(db, a, max_branches=1)
    _tariff(db, b, max_branches=3)
    assert client.login(ua).post('/api/branches', json={'name': 'A2'}).status_code == 403
    assert client.login(ub).post('/api/branches', json={'name': 'B2'}).status_code == 200
    # A xodimi B filialini o'zgartira olmaydi
    assert client.login(ua).patch(f'/api/branches/{bb.id}', json={'is_active': False}).status_code == 404


# ───────────────────────── POST/PATCH /warehouses ─────────────────────────

def test_post_warehouse_modes(client, db, mk, monkeypatch, caplog):
    c, b, w, u = mk.tenant()
    _tariff(db, c, max_warehouses=1)

    monkeypatch.setattr(settings, 'TARIFF_WAREHOUSE_LIMIT_MODE', 'enforce')
    r = client.login(u).post('/api/warehouses', json={'name': 'Yangi', 'branch_id': b.id})
    assert r.status_code == 403 and 'maksimal omborlar soni' in r.json()['detail']

    monkeypatch.setattr(settings, 'TARIFF_WAREHOUSE_LIMIT_MODE', 'warn')
    with caplog.at_level(logging.WARNING):
        r = client.login(u).post('/api/warehouses', json={'name': 'Yangi', 'branch_id': b.id})
    assert r.status_code == 200
    assert any('Ombor limiti oshdi' in rec.getMessage() for rec in caplog.records)
    # usage endpointida over=true
    d = client.login(u).get('/api/billing/my-company/usage').json()
    assert d['usage']['warehouses'] == {'used': 2, 'limit': 1, 'over': True, 'full': True}
    assert d['over_limit'] is True


def test_patch_warehouse_reactivate_enforce(client, db, mk, monkeypatch):
    c, b, w, u = mk.tenant()
    _tariff(db, c, max_warehouses=1)
    off = mk.warehouse(c, b, is_active=False)
    monkeypatch.setattr(settings, 'TARIFF_WAREHOUSE_LIMIT_MODE', 'enforce')
    assert client.login(u).patch(f'/api/warehouses/{off.id}', json={'is_active': True}).status_code == 403
    assert db.get(Warehouse, off.id).is_active is False
    # nom o'zgartirish (is_active yuborilmagan) limitga tegmaydi
    assert client.login(u).patch(f'/api/warehouses/{w.id}', json={'name': 'Yangi nom'}).status_code == 200
    # warn rejimida qayta yoqiladi
    monkeypatch.setattr(settings, 'TARIFF_WAREHOUSE_LIMIT_MODE', 'warn')
    assert client.login(u).patch(f'/api/warehouses/{off.id}', json={'is_active': True}).status_code == 200


def test_warehouse_limit_isolation_and_super_admin(client, db, mk, monkeypatch):
    monkeypatch.setattr(settings, 'TARIFF_WAREHOUSE_LIMIT_MODE', 'enforce')
    a, ba, wa, ua = mk.tenant()
    b, bb, wb, ub = mk.tenant()
    _tariff(db, a, max_warehouses=1)
    _tariff(db, b, max_warehouses=2)
    assert client.login(ua).post('/api/warehouses', json={'name': 'A2', 'branch_id': ba.id}).status_code == 403
    assert client.login(ub).post('/api/warehouses', json={'name': 'B2', 'branch_id': bb.id}).status_code == 200   # o'z limiti
    assert client.login(ua).patch(f'/api/warehouses/{wb.id}', json={'is_active': True}).status_code == 404       # begona resurs
    sa = mk.user(None, role=UserRole.super_admin)
    assert client.login(sa).post('/api/warehouses', json={'name': 'SA', 'branch_id': ba.id}).status_code == 200   # super_admin o'tkaziladi


# ───────────────────────── GET /billing/my-company/usage ─────────────────────────

def test_usage_endpoint_shape_and_isolation(client, db, mk):
    a, ba, _, ua = mk.tenant()
    b, bb, _, ub = mk.tenant()
    mk.branch(b)
    mk.branch(b)
    _tariff(db, a, name='Boshlang', max_branches=2, max_warehouses=3, max_users=9999, max_products=None)
    r = client.login(ua).get('/api/billing/my-company/usage')
    assert r.status_code == 200
    d = r.json()
    assert d['tariff']['name'] == 'Boshlang' and d['subscription_active'] is True
    assert set(d['usage']) == {'branches', 'warehouses', 'users', 'products', 'agents', 'couriers'}
    assert d['usage']['branches'] == {'used': 1, 'limit': 2, 'over': False, 'full': False}
    assert d['usage']['warehouses']['limit'] == 3
    assert d['usage']['users']['limit'] is None                   # 9999 -> cheksiz
    assert d['usage']['products']['limit'] is None                # NULL -> cheksiz
    assert d['limits']['max_branches'] == 2
    # B korxonasi faqat o'z hisobini ko'radi (3 ta filial, tarifsiz -> limit 1)
    db_ = client.login(ub).get('/api/billing/my-company/usage').json()
    assert db_['tariff'] is None and db_['subscription_active'] is False
    assert db_['usage']['branches'] == {'used': 3, 'limit': 1, 'over': True, 'full': True}


def test_usage_endpoint_expired_and_no_company(client, db, mk):
    c, _, _, u = mk.tenant()
    _tariff(db, c, ends='past')
    d = client.login(u).get('/api/billing/my-company/usage').json()
    assert d['subscription_active'] is False and d['usage']['branches']['limit'] == 1
    sa = mk.user(None, role=UserRole.super_admin)
    assert client.login(sa).get('/api/billing/my-company/usage').status_code == 404


# ───────────────────────── companies: branches_count va modul bayroqlari ─────────────────────────

def test_branches_count_counts_only_active(client, db, mk):
    c, b, _, u = mk.tenant()
    mk.branch(c, is_active=False)
    mk.branch(c, is_active=False)
    r = client.login(u).get('/api/companies')
    assert r.status_code == 200
    row = [x for x in r.json() if x['id'] == c.id][0]
    assert row['branches_count'] == 1


def test_update_company_module_toggle_requires_tariff(client, db, mk):
    c, _, _, admin = mk.tenant()
    _tariff(db, c, has_distribution=False, has_manufacturing=True)
    cl = client.login(admin)
    r = cl.put(f'/api/companies/{c.id}', json={'distribution_enabled': True})
    assert r.status_code == 403 and 'tarif yoki paket' in r.json()['detail']
    assert db.get(Company, c.id).distribution_enabled is False
    # tarifda bor modul yoqiladi, o'chirish doim mumkin
    assert cl.put(f'/api/companies/{c.id}', json={'manufacturing_enabled': True}).status_code == 200
    assert cl.put(f'/api/companies/{c.id}', json={'manufacturing_enabled': False}).status_code == 200
    # allaqachon yoqilgan modul bayrog'ini qayta yuborish (forma qayta saqlanishi) 403 bermaydi
    c.distribution_enabled = True
    db.flush()
    assert cl.put(f'/api/companies/{c.id}', json={'distribution_enabled': True}).status_code == 200
    # super admin tarifdan qat'i nazar yoqa oladi
    c.distribution_enabled = False
    db.flush()
    sa = mk.user(None, role=UserRole.super_admin)
    assert client.login(sa).put(f'/api/companies/{c.id}', json={'distribution_enabled': True}).status_code == 200
    assert db.get(Company, c.id).distribution_enabled is True


def test_update_company_module_toggle_other_company_404(client, db, mk):
    a, _, _, ua = mk.tenant()
    b, _, _, _ = mk.tenant()
    _tariff(db, b, has_distribution=True)
    assert client.login(ua).put(f'/api/companies/{b.id}', json={'distribution_enabled': True}).status_code == 404


# ───────────────────────── xodim / agent / kuryer limitlari ─────────────────────────

def _user_body(phone, role='cashier', **kw):
    return {'name': 'Yangi', 'phone': phone, 'password': 'parol123', 'role': role, **kw}


def test_check_user_limit_counts_user_company_members(db, mk):
    a, ba, _, admin_a = mk.tenant()
    b, bb, _, _ = mk.tenant()
    _tariff(db, a, max_users=2)
    tg.check_user_limit(db, a.id, admin_a)              # 1 < 2
    shared = mk.user(b, role=UserRole.cashier, branch=bb)
    db.add(UserCompany(user_id=shared.id, company_id=a.id, role=UserRole.cashier, is_active=True))
    db.flush()
    with pytest.raises(HTTPException) as e:
        tg.check_user_limit(db, a.id, admin_a)          # 2 >= 2 (UserCompany orqali qo'shilgan ham hisobda)
    assert e.value.status_code == 403 and 'maksimal xodimlar soni: 2' in e.value.detail


def test_create_user_blocked_by_user_company_member(client, db, mk):
    a, ba, _, admin_a = mk.tenant()
    b, bb, _, _ = mk.tenant()
    _tariff(db, a, max_users=2)
    shared = mk.user(b, role=UserRole.cashier, branch=bb)
    db.add(UserCompany(user_id=shared.id, company_id=a.id, role=UserRole.cashier, is_active=True))
    db.flush()
    r = client.login(admin_a).post('/api/users/', json=_user_body('998900000001', branch_id=ba.id))
    assert r.status_code == 403 and 'maksimal xodimlar soni' in r.json()['detail']


def test_create_agent_and_courier_limits(client, db, mk):
    c, b, _, admin = mk.tenant()
    _tariff(db, c, max_users=50, has_distribution=True, max_agents=1, max_couriers=1)
    c.distribution_enabled = True   # modul kompaniyada yoqilgan (birlashtirilgan paket qoidasi)
    mk.user(c, role=UserRole.agent, branch=b)                      # agent kvotasi to'lgan
    db.add(Courier(company_id=c.id, name='K1', phone='901', is_active=True))   # kuryer kvotasi to'lgan
    db.flush()
    cl = client.login(admin)
    r = cl.post('/api/users/', json=_user_body('998900000011', role='agent', branch_id=b.id))
    assert r.status_code == 400 and 'agentlari limiti' in r.json()['detail']
    r = cl.post('/api/users/', json=_user_body('998900000012', role='courier', branch_id=b.id))
    assert r.status_code == 400 and 'kuryerlar' in r.json()['detail']
    # boshqa rol ta'sirlanmaydi
    assert cl.post('/api/users/', json=_user_body('998900000013', role='cashier', branch_id=b.id)).status_code == 201


def test_create_agent_courier_unlimited_when_null(client, db, mk):
    """Migratsiyadan keyin: has_distribution=true va max_agents/max_couriers NULL -> cheksiz, 403 yo'q."""
    c, b, _, admin = mk.tenant()
    _tariff(db, c, max_users=50, has_distribution=True, max_agents=None, max_couriers=None)
    c.distribution_enabled = True   # modul kompaniyada yoqilgan (birlashtirilgan paket qoidasi)
    cl = client.login(admin)
    assert cl.post('/api/users/', json=_user_body('998900000021', role='agent', branch_id=b.id)).status_code == 201
    assert cl.post('/api/users/', json=_user_body('998900000022', role='courier', branch_id=b.id)).status_code == 201
    assert cl.post('/api/users/', json=_user_body('998900000023', role='courier', branch_id=b.id)).status_code == 201


def test_create_agent_without_distribution_module_403(client, db, mk):
    c, b, _, admin = mk.tenant()
    _tariff(db, c, max_users=50, has_distribution=False)
    r = client.login(admin).post('/api/users/', json=_user_body('998900000031', role='agent', branch_id=b.id))
    assert r.status_code == 403


def test_update_user_role_to_agent_checks_limit(client, db, mk):
    c, b, _, admin = mk.tenant()
    _tariff(db, c, max_users=50, has_distribution=True, max_agents=1)
    c.distribution_enabled = True   # modul kompaniyada yoqilgan (birlashtirilgan paket qoidasi)
    mk.user(c, role=UserRole.agent, branch=b)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    r = client.login(admin).put(f'/api/users/{cashier.id}', json={'role': 'agent'})
    assert r.status_code == 400 and 'agentlari limiti' in r.json()['detail']
    assert db.get(User, cashier.id).role == UserRole.cashier
    # agentning o'zini qayta saqlash (rol o'zgarmaydi) limitga to'sqinlik qilmaydi
    ag = db.query(User).filter(User.company_id == c.id, User.role == UserRole.agent).first()
    assert client.login(admin).put(f'/api/users/{ag.id}', json={'name': 'Yangi ism'}).status_code == 200


def test_agent_courier_isolation_between_companies(client, db, mk):
    a, ba, _, admin_a = mk.tenant()
    b, bb, _, admin_b = mk.tenant()
    _tariff(db, a, max_users=50, has_distribution=True, max_agents=1)
    _tariff(db, b, max_users=50, has_distribution=True, max_agents=1)
    a.distribution_enabled = b.distribution_enabled = True
    mk.user(a, role=UserRole.agent, branch=ba)                    # faqat A to'lgan
    assert client.login(admin_a).post('/api/users/', json=_user_body('998900000041', role='agent', branch_id=ba.id)).status_code == 400
    assert client.login(admin_b).post('/api/users/', json=_user_body('998900000042', role='agent', branch_id=bb.id)).status_code == 201


def test_courier_reactivation_respects_limit(client, db, mk):
    c, b, _, admin = mk.tenant()
    _tariff(db, c, has_distribution=True, max_couriers=1)
    c.distribution_enabled = True   # modul kompaniyada yoqilgan (birlashtirilgan paket qoidasi)
    active = Courier(company_id=c.id, name='A', phone='901', is_active=True)
    off = Courier(company_id=c.id, name='B', phone='902', is_active=False)
    db.add_all([active, off])
    db.flush()
    cl = client.login(admin)
    r = cl.put(f'/api/couriers/{off.id}', json={'is_active': True})
    assert r.status_code == 400 and 'kuryerlar' in r.json()['detail']
    assert db.get(Courier, off.id).is_active is False
    # o'chirish doim mumkin; faol kuryerning boshqa maydonini o'zgartirish limitga tegmaydi
    assert cl.put(f'/api/couriers/{active.id}', json={'name': 'A2'}).status_code == 200
    assert cl.put(f'/api/couriers/{active.id}', json={'is_active': False}).status_code == 200
    # joy bo'shagach qayta yoqiladi
    assert cl.put(f'/api/couriers/{off.id}', json={'is_active': True}).status_code == 200


def test_courier_update_isolation(client, db, mk):
    a, _, _, ua = mk.tenant()
    b, _, _, _ = mk.tenant()
    _tariff(db, a, has_distribution=True, max_couriers=1)
    other = Courier(company_id=b.id, name='B', phone='902', is_active=False)
    db.add(other)
    db.flush()
    assert client.login(ua).put(f'/api/couriers/{other.id}', json={'is_active': True}).status_code == 404


def test_ensure_courier_profile_login_never_raises(db, mk):
    from app.services.mobile_service import ensure_courier_profile
    c, b, _, _ = mk.tenant()
    _tariff(db, c, has_distribution=True, max_couriers=1)
    db.add(Courier(company_id=c.id, name='Band', phone='901', is_active=True))
    db.flush()
    cu = mk.user(c, role=UserRole.courier, branch=b)
    prof = ensure_courier_profile(db, cu)                     # HTTPException ko'tarilmaydi
    assert prof is not None and prof.is_active is False and prof.user_id == cu.id
    # tarifda joy bo'lsa faol profil
    c2, b2, _, _ = mk.tenant()
    _tariff(db, c2, has_distribution=True, max_couriers=None)
    cu2 = mk.user(c2, role=UserRole.courier, branch=b2)
    assert ensure_courier_profile(db, cu2).is_active is True
    # tarifsiz korxona: cheklov yo'q
    c3, b3, _, _ = mk.tenant()
    cu3 = mk.user(c3, role=UserRole.courier, branch=b3)
    assert ensure_courier_profile(db, cu3).is_active is True


def test_mobile_courier_me_403_when_over_limit(client, db, mk):
    c, b, _, _ = mk.tenant()
    c.distribution_enabled = True
    _tariff(db, c, has_distribution=True, max_couriers=1)
    db.add(Courier(company_id=c.id, name='Band', phone='901', is_active=True))
    db.flush()
    cu = mk.user(c, role=UserRole.courier, branch=b)
    r = client.login(cu).get('/api/mobile/courier/today')
    assert r.status_code == 403 and 'faol emas' in r.json()['detail']
    # login yo'li (profil) buzilmaydi
    prof = db.query(Courier).filter(Courier.user_id == cu.id).first()
    assert prof is not None and prof.is_active is False


# ───────────────────────── downgrade ogohlantirishi: quote / subscribe ─────────────────────────

def _five_branch_company(db, mk, balance=10_000_000):
    c, b, _, u = mk.tenant()
    for _ in range(4):
        mk.branch(c)
    c.balance = balance
    db.flush()
    assert _active_branches(db, c) == 5
    return c, u


def test_quote_usage_warnings(client, db, mk):
    c, u = _five_branch_company(db, mk)
    small = _tariff(db, max_branches=1, price_per_month=100000, name='Kichik')
    big = _tariff(db, max_branches=10, price_per_month=200000, name='Katta')
    r = client.login(u).get(f'/api/billing/tariffs/{small.id}/quote?months=1')
    assert r.status_code == 200
    assert r.json()['usage_warnings'] == [{'resource': 'branches', 'used': 5, 'limit': 1}]
    assert client.login(u).get(f'/api/billing/tariffs/{big.id}/quote?months=1').json()['usage_warnings'] == []


def test_subscribe_over_limit_409_then_confirm_grandfathers(client, db, mk):
    c, u = _five_branch_company(db, mk)
    small = _tariff(db, max_branches=1, price_per_month=100000, name='Kichik')
    cl = client.login(u)
    r = cl.post('/api/billing/my-company/subscribe', json={'tariff_id': small.id, 'months': 1})
    assert r.status_code == 409
    d = r.json()['detail']
    assert d['code'] == 'over_limit'
    assert {'resource': 'branches', 'used': 5, 'limit': 1} in d['items']
    db.refresh(c)
    assert c.tariff_id is None and float(c.balance) == 10_000_000      # hech narsa yechilmadi
    # tasdiqlansa obuna faollashadi, 5 filial ishlashda davom etadi
    r = cl.post('/api/billing/my-company/subscribe', json={'tariff_id': small.id, 'months': 1, 'confirm_over_limit': True})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.tariff_id == small.id and _active_branches(db, c) == 5
    # lekin 6-sini yaratib bo'lmaydi
    assert cl.post('/api/branches', json={'name': 'Oltinchi'}).status_code == 403
    assert cl.get('/api/billing/my-company/usage').json()['usage']['branches']['over'] is True


def test_subscribe_without_overage_has_no_409(client, db, mk):
    c, b, _, u = mk.tenant()
    c.balance = 10_000_000
    t = _tariff(db, max_branches=3, price_per_month=100000)
    db.flush()
    r = client.login(u).post('/api/billing/my-company/subscribe', json={'tariff_id': t.id, 'months': 1})
    assert r.status_code == 200, r.text


def test_subscribe_renewal_same_tariff_not_blocked(client, db, mk):
    """Korxona allaqachon shu tarifda (o'tgan davrdan oshgan): uzaytirishda qayta tasdiq so'ralmaydi."""
    c, u = _five_branch_company(db, mk)
    small = _tariff(db, c, max_branches=1, price_per_month=100000, ends='past')
    r = client.login(u).post('/api/billing/my-company/subscribe', json={'tariff_id': small.id, 'months': 1})
    assert r.status_code == 200, r.text


def test_super_admin_subscribe_returns_warnings_not_block(client, db, mk):
    c, _ = _five_branch_company(db, mk)
    small = _tariff(db, max_branches=1, price_per_month=100000)
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).post(f'/api/billing/companies/{c.id}/subscribe', json={'tariff_id': small.id, 'months': 1})
    assert r.status_code == 200, r.text
    assert r.json()['warnings'] == [{'resource': 'branches', 'used': 5, 'limit': 1}]
    assert _active_branches(db, c) == 5


def test_subscribe_other_company_isolation(client, db, mk):
    """Foydalanuvchi faqat o'z korxonasi uchun obuna oladi; ogohlantirish ham o'z foydalanishi bo'yicha."""
    a, ua = _five_branch_company(db, mk)
    b, bb, _, ub = mk.tenant()
    b.balance = 10_000_000
    small = _tariff(db, max_branches=1, price_per_month=100000)
    # B (1 filial) uchun ogohlantirish yo'q, A ning 5 filiali ta'sir qilmaydi
    r = client.login(ub).post('/api/billing/my-company/subscribe', json={'tariff_id': small.id, 'months': 1})
    assert r.status_code == 200, r.text
    db.refresh(a)
    assert a.tariff_id is None


# ───────────────────────── yagona manba (statik tekshiruvlar) ─────────────────────────

def test_no_inline_limit_code_and_single_source():
    for f in ('app/routers/branches.py', 'app/routers/users.py'):
        src = _read(f)
        assert not re.search(r'\bmax_br\b|\bmax_usr\b', src), f
        assert 'app.utils.tariff_check' not in src, f
        assert 'tariff_guard' in src, f
    shim = _read('app/utils/tariff_check.py')
    assert 'def ' not in shim and 'tariff_guard' in shim            # mantiq yo'q, faqat qayta eksport
    import app.utils.tariff_check as tc
    assert tc.check_branch_limit is tg.check_branch_limit and tc.TariffLimitError is tg.TariffLimitError
    assert tc.check_user_limit is tg.check_user_limit and tc.get_company_limits is tg.get_company_limits


# ───────────────────────── migratsiya ─────────────────────────

def _load_migration():
    path = os.path.join(ROOT, 'alembic', 'versions', 't3_9_backfill_tariff_module_limits.py')
    spec = importlib.util.spec_from_file_location('t3_9_mig', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_backfills_old_state(db, mk, monkeypatch):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    mig = _load_migration()
    assert mig.revision == 't3_9' and mig.down_revision == 't3_8'

    # eski holat: has_distribution=false, max_couriers=0, lekin korxona modulni yoqib ishlayapti
    c1 = mk.company()
    c1.distribution_enabled = True
    c1.manufacturing_enabled = True
    t1 = _tariff(db, c1, has_distribution=False, has_manufacturing=False, max_couriers=0, max_agents=0)
    # modul yoqmagan korxonali tarif o'zgarmasligi kerak
    c2 = mk.company()
    t2 = _tariff(db, c2, has_distribution=False, has_manufacturing=False, max_couriers=0, max_agents=0)
    # cheklangan (0 emas) qiymatlar saqlanadi
    c3 = mk.company()
    c3.distribution_enabled = True
    t3 = _tariff(db, c3, has_distribution=False, max_couriers=3, max_agents=7)
    db.flush()

    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        mig.upgrade()
        mig.upgrade()                                                  # idempotent
    for t in (t1, t2, t3):
        db.refresh(t)
    assert t1.has_distribution is True and t1.has_manufacturing is True
    assert t1.max_couriers is None and t1.max_agents is None
    assert t2.has_distribution is False and t2.has_manufacturing is False
    assert t2.max_couriers == 0 and t2.max_agents == 0
    assert t3.has_distribution is True and t3.max_couriers == 3 and t3.max_agents == 7
    mig.downgrade()                                                    # xato bermaydi


def test_migration_unblocks_courier_creation(client, db, mk):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    mig = _load_migration()
    c, b, _, admin = mk.tenant()
    c.distribution_enabled = True
    _tariff(db, c, has_distribution=False, max_couriers=0)
    # modul kompaniyada yoqilgan va paket yo'q: tarifda modul bo'lmasa kuryer soni cheklanmaydi (birlashtirilgan qoida)
    with Operations.context(MigrationContext.configure(db.connection())):
        mig.upgrade()
    db.expire_all()
    assert client.login(admin).post('/api/couriers', json={'name': 'K', 'phone': '901234567'}).status_code == 201


# ───────────────────────── frontend / i18n (manba matni) ─────────────────────────

def _dict_keys(fname):
    src = _read('frontend', 'src', 'i18n', fname)
    return set(re.findall(r"^\s*['\"]([^'\"]+)['\"]\s*:", src, re.M))


def test_pending_keys_complete_and_new():
    with open(os.path.join(os.path.dirname(__file__), 'i18n_pending', 'T3.9.json'), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en']) and data['uz']
    for lang, d in data.items():
        for k, v in d.items():
            assert isinstance(v, str) and v.strip(), (lang, k)
    # kalitlar lug'atlarga birlashtirilgan (pending fayl o'chirilgan)
    for fname in ('uz.js', 'ru.js', 'en.js'):
        missing = set(data['uz']) - _dict_keys(fname)
        assert not missing, (fname, missing)
    # {used}/{limit}/{items} o'rin belgilari uch tilda ham bor
    for k in ('branch.limitBadge', 'warehouse.limitBadge', 'branch.warehouseLimitBadge'):
        for lang in data:
            assert '{used}' in data[lang][k] and '{limit}' in data[lang][k], (lang, k)
    for lang in data:
        assert '{items}' in data[lang]['tariffs.overLimitConfirm']


def test_frontend_keys_used_are_defined():
    with open(os.path.join(os.path.dirname(__file__), 'i18n_pending', 'T3.9.json'), encoding='utf-8') as f:
        pend = set(json.load(f)['uz'])
    known = pend | _dict_keys('uz.js')
    # boshqa agentlarning pending fayllaridagi kalitlar ham (Filiallar.jsx umumiy sahifa)
    pdir = os.path.join(os.path.dirname(__file__), 'i18n_pending')
    for fn in os.listdir(pdir):
        if fn.endswith('.json'):
            try:
                with open(os.path.join(pdir, fn), encoding='utf-8') as f:
                    known |= set(json.load(f).get('uz', {}))
            except Exception:
                pass
    # C4.2: frontend/src/i18n/pending/*.json (lug'atga birlashtirilguncha)
    fdir = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'i18n', 'pending')
    if os.path.isdir(fdir):
        for fn in os.listdir(fdir):
            if fn.endswith('.json'):
                with open(os.path.join(fdir, fn), encoding='utf-8') as f:
                    known |= set(json.load(f).get('uz', {}))
    for page in ('Tariflar.jsx', 'Filiallar.jsx', 'Warehouse.jsx'):
        src = _read('frontend', 'src', 'pages', 'admin', page)
        used = set(re.findall(r"tf\(\s*'((?:tariffs|branch|warehouse)\.[\w.]+)'", src))
        mine = {k for k in used if k in pend}
        assert mine                                                       # sahifa T3.9 kalitlarini ishlatadi
        if page != 'Warehouse.jsx':                                       # (Warehouse.jsx da boshqa agent kalitlari ham bor)
            assert used <= known, (page, used - known)


def test_frontend_wiring():
    tar = _read('frontend', 'src', 'pages', 'admin', 'Tariflar.jsx')
    assert '/billing/my-company/usage' in tar and 'confirm_over_limit' in tar and "'over_limit'" in tar
    assert 'max_branches' in tar                                    # Filiallar qatori
    assert 'Resurs Limitlari' not in tar and "tf('tariffs.resourceLimits'" in tar
    assert "tf('tariffs.productLimit'" in tar and tar.count("'Cheksiz'") == 1   # faqat tf() zaxirasi
    fil = _read('frontend', 'src', 'pages', 'admin', 'Filiallar.jsx')
    assert '/billing/my-company/usage' in fil and 'branchFull' in fil and "navigate('/admin/tariflar')" in fil
    assert 'handleReactivateBranch' in fil and 'is_active: true' in fil
    wh = _read('frontend', 'src', 'pages', 'admin', 'Warehouse.jsx')
    assert '/billing/my-company/usage' in wh and 'warehouse.limitBadge' in wh
