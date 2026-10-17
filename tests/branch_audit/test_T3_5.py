"""T3.5 — i18n va xato xabarlari: tarif limiti 403 (code=TARIFF_LIMIT).

Backend: `TariffLimitError` (403, detail satr, code/limit/current), main.py handler, `check_branch_limit`
va `check_user_limit`, POST /branches va POST /users/ javoblari, korxonalar izolyatsiyasi.
Frontend (JS ishga tushirilmaydi — manba matni va pending kalitlar tekshiriladi): axios 403 tarmog'i,
Filiallar/Users `_suppressToast`, settingsMenus t(), i18n kalitlari pending/T3.5.json da.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.models.billing import Tariff
from app.models.user import User, UserRole
from app.utils.tariff_check import TariffLimitError, check_branch_limit, check_user_limit

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FE = os.path.join(ROOT, 'frontend', 'src')


def _read(*parts):
    with open(os.path.join(FE, *parts), encoding='utf-8') as f:
        return f.read()


def _tariff(db, company, name="Boshlang'ich", max_branches=2, max_users=5):
    t = Tariff(name=name, max_branches=max_branches, max_users=max_users, is_active=True)
    db.add(t)
    db.flush()
    company.tariff_id = t.id
    company.subscription_ends_at = datetime.now(timezone.utc) + timedelta(days=30)
    db.flush()
    db.refresh(company)
    return t


@pytest.fixture
def world(db, mk):
    """A korxona: tarif max_branches=2 (1 filial bor); B korxona: alohida tarif, 2 ta faol filial bo'sh joy bilan."""
    ca, ba, wa, admin_a = mk.tenant()
    cb, bb, wb, admin_b = mk.tenant()
    _tariff(db, ca, max_branches=2, max_users=3)
    _tariff(db, cb, name='Pro', max_branches=5, max_users=10)
    cashier_a = mk.user(ca, role=UserRole.cashier, branch=ba)
    return {'ca': ca, 'ba': ba, 'admin_a': admin_a, 'cashier_a': cashier_a,
            'cb': cb, 'bb': bb, 'admin_b': admin_b}


# ───────────────────────── TariffLimitError / yordamchilar ─────────────────────────

def test_check_branch_limit_raises_tariff_limit_error(db, mk, world):
    w = world
    mk.branch(w['ca'])                       # A: 2 / 2 — to'ldi
    with pytest.raises(TariffLimitError) as ei:
        check_branch_limit(db, w['ca'].id, w['admin_a'])
    e = ei.value
    assert e.status_code == 403
    assert e.code == 'TARIFF_LIMIT'
    assert (e.limit, e.current) == (2, 2)
    assert isinstance(e.detail, str)
    assert "'Boshlang'ich' tarifi bo'yicha maksimal filiallar soni: 2" in e.detail


def test_check_branch_limit_ok_below_limit_and_exclude(db, mk, world):
    w = world
    check_branch_limit(db, w['ca'].id, w['admin_a'])          # 1 / 2 — o'tadi
    b2 = mk.branch(w['ca'])
    # qayta yoqilayotgan filial sanashda hisobga olinmaydi
    check_branch_limit(db, w['ca'].id, w['admin_a'], exclude_branch_id=b2.id)


def test_check_user_limit_raises_tariff_limit_error(db, mk, world):
    w = world
    mk.user(w['ca'], role=UserRole.warehouse)                  # admin + cashier + warehouse = 3 / 3
    with pytest.raises(TariffLimitError) as ei:
        check_user_limit(db, w['ca'].id, w['admin_a'])
    e = ei.value
    assert e.status_code == 403 and e.code == 'TARIFF_LIMIT'
    assert (e.limit, e.current) == (3, 3)
    assert 'maksimal xodimlar soni: 3' in e.detail


def test_super_admin_has_no_limit(db, mk, world):
    w = world
    mk.branch(w['ca'])
    sa = mk.user(None, role=UserRole.super_admin)
    check_branch_limit(db, w['ca'].id, sa)
    check_user_limit(db, w['ca'].id, sa)


