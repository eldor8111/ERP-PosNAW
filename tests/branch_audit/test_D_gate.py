"""Dorixona moduli darvozasi: oddiy korxona (modul o'chiq) /api/pharmacy/* endpointlaridan foydalana olmaydi,
dorixona korxonasida esa ular ochiq. Yangi dorixona endpointi qo'shilsa, bu test uni avtomatik qamraydi."""
import re
from datetime import datetime, timedelta, timezone

from app.main import app
from app.models.billing import CompanyPackage


def _pharmacy_routes():
    """OpenAPI sxemasidan /api/pharmacy/* yo'llari (FastAPI ulangan routerlarni ichma-ich saqlaydi,
    shuning uchun app.routes ni to'g'ridan-to'g'ri sanab bo'lmaydi)."""
    app.openapi_schema = None
    paths = app.openapi().get("paths", {})
    out = []
    for path, ops in paths.items():
        if not path.startswith("/api/pharmacy"):
            continue
        for m in ops:
            if m.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                out.append((m.upper(), re.sub(r"\{[^}]+\}", "1", path)))
    return sorted(set(out))


def _enable(db, c):
    c.pharmacy_enabled = True
    db.add(CompanyPackage(company_id=c.id, package_code="pharmacy", is_active=True,
                          starts_at=datetime.now(timezone.utc),
                          ends_at=datetime.now(timezone.utc) + timedelta(days=30)))
    db.flush()


def test_pharmacy_routes_exist():
    routes = _pharmacy_routes()
    prefixes = {p.split("/")[3] for _, p in routes}
    # katalog, birliklar, markirovka, partiyalar, hisobotlar, qaytarib olish, defektura, jurnallar, tahlil
    assert len(routes) >= 15, routes
    assert {"substances", "marking", "batches", "reports", "recall", "journals", "analytics"} <= prefixes or len(prefixes) >= 6


def test_ordinary_company_cannot_use_any_pharmacy_endpoint(client, db, mk):
    c, _, _, admin = mk.tenant()
    cl = client.login(admin)
    opened = []
    for method, path in _pharmacy_routes():
        r = cl.request(method, path, json={})
        if 200 <= r.status_code < 300:
            opened.append((method, path, r.status_code))
    assert opened == [], f"Modul o'chiq korxonada ochiq qolgan endpointlar: {opened}"


def test_pharmacy_company_can_read_pharmacy_endpoints(client, db, mk):
    c, _, _, admin = mk.tenant()
    _enable(db, c)
    cl = client.login(admin)
    for path in ("/api/pharmacy/substances", "/api/pharmacy/batches"):
        r = cl.get(path)
        assert r.status_code == 200, (path, r.status_code, r.text[:200])


def test_expired_package_closes_endpoints(client, db, mk):
    c, _, _, admin = mk.tenant()
    c.pharmacy_enabled = True
    db.add(CompanyPackage(company_id=c.id, package_code="pharmacy", is_active=True,
                          starts_at=datetime.now(timezone.utc) - timedelta(days=40),
                          ends_at=datetime.now(timezone.utc) - timedelta(days=10)))
    db.flush()
    r = client.login(admin).get("/api/pharmacy/substances")
    assert not (200 <= r.status_code < 300)
