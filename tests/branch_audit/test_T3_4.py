"""T3.4 — Xodim formalari, huquqlar va mojibake.

Backend: POST/PUT /users/ da filial majburiyligi (cashier/warehouse, 2+ faol filial), tahrirda faqat
rol yoki `branch_id` yuborilganda tekshiriladi; korxonalar izolyatsiyasi; role + role_id birga saqlanadi.
Frontend (JS ishga tushirilmaydi — manba matni tekshiriladi): Register marshruti yo'q, mojibake yo'q,
umumiy RoleSelect/BranchSelect, formatBalances, isPageAllowed alias, huquq tavsiflari, i18n pending kalitlari.
"""
import json
import os
import re

import pytest

from app.models.role import Role
from app.models.user import User, UserRole
from app.models.user_company import UserCompany

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FE = os.path.join(ROOT, 'frontend', 'src')


def _read(*parts):
    with open(os.path.join(FE, *parts), encoding='utf-8') as f:
        return f.read()


def _uc(db, user, company, role, branch=None):
    uc = UserCompany(user_id=user.id, company_id=company.id, role=role, permissions={}, is_active=True,
                     branch_id=branch.id if branch else None)
    db.add(uc)
    db.flush()
    return uc


def _payload(phone, role, **kw):
    d = {'name': 'Yangi xodim', 'phone': phone, 'password': 'secret123', 'role': role}
    d.update(kw)
    return d


@pytest.fixture
def world(db, mk):
    """A korxona: 2 faol filial + admin; B korxona: 1 filial + admin."""
    ca, cb = mk.company(), mk.company()
    ba1, ba2 = mk.branch(ca), mk.branch(ca)
    bb = mk.branch(cb)
    mk.warehouse(ca, ba1)
    mk.warehouse(cb, bb)
    admin_a = mk.user(ca, role=UserRole.admin, branch=ba1)
    admin_b = mk.user(cb, role=UserRole.admin, branch=bb)
    _uc(db, admin_a, ca, UserRole.admin, ba1)
    _uc(db, admin_b, cb, UserRole.admin, bb)
    return dict(ca=ca, cb=cb, ba1=ba1, ba2=ba2, bb=bb, admin_a=admin_a, admin_b=admin_b)


# ─── Backend: filial majburiyligi ───

def test_cashier_without_branch_400_when_company_has_branches(client, db, world):
    w = world
    for i, role in enumerate(('cashier', 'warehouse')):
        r = client.login(w['admin_a']).post('/api/users/', json=_payload(f'99890111000{i}', role))
        assert r.status_code == 400, r.text
        assert 'filial' in r.json()['detail'].lower()
    assert db.query(User).filter(User.phone.like('99890111000%')).count() == 0


def test_cashier_with_branch_created(client, db, world):
    w = world
    r = client.login(w['admin_a']).post('/api/users/', json=_payload('998901110010', 'cashier', branch_id=w['ba2'].id))
    assert r.status_code == 201, r.text
    assert r.json()['branch_id'] == w['ba2'].id


def test_admin_without_branch_created(client, db, world):
    w = world
    r = client.login(w['admin_a']).post('/api/users/', json=_payload('998901110020', 'admin'))
    assert r.status_code == 201, r.text
    r = client.login(w['admin_a']).post('/api/users/', json=_payload('998901110021', 'manager'))
    assert r.status_code == 201, r.text


def test_cashier_branchless_allowed_when_company_has_single_branch(client, db, world):
    """Bitta faol filialli korxonada backend filialsiz kassirga to'sqinlik qilmaydi (forma filialni o'zi tanlaydi)."""
    w = world
    r = client.login(w['admin_b']).post('/api/users/', json=_payload('998901110030', 'cashier'))
    assert r.status_code == 201, r.text


def test_edit_name_of_legacy_branchless_cashier_allowed(client, db, mk, world):
    w = world
    legacy = mk.user(w['ca'], role=UserRole.cashier, branch=None)
    _uc(db, legacy, w['ca'], UserRole.cashier, None)
    r = client.login(w['admin_a']).put(f"/api/users/{legacy.id}", json={'name': 'Yangi ism'})
    assert r.status_code == 200, r.text
    assert r.json()['name'] == 'Yangi ism'


