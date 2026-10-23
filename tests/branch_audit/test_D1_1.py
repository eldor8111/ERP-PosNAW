"""D1.1 — Dorixona moduli: bayroq, paket (BHM 25%), sozlamalar va oddiy do'konga ta'sir yo'qligi."""
import ast
import pathlib
from datetime import datetime, timedelta, timezone

from app.models.billing import CompanyPackage, FeaturePackage
from app.models.company import Company
from app.services.pharmacy import (
    DEFAULT_SETTINGS, get_pharmacy_settings, pharmacy_context, pharmacy_enabled,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _package(db, company, days=30):
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=datetime.now(timezone.utc),
                          ends_at=datetime.now(timezone.utc) + timedelta(days=days)))
    db.flush()


def test_default_company_is_not_pharmacy(client, db, mk):
    c, _, _, admin = mk.tenant()
    assert pharmacy_enabled(db, c.id) is False
    enabled, settings = pharmacy_context(db, c.id)
    assert enabled is False and settings == DEFAULT_SETTINGS
    r = client.login(admin).get('/api/companies/me/features')
    assert r.status_code == 200
    assert r.json()['pharmacy'] is False


def test_enable_requires_package(client, db, mk):
    c, _, _, admin = mk.tenant()
    cl = client.login(admin)
    r = cl.put(f'/api/companies/{c.id}', json={'pharmacy_enabled': True})
    assert r.status_code == 403
    assert db.get(Company, c.id).pharmacy_enabled is False
    _package(db, c)
    r = cl.put(f'/api/companies/{c.id}', json={'pharmacy_enabled': True})
    assert r.status_code == 200, r.text
    assert r.json()['pharmacy_enabled'] is True
    assert pharmacy_enabled(db, c.id) is True
    assert cl.get('/api/companies/me/features').json()['pharmacy'] is True
    # qayta saqlash (forma) va o'chirish doim mumkin
    assert cl.put(f'/api/companies/{c.id}', json={'pharmacy_enabled': True}).status_code == 200
    assert cl.put(f'/api/companies/{c.id}', json={'pharmacy_enabled': False}).status_code == 200


def test_expired_package_disables_module(client, db, mk):
    c, _, _, admin = mk.tenant()
    c.pharmacy_enabled = True
    db.add(CompanyPackage(company_id=c.id, package_code="pharmacy", is_active=True,
                          starts_at=datetime.now(timezone.utc) - timedelta(days=40),
                          ends_at=datetime.now(timezone.utc) - timedelta(days=10)))
    db.flush()
    assert pharmacy_enabled(db, c.id) is False


def test_settings_validation_and_merge(client, db, mk):
    c, _, _, admin = mk.tenant()
    _package(db, c)
    cl = client.login(admin)
    assert cl.put(f'/api/companies/{c.id}', json={'pharmacy_settings': {'rx_mode': 'x'}}).status_code == 400
    assert cl.put(f'/api/companies/{c.id}', json={'pharmacy_settings': {'expiry_block_days': 999}}).status_code == 400
    r = cl.put(f'/api/companies/{c.id}', json={'pharmacy_enabled': True,
                                                'pharmacy_settings': {'expiry_block_days': 7, 'rx_mode': 'block'}})
    assert r.status_code == 200, r.text
    s = r.json()['pharmacy_settings']
    assert s['expiry_block_days'] == 7 and s['rx_mode'] == 'block'
    assert s['expiry_warn_days'] == DEFAULT_SETTINGS['expiry_warn_days']
    # qisman yangilash boshqa kalitlarni saqlaydi
    r = cl.put(f'/api/companies/{c.id}', json={'pharmacy_settings': {'expiry_warn_days': 45}})
    s = r.json()['pharmacy_settings']
    assert s['expiry_block_days'] == 7 and s['expiry_warn_days'] == 45
    assert get_pharmacy_settings(db, c.id)['rx_mode'] == 'block'


def test_other_company_cannot_change_pharmacy(client, db, mk):
    a, _, _, admin_a = mk.tenant()
    b, _, _, _ = mk.tenant()
    _package(db, b)
    r = client.login(admin_a).put(f'/api/companies/{b.id}', json={'pharmacy_enabled': True})
    assert r.status_code in (403, 404)
    assert db.get(Company, b.id).pharmacy_enabled is False


def test_package_price_is_bhm_25_percent(client, db, mk):
    c, _, _, admin = mk.tenant()
    db.add(FeaturePackage(code="pharmacy", name="Dorixona", bhm_percent=25.0, price_per_month=110000,
                          is_active=True, sort_order=4))
    db.flush()
    r = client.login(admin).get('/api/billing/packages')
    assert r.status_code == 200, r.text
    pkg = [p for p in r.json() if p['code'] == 'pharmacy'][0]
    assert pkg['bhm_percent'] == 25.0
    assert pkg['price_per_month'] in (110000, 110000.0)          # standart BHM 440 000 ning 25 foizi


def test_default_package_seed_has_pharmacy_bhm_25():
    src = (ROOT / 'app' / 'main.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_seed_default_feature_packages'][0]
    pkgs = [ast.literal_eval(d) for d in ast.walk(fn) if isinstance(d, ast.Dict)
            and any(isinstance(k, ast.Constant) and k.value == 'code' for k in d.keys)]
    ph = [p for p in pkgs if p['code'] == 'pharmacy'][0]
    assert ph['bhm_percent'] == 25.0 and ph['price_per_month'] == 110000


def test_migration_chained_to_previous_head():
    src = (ROOT / 'alembic' / 'versions' / 't6_01_pharmacy_module.py').read_text(encoding='utf-8')
    assert "down_revision: Union[str, Sequence[str], None] = 't5_02_protect_content'" in src