def test_limit_counts_only_own_company(db, mk, world):
    """A korxona limiti to'lsa ham B korxonaga ta'sir qilmaydi (izolyatsiya)."""
    w = world
    mk.branch(w['ca'])
    with pytest.raises(TariffLimitError):
        check_branch_limit(db, w['ca'].id, w['admin_a'])
    check_branch_limit(db, w['cb'].id, w['admin_b'])           # B: 1 / 5


def test_tariff_limit_error_is_http_exception():
    """Eski `except HTTPException` joylari buzilmasligi uchun."""
    from fastapi import HTTPException
    e = TariffLimitError(detail='x', limit=1, current=1)
    assert isinstance(e, HTTPException) and e.status_code == 403


# ───────────────────────── HTTP javoblari ─────────────────────────

def test_post_branch_limit_returns_403_with_code(client, db, mk, world):
    w = world
    mk.branch(w['ca'])                                         # A: to'ldi
    r = client.login(w['admin_a']).post('/api/branches', json={'name': 'Uchinchi filial'})
    assert r.status_code == 403, r.text                        # 402 emas
    body = r.json()
    assert body['code'] == 'TARIFF_LIMIT'
    assert body['limit'] == 2 and body['current'] == 2
    assert isinstance(body['detail'], str)
    assert "'Boshlang'ich' tarifi bo'yicha maksimal filiallar soni: 2" in body['detail']


def test_post_branch_below_limit_succeeds(client, db, world):
    w = world
    r = client.login(w['admin_a']).post('/api/branches', json={'name': 'Ikkinchi filial'})
    assert r.status_code in (200, 201), r.text
    assert r.json()['name'] == 'Ikkinchi filial'


def test_post_branch_isolation_other_company_unaffected(client, db, mk, world):
    """A to'lgan, B esa bo'sh joyi bor: B admini filial qo'sha oladi."""
    w = world
    mk.branch(w['ca'])
    r = client.login(w['admin_b']).post('/api/branches', json={'name': 'B yangi filial'})
    assert r.status_code in (200, 201), r.text
    assert r.json()['company_id'] == w['cb'].id


def test_company_a_admin_cannot_touch_company_b_branch(client, db, world):
    w = world
    r = client.login(w['admin_a']).patch(f"/api/branches/{w['bb'].id}", json={'name': 'Hujum'})
    assert r.status_code in (403, 404), r.text
    assert 'code' not in r.json()


def test_real_permission_403_has_no_tariff_code(client, db, world):
    """Kassir POST /branches -> oddiy huquq 403 (code yo'q, frontend 'huquq yo'q' ko'rsatadi)."""
    w = world
    r = client.login(w['cashier_a']).post('/api/branches', json={'name': 'Kassir filiali'})
    assert r.status_code == 403
    assert r.json().get('code') != 'TARIFF_LIMIT'


def test_post_user_limit_returns_403_with_code(client, db, mk, world):
    w = world
    mk.user(w['ca'], role=UserRole.warehouse)                  # 3 / 3
    payload = {'name': 'Yangi', 'phone': '998901112233', 'password': 'secret123',
               'role': 'cashier', 'branch_id': w['ba'].id}
    r = client.login(w['admin_a']).post('/api/users/', json=payload)
    assert r.status_code == 403, r.text
    body = r.json()
    assert body['code'] == 'TARIFF_LIMIT'
    assert body['limit'] == 3 and body['current'] == 3
    assert 'maksimal xodimlar soni: 3' in body['detail']


def test_post_user_below_limit_succeeds(client, db, world):
    w = world                                                   # 2 / 3
    payload = {'name': 'Yangi', 'phone': '998901112244', 'password': 'secret123',
               'role': 'cashier', 'branch_id': w['ba'].id}
    r = client.login(w['admin_a']).post('/api/users/', json=payload)
    assert r.status_code == 201, r.text
    assert db.query(User).filter(User.phone == '998901112244').one().company_id == w['ca'].id


def test_post_user_isolation_other_company_unaffected(client, db, mk, world):
    w = world
    mk.user(w['ca'], role=UserRole.warehouse)                  # A to'ldi
    payload = {'name': 'B xodimi', 'phone': '998901112255', 'password': 'secret123',
               'role': 'cashier', 'branch_id': w['bb'].id}
    r = client.login(w['admin_b']).post('/api/users/', json=payload)
    assert r.status_code == 201, r.text


