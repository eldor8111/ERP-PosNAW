"""D4.6 — Dorixona sahifasi (PharmacyHub): marshrut, shartli sidebar havolasi, barcha panellar ulangan; features API ikki holat."""
import json
import pathlib
import re
from datetime import datetime, timedelta, timezone

from app.models.billing import CompanyPackage

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"


def _read(rel):
    return (SRC / rel).read_text(encoding="utf-8")


def _pharmacy(db, company):
    company.pharmacy_enabled = True
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=datetime.now(timezone.utc),
                          ends_at=datetime.now(timezone.utc) + timedelta(days=30)))
    db.flush()


def test_hub_imports_all_panels_lazily():
    src = _read("pages/admin/PharmacyHub.jsx")
    for panel in ("AnalyticsPanel", "ExpiryReport", "BatchesPanel", "RecallPanel", "DefekturaPanel", "JournalsPanel"):
        assert f"lazy(() => import('./pharmacy/{panel}'))" in src, panel
        assert f"<{panel}" in src, panel
        assert (SRC / "pages" / "admin" / "pharmacy" / f"{panel}.jsx").exists()


def test_hub_remembers_tab_in_hash():
    src = _read("pages/admin/PharmacyHub.jsx")
    assert "location.hash" in src
    assert "hash: `#${key}`" in src
    for k in ("analytics", "expiry", "batches", "recall", "defektura", "journals"):
        assert f"key: '{k}'" in src


def test_route_is_gated_by_pharmacy_feature_and_roles():
    src = _read("App.jsx")
    assert "const PharmacyHub" in src and "import('./pages/admin/PharmacyHub')" in src
    m = re.search(r'<Route path="pharmacy" element=\{(.+)\} />', src)
    assert m, "pharmacy marshruti topilmadi"
    line = m.group(1)
    assert 'FeatureGate feature="pharmacy"' in line
    assert "PrivateRoute roles={PHARMACY_ROUTE_ROLES}" in line
    assert "<PharmacyHub />" in line
    assert "const PHARMACY_ROUTE_ROLES" in src


def test_sidebar_link_only_when_pharmacy_enabled():
    src = _read("components/AdminLayout.jsx")
    i = src.index("path: '/admin/pharmacy'")
    block = src[i - 120:i + 200]
    assert "feature: 'pharmacy'" in block
    assert "roles:" in block
    # havolalarni feature bo'yicha filtrlash mexanizmi mavjud (oddiy korxonada yashiriladi)
    # CD.3 dan keyin filtr isNavLinkVisible yordamchisiga ko'chdi; render shu yordamchi orqali o'tadi
    assert "if (link.feature && !features?.[link.feature]) return false;" in src
    assert "isNavLinkVisible(user, link, features)" in src


def test_ordinary_routes_unchanged():
    app = _read("App.jsx")
    # mavjud marshrutlar saqlangan
    for p in ('path="settings"', 'path="reports"', 'path="production"', 'path="filiallar"'):
        assert p in app
    layout = _read("components/AdminLayout.jsx")
    assert len(re.findall(r"^\s+feature: 'pharmacy',", layout, re.M)) == 1


def test_pending_i18n_keys_complete_and_used():
    data = json.loads((pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D4.6.json").read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"])
    src = _read("pages/admin/PharmacyHub.jsx")
    used = set(re.findall(r"'(pharmacyHub\.[A-Za-z]+)'", src))
    assert used and used <= set(data["uz"])
    assert "nav.pharmacy" in data["uz"] and "t('nav.pharmacy')" in _read("components/AdminLayout.jsx")


def test_features_api_pharmacy_company_vs_ordinary(client, db, mk):
    c_a, _, _, admin_a = mk.tenant()
    c_b, _, _, admin_b = mk.tenant()
    _pharmacy(db, c_a)
    ja = client.login(admin_a).get('/api/companies/me/features').json()
    jb = client.login(admin_b).get('/api/companies/me/features').json()
    assert ja['pharmacy'] is True
    assert jb['pharmacy'] is False  # izolyatsiya + oddiy korxona avvalgidek
