"""C0.2 — 0-bosqich tozalash: frontend va i18n qoldiqlari.

i18n: uz/ru/en fayllari regex bilan o'qiladi, yangi kalitlar uchala tilda ham
borligi, to'plamlar bir xilligi va {n}/{phone} o'rin egalari saqlanganligi
tekshiriladi. Frontend: w.balance himoyasi, InventoryCounts esc(), ReceiptTab
rol cheklovi, kuryer unlink tugmasi, SuperAdmin "moved" bloki.
Backend: kuryer unlink-telegram endpointi (yangi tugma shuni chaqiradi) uchun
ikki korxona izolyatsiyasi.
"""
import os
import re

import pytest

from app.models.courier import Courier
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
I18N = os.path.join(ROOT, 'frontend', 'src', 'i18n')
ADMIN = os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin')
LANGS = ('uz', 'ru', 'en')

# Bir qatorli flat kalit: '<kalit>': '<qiymat>' yoki "<qiymat>"
KEY_RE = re.compile(r"""^\s*'([^']+)':\s*(?:'((?:[^'\\]|\\.)*)'|"([^"]*)")\s*,?\s*$""", re.M)

NEW_KEYS = [
    'tariff.ownerOnly',
    'settings.adminBot.linkHintTitle', 'settings.adminBot.linkHint',
    'superAdmin.purge.moved',
    'user.sharedNote',
    'ops.remainderFromDebt', 'ops.selectCustomerForRemainder',
    'settings.apiKeys.lastUsed', 'settings.apiKeys.prefix',
    'settings.general.mpDefaultBranch', 'settings.general.mpDefaultBranchDesc',
    'settings.general.mpDefaultBranchNone',
    'profile.editTitle', 'profile.nameLabel', 'profile.emailLabel', 'profile.phoneNote',
    'profile.changePassword', 'profile.currentPassword', 'profile.newPassword',
    'profile.confirmPassword', 'profile.nameTooShort', 'profile.passwordTooShort',
    'profile.passwordMismatch', 'profile.currentPasswordRequired', 'profile.saved',
    'courier.unlinkTelegram', 'courier.unlinked',
]
PLACEHOLDERS = {'superAdmin.purge.moved': '{n}', 'profile.phoneNote': '{phone}'}


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _i18n(lang):
    """Fayldagi barcha kalitlar: kalit -> qiymat (regex, modulni yuklamasdan)."""
    out = {}
    for m in KEY_RE.finditer(_read(os.path.join(I18N, f'{lang}.js'))):
        out[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    return out


@pytest.fixture(scope='module')
def dicts():
    return {lang: _i18n(lang) for lang in LANGS}


# ───────────── i18n ─────────────

@pytest.mark.parametrize('key', NEW_KEYS)
def test_new_key_in_all_langs(dicts, key):
    for lang in LANGS:
        assert key in dicts[lang], f'{lang}.js da {key} yo\'q'
        assert dicts[lang][key].strip(), f'{lang}.js da {key} bo\'sh'


def test_new_key_sets_equal_across_langs(dicts):
    sets = {lang: set(NEW_KEYS) & set(dicts[lang]) for lang in LANGS}
    assert sets['uz'] == sets['ru'] == sets['en'] == set(NEW_KEYS)


def test_no_duplicate_new_keys():
    for lang in LANGS:
        text = _read(os.path.join(I18N, f'{lang}.js'))
        for key in NEW_KEYS:
            n = len(re.findall(r"^\s*'%s':" % re.escape(key), text, re.M))
            assert n == 1, f'{lang}.js: {key} {n} marta uchraydi'


@pytest.mark.parametrize('key,ph', sorted(PLACEHOLDERS.items()))
def test_placeholders_kept(dicts, key, ph):
    for lang in LANGS:
        assert ph in dicts[lang][key], f'{lang}.js: {key} da {ph} yo\'q'


def test_profile_jsx_keys_exist_in_uz(dicts):
    src = _read(os.path.join(ADMIN, 'Profile.jsx'))
    used = set(re.findall(r"""t\(\s*['"](profile\.[A-Za-z0-9_]+)['"]""", src))
    assert used, 'Profile.jsx da profile.* kalitlari topilmadi'
    missing = sorted(k for k in used if k not in dicts['uz'])
    assert not missing, f'uz.js da yo\'q: {missing}'


@pytest.mark.parametrize('fname', [
    'Settings.jsx', 'Users.jsx', 'Operations.jsx', 'Tariflar.jsx', 'Couriers.jsx', 'SuperAdmin.jsx',
    os.path.join('Settings', 'Users.jsx'),
])
def test_used_new_keys_exist_in_uz(dicts, fname):
    src = _read(os.path.join(ADMIN, fname))
    used = set(re.findall(r"""\bt[f]?\(\s*['"]([A-Za-z0-9_.]+)['"]""", src))
    missing = sorted(k for k in used if k in NEW_KEYS and k not in dicts['uz'])
    assert not missing, f'{fname}: uz.js da yo\'q: {missing}'
    # ReceiptTab/Tariflar/Couriers o'z kalitlarini haqiqatan ishlatadi
    expected = {
        'Tariflar.jsx': {'tariff.ownerOnly'},
        'Couriers.jsx': {'courier.unlinkTelegram', 'courier.unlinked'},
        'SuperAdmin.jsx': {'superAdmin.purge.moved'},
        'Operations.jsx': {'ops.remainderFromDebt', 'ops.selectCustomerForRemainder'},
    }.get(fname, set())
    assert expected <= used, f'{fname}: {sorted(expected - used)} ishlatilmagan'


# ───────────── frontend bandlari ─────────────

@pytest.mark.parametrize('fname', [
    'Shifts.jsx', 'Customers.jsx', 'Purchases.jsx', 'Operations.jsx', 'CustomerDetail.jsx',
])
def test_wallet_balance_guarded(fname):
    """T0.5: kassir uchun balance kelmaydi — faqat w.balance !== undefined bo'lsa ko'rsatiladi."""
    src = _read(os.path.join(ADMIN, fname))
    if fname == 'Shifts.jsx':
        # smena yopish oynasi alohida komponentga ajratilgan (ShiftCloseModal.jsx)
        src += _read(os.path.join(ROOT, 'frontend', 'src', 'components', 'ShiftCloseModal.jsx'))
    lines = [ln for ln in src.splitlines() if 'fmt(w.balance)' in ln or 'fmtNum(w.balance)' in ln]
    assert lines, f'{fname}: w.balance ishlatilgan joy topilmadi'
    for ln in lines:
        assert 'w.balance !== undefined' in ln, f'{fname}: himoyasiz: {ln.strip()}'


def test_inventory_counts_print_escaped():
    """T0.19: document.write ga boradigan foydalanuvchi matni esc() orqali o'tadi (XSS)."""
    src = _read(os.path.join(ADMIN, 'InventoryCounts.jsx'))
    assert re.search(r'const esc = \(v\) => String\(v \?\? \'\'\)\.replace', src)
    for field in ('item.product_name', 'item.product_sku', 'item.variant_name', 'item.variance_reason',
                  'item.product_unit', 'count.number', 'count.warehouse_name', 'count.note'):
        # ${field ...} ko'rinishida esc'siz qolmagan
        raw = re.findall(r'\$\{\s*' + re.escape(field) + r'(?:\s*\|\|[^}]*)?\}', src)
        assert not raw, f'esc()siz: {raw}'
    assert 'esc(item.product_name)' in src and 'esc(count.warehouse_name)' in src


def test_receipt_tab_save_only_admin_director():
    """T0.19: ReceiptTab "Saqlash" tugmasi faqat admin/direktor uchun (backend 403)."""
    src = _read(os.path.join(ADMIN, 'Settings.jsx'))
    assert "import { useAuth } from '../../context/AuthContext';" in src
    i = src.index('function ReceiptTab()')
    body = src[i:i + 12000]
    assert "['admin', 'director'].includes(user?.role)" in body
    assert re.search(r'\{canSaveReceipt && \(\s*<button onClick=\{handleSave\}', body)


def test_couriers_unlink_button():
    """T0.17: tg_connected kuryer uchun "Telegramni uzish" tugmasi va POST unlink-telegram."""
    src = _read(os.path.join(ADMIN, 'Couriers.jsx'))
    assert 'api.post(`/couriers/${c.id}/unlink-telegram`)' in src
    assert re.search(r"\{c\.tg_connected && \(\s*<button onClick=\{\(\) => unlinkTelegram\(c\)\} title=\{t\('courier\.unlinkTelegram'\)\}", src)
    assert "toast.success(t('courier.unlinked'))" in src
    # muvaffaqiyatda ro'yxat yangilanadi
    i = src.index('const unlinkTelegram')
    assert 'load();' in src[i:i + 400]


def test_superadmin_moved_block():
    """T0.25: preview.moved bo'sh bo'lmasa har jadval uchun superAdmin.purge.moved ko'rsatiladi."""
    src = _read(os.path.join(ADMIN, 'SuperAdmin.jsx'))
    assert 'Object.keys(preview.moved || {}).length > 0' in src
    assert "t('superAdmin.purge.moved', { n:" in src
    assert 'Object.entries(preview.moved).map(([k, n])' in src


def test_empty_bin_loc_constant():
    src = _read(os.path.join(ADMIN, 'products', 'constants.js'))
    assert "export const emptyBinLoc = { code: '', label: '', warehouse_id: '' };" in src


# ───────────── backend: unlink-telegram izolyatsiyasi ─────────────

def _courier(db, company, chat='555000111'):
    c = Courier(company_id=company.id, name='Kuryer', phone='998901112233', tg_chat_id=chat, is_active=True)
    db.add(c)
    db.flush()
    return c


def test_unlink_telegram_own_courier(db, mk, client):
    """Ijobiy yo'l: o'z korxonasining kuryeri uzilaydi (tg_chat_id = None)."""
    company, branch, _wh, admin = mk.tenant(role=UserRole.admin)
    courier = _courier(db, company)
    r = client.login(admin).post(f'/api/couriers/{courier.id}/unlink-telegram')
    assert r.status_code == 200, r.text
    assert r.json() == {'ok': True}
    db.refresh(courier)
    assert courier.tg_chat_id is None


def test_unlink_telegram_other_company_404(db, mk, client):
    """Izolyatsiya: A korxona admini B korxona kuryerini uza olmaydi — 404, ma'lumot o'zgarmaydi."""
    company_a, _b, _w, admin_a = mk.tenant(role=UserRole.admin)
    company_b = mk.company()
    courier_b = _courier(db, company_b, chat='999')
    r = client.login(admin_a).post(f'/api/couriers/{courier_b.id}/unlink-telegram')
    assert r.status_code == 404, r.text
    db.refresh(courier_b)
    assert courier_b.tg_chat_id == '999'


def test_unlink_telegram_cashier_forbidden(db, mk, client):
    """Kassir (MANAGE_ROLES da yo'q) uchun 403."""
    company, branch, _wh, _admin = mk.tenant()
    cashier = mk.user(company, role=UserRole.cashier, branch=branch)
    courier = _courier(db, company)
    r = client.login(cashier).post(f'/api/couriers/{courier.id}/unlink-telegram')
    assert r.status_code == 403, r.text
    db.refresh(courier)
    assert courier.tg_chat_id == '555000111'