# ───────────────────────── Frontend manba tekshiruvlari ─────────────────────────

def _uz_keys():
    src = _read('i18n', 'uz.js')
    return {m.group(1) or m.group(2)
            for m in re.finditer(r"""^\s*(?:'((?:[^'\\]|\\.)+)'|"((?:[^"\\]|\\.)+)")\s*:""", src, re.M)}


def _lang_keys(lang):
    src = _read('i18n', f'{lang}.js')
    return {m.group(1) or m.group(2)
            for m in re.finditer(r"""^\s*(?:'((?:[^'\\]|\\.)+)'|"((?:[^"\\]|\\.)+)")\s*:""", src, re.M)}


def _pending():
    with open(os.path.join(os.path.dirname(__file__), 'i18n_pending', 'T3.5.json'), encoding='utf-8') as f:
        data = json.load(f)
    # C4.2: keyingi vazifalar kalitlari frontend/src/i18n/pending/*.json da (lug'atga birlashtirilguncha)
    fdir = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'i18n', 'pending')
    if os.path.isdir(fdir):
        for name in os.listdir(fdir):
            if name.endswith('.json'):
                with open(os.path.join(fdir, name), encoding='utf-8') as f:
                    extra = json.load(f)
                for lang, kv in extra.items():
                    data.setdefault(lang, {}).update({k: v for k, v in kv.items() if k not in data.get(lang, {})})
    return data


def _all_pending_uz():
    out = set()
    pdir = os.path.join(os.path.dirname(__file__), 'i18n_pending')
    for name in os.listdir(pdir):
        if name.endswith('.json'):
            with open(os.path.join(pdir, name), encoding='utf-8') as f:
                out |= set(json.load(f).get('uz', {}))
    return out


def _used_keys(*files):
    rx = re.compile(r"""(?<![\w$.])t\(\s*(['"])([A-Za-z0-9_.\-]+)\1\s*[,)]""")
    out = set()
    for f in files:
        out |= {m.group(2) for m in rx.finditer(_read(*f))}
    return out


CHANGED_FILES = [
    ('api', 'axios.js'),
    ('components', 'AdminLayout.jsx'),
    ('components', 'ShiftOpenModal.jsx'),
    ('constants', 'settingsMenus.jsx'),
    ('pages', 'admin', 'Filiallar.jsx'),
    ('pages', 'admin', 'Ombor.jsx'),
    ('pages', 'admin', 'Warehouse.jsx'),
    ('pages', 'admin', 'Settings', 'Users.jsx'),
]


def test_pending_has_same_new_keys_in_all_languages():
    p = _pending()
    assert set(p) == {'uz', 'ru', 'en'}
    # yangi kalitlar (uz da pending orqali keladi) ru/en da ham bor
    assert set(p['uz']) <= set(p['ru']) and set(p['uz']) <= set(p['en'])
    # bo'sh qiymat yo'q; {count}/{name}/{date}/{status} o'rinbosarlari tillar bo'yicha bir xil
    for k, v in p['uz'].items():
        for lang in ('ru', 'en'):
            assert p[lang][k].strip(), (lang, k)
            assert sorted(re.findall(r'\{\w+\}', v)) == sorted(re.findall(r'\{\w+\}', p[lang][k])), (lang, k)


def test_ui29_nine_missing_keys_are_added_in_all_languages():
    p = _pending()
    nine = ['ombor.selectVariant', 'ombor.selectVariantError', 'common.settings', 'kassa.accept', 'kassa.reject',
            'kassa.pendingTransfers', 'kassa.transferAccepted', 'kassa.transferRejected', 'auth.errOfertaReq']
    for lang in ('uz', 'ru', 'en'):
        for k in nine:
            assert p[lang].get(k), (lang, k)


def test_ui30_gaps_filled_en_and_ru():
    p = _pending()
    for k in ('settings.addBranch', 'settings.branchName', 'settings.branchEmpty', 'settings.deactivateBranch',
              'settings.tab.branches', 'ops.tab.transfers', 'purchase.selectWarehouse', 'tariffs.maxBranches'):
        assert p['en'].get(k), k
    for k in ('finance.wallet', 'finance.wallets', 'finance.balance', 'finance.addWallet',
              'finance.addWalletPrompt', 'finance.noWallets', 'customer.totalCreditors',
              'product.productsCount', 'settings.pageDesc'):
        assert p['ru'].get(k), k


