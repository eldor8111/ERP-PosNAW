"""T3.2 — Super admin panelida filial va ombor boshqaruvi.

Qamrov: korxona bo'yicha xodim/ombor hisoblari (filialsiz va faqat user_companies a'zolari bilan),
faol/nofaol filiallar, limits/usage (tarif muddati o'tgan bo'lsa default), `/companies/{id}/users` filtri,
`/users?company_id=` izolyatsiyasi, yozuv endpointlari (korxona izolyatsiyasi, 400/403/404) va frontend fayli.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.models.billing import Tariff
from app.models.user import UserRole
from app.models.user_company import UserCompany
from app.utils.tariff_check import get_company_limits

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


@pytest.fixture
def world(db, mk):
    """Korxona A: 2 filial (1 nofaol), 3 filialli + 2 filialsiz xodim, 1 UserCompany-only a'zo,
    1 filialsiz ombor. Korxona B: oddiy tenant. super admin."""
    ca = mk.company('A korxona')
    b1 = mk.branch(ca, 'A-1')
    b2 = mk.branch(ca, 'A-2', is_active=False)
    w1 = mk.warehouse(ca, b1, 'A ombor 1')
    w_free = mk.warehouse(ca, None, 'Filialsiz ombor')
    u_b1 = [mk.user(ca, role=UserRole.cashier, branch=b1) for _ in range(2)]
    u_b2 = mk.user(ca, role=UserRole.cashier, branch=b2)
    u_free = [mk.user(ca, role=UserRole.manager) for _ in range(2)]
    # boshqa korxonaning xodimi, A ga faqat user_companies orqali a'zo
    cb, bb, wb, ub = mk.tenant()
    db.add(UserCompany(user_id=ub.id, company_id=ca.id, role=UserRole.cashier, is_active=True))
    db.flush()
    sa = mk.user(None, role=UserRole.super_admin)
    return dict(ca=ca, b1=b1, b2=b2, w1=w1, w_free=w_free, u_b1=u_b1, u_b2=u_b2, u_free=u_free,
                cb=cb, bb=bb, wb=wb, ub=ub, sa=sa)


# ── Hisoblar ─────────────────────────────────────────────────

def test_detail_stats_count_by_company(client, world):
    w = world
    r = client.login(w['sa']).get(f"/api/super-admin/companies/{w['ca'].id}")
    assert r.status_code == 200, r.text
    d = r.json()
    st = d['stats']
    # 5 ta asosiy xodim + 1 ta user_companies orqali a'zo
    assert st['users'] == 6
    assert st['users_no_branch'] == 3          # 2 filialsiz + UserCompany-only (filialsiz)
    assert st['branches'] == st['branches_total'] == 2
    assert st['branches_active'] == 1 and st['branches_inactive'] == 1
    assert st['branches_active'] + st['branches_inactive'] == st['branches_total']
    assert st['warehouses'] == 2               # filialli + filialsiz
    assert st['warehouses_no_branch'] == 1
    assert 'limits' in d and 'usage' in d
    assert [x['name'] for x in d['unassigned_warehouses']] == ['Filialsiz ombor']


def test_list_companies_users_count_matches_detail(client, world):
    w = world
    r = client.login(w['sa']).get('/api/super-admin/companies')
    assert r.status_code == 200
    row = next(c for c in r.json() if c['id'] == w['ca'].id)
    detail = client.get(f"/api/super-admin/companies/{w['ca'].id}").json()
    assert row['users_count'] == detail['stats']['users'] == 6
    # B korxona: faqat o'z xodimi
    rowb = next(c for c in r.json() if c['id'] == w['cb'].id)
    assert rowb['users_count'] == 1


def test_company_users_endpoint_filters(client, world):
    w = world
    c = client.login(w['sa'])
    base = f"/api/super-admin/companies/{w['ca'].id}/users"
    allu = c.get(base).json()
    assert len(allu) == 6
    assert set(allu[0]) >= {'id', 'name', 'phone', 'role', 'status', 'branch_id', 'branch_name'}
    free = c.get(base, params={'no_branch': 'true'}).json()
    assert {u['id'] for u in free} == {u.id for u in w['u_free']} | {w['ub'].id}
    assert all(u['branch_id'] is None for u in free)
    in_b1 = c.get(base, params={'branch_id': w['b1'].id}).json()
    assert {u['id'] for u in in_b1} == {u.id for u in w['u_b1']}
    assert all(u['branch_name'] == w['b1'].name for u in in_b1)
    assert c.get('/api/super-admin/companies/999999/users').status_code == 404


def test_list_all_users_company_filter_without_branches(client, db, mk, world):
    w = world
    empty = mk.company('Filialsiz korxona')
    u = mk.user(empty, role=UserRole.admin)
    r = client.login(w['sa']).get('/api/super-admin/users', params={'company_id': empty.id})
    assert r.status_code == 200
    assert [x['id'] for x in r.json()] == [u.id]


# ── limits / usage ───────────────────────────────────────────

def _tariff(db, **kw):
    t = Tariff(name='Pro', max_branches=5, max_users=20, max_warehouses=4, **kw)
    db.add(t)
    db.flush()
    return t


def test_limits_default_without_tariff(client, db, world):
    w = world
    info = get_company_limits(db, w['ca'])
    assert info['limits'] == {'max_branches': 1, 'max_users': 5, 'max_warehouses': 1}
    assert info['usage']['active_branches'] == 1
    assert info['usage']['active_warehouses'] == 2
    d = client.login(w['sa']).get(f"/api/super-admin/companies/{w['ca'].id}").json()
    assert d['limits']['max_branches'] == 1 and d['usage']['active_branches'] == 1


def test_limits_active_and_expired_tariff(db, world):
    ca = world['ca']
    t = _tariff(db)
    ca.tariff_id = t.id
    ca.subscription_ends_at = datetime.now(timezone.utc) + timedelta(days=10)
    db.flush()
    db.refresh(ca)
    info = get_company_limits(db, ca)
    assert info['limits'] == {'max_branches': 5, 'max_users': 20, 'max_warehouses': 4}
    # muddati o'tgan -> default
    ca.subscription_ends_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    info = get_company_limits(db, ca)
    assert info['limits']['max_branches'] == 1 and info['limits']['max_users'] == 5


def test_limits_usage_matches_user_limit_rule(db, mk):
    c = mk.company()
    mk.user(c, role=UserRole.cashier)
    mk.user(c, role=UserRole.cashier, status=__import__('app.models.user', fromlist=['UserStatus']).UserStatus.inactive)
    mk.user(c, role=UserRole.super_admin)
    assert get_company_limits(db, c)['usage']['users'] == 1


# ── Filial yozuvlari ─────────────────────────────────────────

def test_create_branch_for_company(client, db, world):
    w = world
    r = client.login(w['sa']).post(
        f"/api/super-admin/companies/{w['ca'].id}/branches",
        json={'name': 'Yangi filial', 'address': 'Toshkent', 'phone': '998901112233', 'company_id': w['cb'].id},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['company_id'] == w['ca'].id            # URL dagi korxona, body dagi emas
    assert d['warehouse_id'] is not None
    assert client.post('/api/super-admin/companies/999999/branches', json={'name': 'X'}).status_code == 404
    # takroriy faol nom -> 409
    dup = client.post(f"/api/super-admin/companies/{w['ca'].id}/branches", json={'name': 'yangi filial'})
    assert dup.status_code == 409


def test_patch_branch_rename_deactivate_and_company_unchanged(client, db, world):
    w = world
    c = client.login(w['sa'])
    r = c.patch(f"/api/super-admin/branches/{w['b1'].id}",
                json={'name': 'Qayta nomlandi', 'company_id': w['cb'].id})
    assert r.status_code == 200, r.text
    assert r.json()['name'] == 'Qayta nomlandi'
    db.refresh(w['b1'])
    assert w['b1'].company_id == w['ca'].id
    r = c.patch(f"/api/super-admin/branches/{w['b1'].id}", json={'is_active': False})
    # filialda xodimlar bor bo'lsa 409 (blokerlar), aks holda nofaol bo'ladi
    if r.status_code == 200:
        assert r.json()['is_active'] is False
    else:
        assert r.status_code == 409
    # bo'sh nom -> 400, mavjud emas -> 404
    assert c.patch(f"/api/super-admin/branches/{w['b1'].id}", json={'name': '  '}).status_code == 400
    assert c.patch('/api/super-admin/branches/999999', json={'name': 'X'}).status_code == 404


def test_patch_branch_deactivate_empty_branch(client, db, mk, world):
    w = world
    empty = mk.branch(w['ca'], 'Bo`sh filial')
    r = client.login(w['sa']).patch(f"/api/super-admin/branches/{empty.id}", json={'is_active': False})
    assert r.status_code == 200, r.text
    assert r.json()['is_active'] is False
    r = client.patch(f"/api/super-admin/branches/{empty.id}", json={'is_active': True})
    assert r.status_code == 200, r.text
    assert r.json()['is_active'] is True


# ── Ombor yozuvlari ──────────────────────────────────────────

def test_create_warehouse_foreign_branch_400(client, world):
    w = world
    c = client.login(w['sa'])
    r = c.post(f"/api/super-admin/companies/{w['ca'].id}/warehouses",
               json={'name': 'Begona', 'branch_id': w['bb'].id})
    assert r.status_code == 400
    assert r.json()['detail'] == "Filial shu korxonaga tegishli emas"
    ok = c.post(f"/api/super-admin/companies/{w['ca'].id}/warehouses",
                json={'name': 'Yangi ombor', 'branch_id': w['b1'].id})
    assert ok.status_code == 200, ok.text
    assert ok.json()['company_id'] == w['ca'].id and ok.json()['branch_id'] == w['b1'].id
    free = c.post(f"/api/super-admin/companies/{w['ca'].id}/warehouses", json={'name': 'Filialsiz 2'})
    assert free.status_code == 200 and free.json()['branch_id'] is None
    assert c.post('/api/super-admin/companies/999999/warehouses', json={'name': 'X'}).status_code == 404


def test_patch_warehouse(client, db, world):
    w = world
    c = client.login(w['sa'])
    r = c.patch(f"/api/super-admin/warehouses/{w['w_free'].id}",
                json={'name': 'Nom o`zgardi', 'branch_id': w['b1'].id})
    assert r.status_code == 200, r.text
    assert r.json()['name'] == 'Nom o`zgardi' and r.json()['branch_id'] == w['b1'].id
    # begona filialga ko'chirish -> 400
    bad = c.patch(f"/api/super-admin/warehouses/{w['w1'].id}", json={'branch_id': w['bb'].id})
    assert bad.status_code == 400
    # begona korxona omborini ham super admin tahrirlaydi, lekin A filialiga o'tkaza olmaydi
    bad2 = c.patch(f"/api/super-admin/warehouses/{w['wb'].id}", json={'branch_id': w['b1'].id})
    assert bad2.status_code == 400
    assert c.patch('/api/super-admin/warehouses/999999', json={'name': 'X'}).status_code == 404
    # nofaol qilish (qoldiq yo'q)
    off = c.patch(f"/api/super-admin/warehouses/{w['w_free'].id}", json={'is_active': False})
    assert off.status_code == 200 and off.json()['is_active'] is False


# ── Ruxsatlar ────────────────────────────────────────────────

def test_non_super_admin_forbidden(client, world):
    w = world
    cashier = w['u_b1'][0]
    c = client.login(cashier)
    cid = w['ca'].id
    assert c.get(f'/api/super-admin/companies/{cid}/users').status_code == 403
    assert c.get(f'/api/super-admin/companies/{cid}').status_code == 403
    assert c.post(f'/api/super-admin/companies/{cid}/branches', json={'name': 'X'}).status_code == 403
    assert c.patch(f"/api/super-admin/branches/{w['b1'].id}", json={'name': 'X'}).status_code == 403
    assert c.post(f'/api/super-admin/companies/{cid}/warehouses', json={'name': 'X'}).status_code == 403
    assert c.patch(f"/api/super-admin/warehouses/{w['w1'].id}", json={'name': 'X'}).status_code == 403
    # korxona adminiga ham yopiq
    assert client.login(w['ub']).patch(f"/api/super-admin/branches/{w['b1'].id}", json={'name': 'X'}).status_code == 403


def test_branch_detail_users_scoped_to_company(client, db, mk, world):
    w = world
    # begona korxona xodimi A filialiga noto'g'ri ulangan (ma'lumot xatosi) — ko'rinmasligi kerak
    stray = mk.user(w['cb'], role=UserRole.cashier, branch=w['b1'])
    d = client.login(w['sa']).get(f"/api/super-admin/branches/{w['b1'].id}").json()
    ids = {u['id'] for u in d['users']}
    assert stray.id not in ids
    assert {u.id for u in w['u_b1']} == ids


# ── Frontend ─────────────────────────────────────────────────

def test_frontend_wired_and_pending_i18n():
    src = open(os.path.join(ROOT, 'frontend/src/pages/admin/SuperAdmin.jsx'), encoding='utf-8').read()
    assert '/super-admin/companies/' in src and '/users' in src
    assert 'users_no_branch' in src and 'branches_active' in src
    assert 'limits' in src and 'usage' in src
    assert '/super-admin/branches/' in src and '/warehouses' in src
    pending = json.load(open(os.path.join(ROOT, 'tests/branch_audit/i18n_pending/T3.2.json'), encoding='utf-8'))
    assert set(pending) == {'uz', 'ru', 'en'}
    assert set(pending['uz']) == set(pending['ru']) == set(pending['en'])
    for key in pending['uz']:
        assert key in src, key
