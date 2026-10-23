"""D1.1b — Dorixona sozlamalari UI va paket kartasi (fayl-matn testlari + API shartnomasi)."""
import json
import pathlib
import re
from datetime import datetime, timedelta, timezone

from app.models.billing import CompanyPackage
from app.services.pharmacy import DEFAULT_SETTINGS, PRICE_ROUND_STEPS

ROOT = pathlib.Path(__file__).resolve().parents[2]
FE = ROOT / 'frontend' / 'src'


def _read(rel):
    return (FE / rel).read_text(encoding='utf-8')


def _package(db, company, days=30):
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=datetime.now(timezone.utc),
                          ends_at=datetime.now(timezone.utc) + timedelta(days=days)))
    db.flush()


# ── Settings.jsx ────────────────────────────────────────────────────────────
def test_settings_has_pharmacy_toggle():
    src = _read('pages/admin/Settings.jsx')
    assert "key: 'pharmacy'" in src
    assert "column: 'pharmacy_enabled'" in src
    # tumbler mavjud toggle() orqali PUT /companies/{id} yuboradi, xato detail ko'rsatiladi
    assert "api.put(`/companies/${companyId}`, { [column]: value })" in src
    assert "e.response?.data?.detail" in src


def test_settings_pharmacy_card_has_all_keys_and_save_shape():
    src = _read('pages/admin/Settings.jsx')
    m = re.search(r'function PharmacySettingsCard.*?\n}\n', src, re.S)
    assert m, 'PharmacySettingsCard topilmadi'
    card = m.group(0)
    for key in DEFAULT_SETTINGS:
        assert key in src, key
    assert "pharmacy_settings: body" in card
    assert "refreshCompanyFeatures" in card
    # yaxlitlash qadamlari serverdagi bilan bir xil
    steps = re.search(r'PHARMACY_ROUND_STEPS = \[([^\]]*)\]', src).group(1)
    assert tuple(int(x) for x in steps.split(',')) == PRICE_ROUND_STEPS
    # rx_mode ikki qiymat
    assert 'value="warn"' in card and 'value="block"' in card
    # server tekshiruv xabari (400 detail) ko'rsatiladi
    assert "e.response?.data?.detail" in card


def test_pharmacy_card_only_when_module_enabled():
    src = _read('pages/admin/Settings.jsx')
    assert "{features?.pharmacy && <PharmacySettingsCard companyId={companyId} />}" in src
    # oddiy korxona: ModulesCard va LoyaltyCard avvalgidek turadi
    assert "<ModulesCard companyId={companyId} />" in src
    assert "<LoyaltyCard companyId={companyId} />" in src


# ── useCompanyFeatures.js ───────────────────────────────────────────────────
def test_hook_returns_pharmacy():
    src = _read('hooks/useCompanyFeatures.js')
    assert 'pharmacy:' in src and 'pharmacy_settings' in src
    # mavjud keshlash saqlangan
    assert 'let cache = null' in src and 'inflight' in src and 'export function refreshCompanyFeatures' in src
    # xato holatida ham dorixona o'chiq
    assert re.search(r'catch\(\(\) => \{ cache = \{[^}]*pharmacy: false', src)


# ── Tariflar.jsx / SuperAdmin.jsx ───────────────────────────────────────────
def test_tariflar_does_not_exclude_pharmacy_and_has_icon():
    src = _read('pages/admin/Tariflar.jsx')
    assert "code === 'pharmacy'" in src and 'Pill' in src
    # paketlar serverdan keladi, kod bo'yicha filtr yo'q (narx serverdan: BHM 25%)
    body = src[src.index('function PaketlarTab'):]
    body = body[:body.index('export default function Tariflar')]
    assert '.filter(' not in body
    assert 'packages.map(' in body and 'pkg.price_per_month' in body and 'pkg.bhm_percent' in body


def test_superadmin_packages_know_pharmacy():
    src = _read('pages/admin/SuperAdmin.jsx')
    assert re.search(r"PKG_ICONS = \{[^}]*pharmacy:", src, re.S)
    assert re.search(r"PKG_COLORS = \{.*?pharmacy:", src, re.S)
    # ro'yxat serverdan (/billing/packages) — qattiq kodlangan ro'yxat yo'q
    assert "api.get('/billing/packages')" in src


# ── i18n pending ────────────────────────────────────────────────────────────
def test_i18n_pending_file_complete():
    data = json.loads((pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D1.1b.json").read_text(encoding='utf-8'))
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    src = _read('pages/admin/Settings.jsx')
    used = set(re.findall(r"tf\('((?:settings|features)\.pharmacy\.[A-Za-z.]+)'", src))
    assert len(used) >= 15
    assert used <= set(data['uz']), used - set(data['uz'])
    # kalitlar umumiy lug'atlarga birlashtirilgan (D-bosqich yakuniy integratsiyasi)
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'i18n/{lang}.js')
        for k in data[lang]:
            assert f"'{k}'" in d or f'"{k}"' in d, (lang, k)


# ── API shartnomasi: oddiy korxona va dorixona ──────────────────────────────
def test_features_api_ordinary_company_regression(client, db, mk):
    c, _, _, admin = mk.tenant()
    r = client.login(admin).get('/api/companies/me/features')
    assert r.status_code == 200
    j = r.json()
    assert j['pharmacy'] is False
    assert j['pharmacy_settings'] == DEFAULT_SETTINGS
    assert j['manufacturing'] is False and j['distribution'] is False


def test_features_api_pharmacy_company_and_isolation(client, db, mk):
    a, _, _, admin_a = mk.tenant()
    b, _, _, admin_b = mk.tenant()
    _package(db, a)
    cl = client.login(admin_a)
    assert cl.put(f'/api/companies/{a.id}', json={'pharmacy_enabled': True}).status_code == 200
    r = cl.put(f'/api/companies/{a.id}', json={'pharmacy_settings': {
        'expiry_block_days': 14, 'rx_mode': 'block', 'price_round': 500, 'markup_pct': 20}})
    assert r.status_code == 200, r.text
    j = cl.get('/api/companies/me/features').json()
    assert j['pharmacy'] is True
    assert j['pharmacy_settings']['expiry_block_days'] == 14
    assert j['pharmacy_settings']['rx_mode'] == 'block'
    assert j['pharmacy_settings']['price_round'] == 500
    # noto'g'ri qiymat — serverdan 400 va o'zbekcha detail (UI shuni ko'rsatadi)
    bad = cl.put(f'/api/companies/{a.id}', json={'pharmacy_settings': {'price_round': 7}})
    assert bad.status_code == 400 and bad.json()['detail']
    # B korxona o'zgarmagan; A foydalanuvchisi B ni o'zgartira olmaydi
    assert client.login(admin_b).get('/api/companies/me/features').json()['pharmacy'] is False
    r = client.login(admin_a).put(f'/api/companies/{b.id}', json={'pharmacy_settings': {'rx_mode': 'block'}})
    assert r.status_code in (403, 404)
    assert client.login(admin_b).get('/api/companies/me/features').json()['pharmacy_settings'] == DEFAULT_SETTINGS


def test_enable_without_package_gives_purchase_message(client, db, mk):
    c, _, _, admin = mk.tenant()
    r = client.login(admin).put(f'/api/companies/{c.id}', json={'pharmacy_enabled': True})
    assert r.status_code == 403
    assert 'Tariflar' in r.json()['detail']