def test_edit_clearing_branch_or_changing_role_requires_branch(client, db, mk, world):
    w = world
    cashier = mk.user(w['ca'], role=UserRole.cashier, branch=w['ba1'])
    _uc(db, cashier, w['ca'], UserRole.cashier, w['ba1'])
    # branch_id aniq None yuborildi (fields_set da) — kassirni filialsiz qoldirib bo'lmaydi
    r = client.login(w['admin_a']).put(f"/api/users/{cashier.id}", json={'branch_id': None})
    assert r.status_code == 400, r.text
    # filial almashtirish — ok
    r = client.login(w['admin_a']).put(f"/api/users/{cashier.id}", json={'branch_id': w['ba2'].id})
    assert r.status_code == 200, r.text
    # filialsiz manager omborchi/kassirga aylantirilsa — filial kerak
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=None)
    _uc(db, mgr, w['ca'], UserRole.manager, None)
    r = client.login(w['admin_a']).put(f"/api/users/{mgr.id}", json={'role': 'warehouse'})
    assert r.status_code == 400, r.text
    r = client.login(w['admin_a']).put(f"/api/users/{mgr.id}", json={'role': 'warehouse', 'branch_id': w['ba1'].id})
    assert r.status_code == 200, r.text


# ─── Backend: korxonalar izolyatsiyasi ───

def test_cross_company_isolation(client, db, mk, world):
    w = world
    only_b = mk.user(w['cb'], role=UserRole.cashier, branch=w['bb'])
    _uc(db, only_b, w['cb'], UserRole.cashier, w['bb'])
    # A admini B xodimini o'zgartira olmaydi
    r = client.login(w['admin_a']).put(f"/api/users/{only_b.id}", json={'name': 'Hujum'})
    assert r.status_code in (403, 404), r.text
    # A admini begona (B) filialga xodim biriktira olmaydi
    r = client.login(w['admin_a']).post('/api/users/', json=_payload('998901110040', 'cashier', branch_id=w['bb'].id))
    assert r.status_code in (400, 403, 404), r.text
    assert db.query(User).filter(User.phone == '998901110040').count() == 0
    # ijobiy yo'l: B admini o'z xodimini tahrirlaydi
    r = client.login(w['admin_b']).put(f"/api/users/{only_b.id}", json={'name': 'Yangi'})
    assert r.status_code == 200, r.text


def test_custom_role_saved_with_base_role_and_foreign_role_rejected(client, db, world):
    w = world
    own = Role(name='Filial kassiri', company_id=w['ca'].id, permissions={})
    foreign = Role(name='Begona', company_id=w['cb'].id, permissions={})
    db.add_all([own, foreign])
    db.flush()
    r = client.login(w['admin_a']).post('/api/users/', json=_payload(
        '998901110050', 'cashier', role_id=own.id, branch_id=w['ba1'].id))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body['role'] == 'cashier' and body['role_id'] == own.id
    r = client.login(w['admin_a']).post('/api/users/', json=_payload(
        '998901110051', 'cashier', role_id=foreign.id, branch_id=w['ba1'].id))
    assert r.status_code in (400, 403, 404), r.text


# ─── Frontend: manba matni tekshiruvi ───

def test_register_route_removed_from_app():
    app = _read('App.jsx')
    assert 'employees/create' not in app
    assert "pages/Register'" not in app and not re.search(r"<Register\s*/>", app)
    assert 'RegisterCompany' in app            # korxona ro'yxatdan o'tishi saqlanadi
    for root, _, files in os.walk(FE):
        for fn in files:
            if fn.endswith(('.js', '.jsx')):
                assert 'employees/create' not in open(os.path.join(root, fn), encoding='utf-8').read(), fn


def test_no_mojibake_in_frontend_src():
    """Qabul mezoni 6: 'тАФ' / 'тЬ' va shu turdagi buzilgan kodlash belgilari qolmasin."""
    bad = re.compile('т[АЬЖФ][Ѐ-ӿ]|тАФ|тЬ|тФ|тЖ')
    hits = []
    for root, _, files in os.walk(FE):
        for fn in files:
            if fn.endswith(('.js', '.jsx')):
                p = os.path.join(root, fn)
                for i, line in enumerate(open(p, encoding='utf-8').read().split('\n'), 1):
                    if bad.search(line):
                        hits.append(f'{os.path.relpath(p, FE)}:{i}')
    assert not hits, hits
    # Foydalanuvchi sahifalarida umuman kirill belgilari bo'lmasligi kerak (barcha matn lotin/o'zbek)
    for rel in (('pages', 'admin', 'Users.jsx'), ('pages', 'admin', 'Settings', 'Users.jsx')):
        assert not re.search('[Ѐ-ӿ]', _read(*rel)), rel