def test_plural_keys_for_warehouse_count():
    p = _pending()
    assert p['ru']['branch.warehouseCount.one'] == '{count} склад'
    assert p['ru']['branch.warehouseCount.few'] == '{count} склада'
    assert p['ru']['branch.warehouseCount.many'] == '{count} складов'
    assert p['en']['branch.warehouseCount.one'] == '{count} warehouse'
    assert p['en']['branch.warehouseCount.other'] == '{count} warehouses'


def test_every_t_key_in_changed_files_exists():
    # boshqa vazifalar (T3.1, T3.2, T3.3 ...) kalitlari ham o'z pending fayllarida turadi
    have = _uz_keys() | set(_pending()['uz']) | _all_pending_uz()
    missing = sorted(_used_keys(*CHANGED_FILES) - have)
    assert missing == []


def test_settings_menus_use_t_for_every_id():
    src = _read('constants', 'settingsMenus.jsx')
    assert 'getSettingsMenus = (t) =>' in src
    ids = re.findall(r"id: '([\w-]+)'", src)
    assert len(ids) >= 14
    p = _pending()
    for i in ids:
        assert f"t('settings.menu.{i}')" in src
        for lang in ('uz', 'ru', 'en'):
            # T4.6 kabi keyingi vazifalar menyusi kaliti (settings.menu.approvals) lug'atga birlashtirilgan
            assert p[lang].get(f'settings.menu.{i}') or f'settings.menu.{i}' in _lang_keys(lang), (lang, i)


def test_axios_tariff_limit_and_translated_messages():
    src = _read('api', 'axios.js')
    assert "'TARIFF_LIMIT'" in src
    assert "createTranslator" in src and "getStoredLang" in src
    for k in ('timeout', 'forbidden', 'notFound', 'invalid', 'server', 'network'):
        assert f"api.error.{k}" in src
    # qattiq yozilgan o'zbekcha interceptor matnlari qolmagan
    for text in ("Sizda bu amalni bajarish huquqi yo'q", "Server bilan aloqa yo'q", "So'rov vaqti tugadi"):
        assert text not in src
    # 402 -> /admin/tariflar redirect hanuz bor (tarif limiti esa 402 emas)
    assert "status === 402" in src


def test_filiallar_and_users_suppress_interceptor_toast():
    fil = _read('pages', 'admin', 'Filiallar.jsx')
    assert fil.count('_suppressToast: true') >= 5
    usr = _read('pages', 'admin', 'Settings', 'Users.jsx')
    assert "api.post('/users/', payload, { _suppressToast: true })" in usr
    assert 'alert(' not in usr


def test_load_errors_not_swallowed_in_warehouse_pages():
    for f in (('pages', 'admin', 'Warehouse.jsx'), ('pages', 'admin', 'Ombor.jsx')):
        src = _read(*f)
        assert 'console.error' not in src, f
        assert 'alert(' not in src, f
        assert 'loadError' in src and "common.retry" in src and "common.loadError" in src, f


def test_hardcoded_texts_moved_to_t():
    lay = _read('components', 'AdminLayout.jsx')
    assert '>Sozlamalar<' not in lay and 'toast.success("copied")' not in lay
    assert "t('subscription.expiredMsg')" in lay
    shift = _read('components', 'ShiftOpenModal.jsx')
    for text in ('Smena ochilmagan', "To'lov qilish uchun avval smenani oching", 'Filialni tanlang'):
        assert text not in shift
    assert "useLang" in shift


def test_plural_support_in_translator():
    src = _read('i18n', 'index.js')
    assert 'Intl.PluralRules' in src
    assert 'vars.count' in src


def test_vitest_added():
    with open(os.path.join(ROOT, 'frontend', 'package.json'), encoding='utf-8') as f:
        pkg = json.load(f)
    assert pkg['scripts']['test'] == 'vitest run'
    assert 'vitest' in pkg['devDependencies']
    assert os.path.exists(os.path.join(FE, 'i18n', '__tests__', 'i18n.test.js'))
