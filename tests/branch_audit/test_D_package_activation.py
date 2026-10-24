"""Paket sotib olinganda / super admin berganda modul bayrog'i yoqiladi (Dorixona ham).

Xato: avval faqat manufacturing/distribution/delivery_automation qo'lda sanalgan edi — "Dorixona" paketi
sotib olinsa ham companies.pharmacy_enabled=False qolib, modul ochilmasdi."""
import pathlib

import pytest

from app.models.billing import FeaturePackage
from app.models.company import Company
from app.models.user import UserRole
from app.services.pharmacy import pharmacy_enabled

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _pkg(db, code, bhm=25.0, price=110000):
    if not db.query(FeaturePackage).filter(FeaturePackage.code == code).first():
        db.add(FeaturePackage(code=code, name=code, bhm_percent=bhm, price_per_month=price, is_active=True))
        db.flush()


def test_subscribe_pharmacy_package_enables_module(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pkg(db, "pharmacy")
    c.balance = 1_000_000
    db.flush()
    assert pharmacy_enabled(db, c.id) is False
    r = client.login(admin).post('/api/billing/my-company/packages/subscribe',
                                 json={"package_code": "pharmacy", "months": 1})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Company, c.id).pharmacy_enabled is True
    assert pharmacy_enabled(db, c.id) is True
    assert client.login(admin).get('/api/companies/me/features').json()['pharmacy'] is True


def test_super_admin_grant_pharmacy_enables_module(client, db, mk):
    c, _, _, _ = mk.tenant()
    _pkg(db, "pharmacy")
    sa = mk.user(c, role=UserRole.super_admin)
    r = client.login(sa).post(f'/api/billing/companies/{c.id}/packages/grant',
                              json={"package_code": "pharmacy", "days": 30})
    assert r.status_code in (200, 201), r.text
    db.expire_all()
    assert db.get(Company, c.id).pharmacy_enabled is True
    assert pharmacy_enabled(db, c.id) is True


@pytest.mark.parametrize("code,column", [
    ("manufacturing", "manufacturing_enabled"),
    ("distribution", "distribution_enabled"),
    ("delivery_automation", "orders_auto_create_sale"),
])
def test_existing_packages_still_enable_their_flag(client, db, mk, code, column):
    c, _, _, admin = mk.tenant()
    _pkg(db, code)
    c.balance = 1_000_000
    db.flush()
    r = client.login(admin).post('/api/billing/my-company/packages/subscribe',
                                 json={"package_code": code, "months": 1})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert getattr(db.get(Company, c.id), column) is True
    assert db.get(Company, c.id).pharmacy_enabled is False   # boshqa paket dorixonani yoqmaydi


def test_auto_migrations_cover_pharmacy_columns_on_existing_tables():
    src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    for stmt in (
        "ALTER TABLE batches ADD COLUMN IF NOT EXISTS status VARCHAR(20)",
        "ALTER TABLE categories ADD COLUMN IF NOT EXISTS markup_pct",
        "ALTER TABLE po_items ADD COLUMN IF NOT EXISTS lot_number",
        "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS supplier_invoice_number",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS pharmacy_enabled",
    ):
        assert stmt in src, stmt


# ─── Super admin: tarif obunasini faollashtirish ─────────────────────────────

def _tariff(db, **kw):
    from app.models.billing import Tariff
    t = Tariff(name=kw.pop("name", "Boshlang'ich"), price_per_month=kw.pop("price", 100000), duration_days=30,
               max_users=10, max_branches=3, max_warehouses=3, is_active=True, **kw)
    db.add(t)
    db.flush()
    return t


def test_super_admin_activate_subscription(client, db, mk):
    c, _, _, _ = mk.tenant()
    t = _tariff(db)
    c.balance = 10_000_000
    db.flush()
    sa = mk.user(c, role=UserRole.super_admin)
    r = client.login(sa).post(f'/api/billing/companies/{c.id}/subscribe', json={"tariff_id": t.id, "months": 1})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Company, c.id).tariff_id == t.id


def test_tariff_subscribe_keeps_purchased_module_package(client, db, mk):
    """Tarifda ishlab chiqarish yo'q, lekin alohida paket sotib olingan — tarif faollashganda modul o'chmasin."""
    from datetime import datetime, timedelta, timezone
    from app.models.billing import CompanyPackage
    c, _, _, admin = mk.tenant()
    t = _tariff(db, has_manufacturing=False, has_distribution=False)
    c.balance = 10_000_000
    c.manufacturing_enabled = True
    c.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    for code in ("manufacturing", "pharmacy"):
        db.add(CompanyPackage(company_id=c.id, package_code=code, is_active=True,
                              starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()
    sa = mk.user(c, role=UserRole.super_admin)
    r = client.login(sa).post(f'/api/billing/companies/{c.id}/subscribe', json={"tariff_id": t.id, "months": 1})
    assert r.status_code == 200, r.text
    db.expire_all()
    comp = db.get(Company, c.id)
    assert comp.manufacturing_enabled is True      # paket faol — o'chmadi
    assert comp.distribution_enabled is False      # paket ham, tarif ham yo'q
    assert comp.pharmacy_enabled is True           # tarif obunasi dorixonaga tegmaydi
    assert pharmacy_enabled(db, c.id) is True


def test_tariff_subscribe_without_package_follows_tariff(client, db, mk):
    c, _, _, _ = mk.tenant()
    t = _tariff(db, has_manufacturing=True, has_distribution=False)
    c.balance = 10_000_000
    c.distribution_enabled = True                  # paket yo'q — tarifga moslanadi
    db.flush()
    sa = mk.user(c, role=UserRole.super_admin)
    r = client.login(sa).post(f'/api/billing/companies/{c.id}/subscribe', json={"tariff_id": t.id, "months": 1})
    assert r.status_code == 200, r.text
    db.expire_all()
    comp = db.get(Company, c.id)
    assert comp.manufacturing_enabled is True and comp.distribution_enabled is False