def test_users_pages_use_shared_components():
    for rel in (('pages', 'admin', 'Users.jsx'), ('pages', 'admin', 'Settings', 'Users.jsx')):
        src = _read(*rel)
        assert 'components/users/RoleSelect' in src and 'components/users/BranchSelect' in src
        assert not re.search(r'^function (RoleSelect|BranchSelect)\b', src, re.M)   # lokal nusxalar yo'q
        assert 'formatBalances(w.balances?.total, t)' in src
        assert 'role_id: form.role_id' in src                                    # role + role_id ikkalasi yuboriladi
        assert 'activeBranches.length === 1' in src                              # bitta filial oldindan tanlanadi
        assert 'w.branch_name' in src                                            # kassa qatorida filial nomi
    assert "w.balances?.total) || 0).toLocaleString" not in _read('pages', 'admin', 'Users.jsx')
    assert "find(t => t.currency" not in _read('pages', 'admin', 'Settings', 'Users.jsx')
    assert "'✓ Default'" not in _read('pages', 'admin', 'Settings', 'Users.jsx')


def test_branch_select_contract():
    src = _read('components', 'users', 'BranchSelect.jsx')
    assert 'allowEmpty' in src and 'warehouses_count === 0' in src and 'user.branchNoWarehouse' in src
    assert 'user.selectBranchPlaceholder' in src and 'user.noBranch' in src
    assert re.search(r'<option value="" disabled>', src) and 'required={isRequired}' in src


def test_role_select_contract():
    src = _read('components', 'users', 'RoleSelect.jsx')
    for k in ('user.systemRoles', 'user.customRoles', 'user.baseRole', 'user.customRoleNote'):
        assert k in src
    assert "DEFAULT_BASE_ROLE = 'cashier'" in src and 'role_id' in src


def test_money_and_permissions_utils_contract():
    money = _read('utils', 'money.js')
    assert 'export function formatBalances(total, t)' in money
    assert 'Array.isArray(total)' in money and "' · '" in money and "common.sum" in money
    perms = _read('utils', 'permissions.js')
    assert "PERMISSION_ALIASES = { ombor: ['ombor', 'warehouse'] }" in perms
    assert 'export function isPageAllowed(user, key)' in perms
    assert "'super_admin'" in perms and '!== false' in perms
    route = _read('components', 'PrivateRoute.jsx')
    assert "from '../utils/permissions'" in route and 'isPageAllowed(user, permKey)' in route


def test_permission_constants_match_pages():
    src = _read('constants', 'permissions.js')
    assert "Filiallar sahifasi: filial va omborlarni boshqarish" in src
    assert "Filiallar o'rtasida tovar ko'chirish" not in src
    assert re.search(r"^\s*ombor:\s*\{ label: \"Ombor va ko'chirish\"", src, re.M)
    assert re.search(r"^\s*warehouse:\s*\{", src, re.M)          # eski kalit saqlanadi (route warehouse)


def test_i18n_pending_keys_complete_and_new():
    p = os.path.join(os.path.dirname(__file__), 'i18n_pending', 'T3.4.json')
    d = json.load(open(p, encoding='utf-8'))
    assert set(d) == {'uz', 'ru', 'en'}
    assert set(d['uz']) == set(d['ru']) == set(d['en'])
    required = {'user.selectBranchPlaceholder', 'user.branchRequired', 'user.branchNoWarehouse', 'user.baseRole',
                'user.customRoleNote', 'user.systemRoles', 'user.customRoles'}
    assert required <= set(d['uz'])
    assert all(v.strip() for lang in d.values() for v in lang.values())
    uz = _read('i18n', 'uz.js')
    # kalitlar uz.js ga birlashtirilgan (pending fayl o'chirilgan)
    for k in d['uz']:
        assert f"'{k}'" in uz, f'{k} uz.js da yo\'q'
