"""Arxivlangan mijoz kassa tanlovida qolib ketmasin (2026-11-28, "Mijoz arxivlangan" xatosi sotuvda).

Sotuv sahifasi "Asosiy mijoz" yoki sessiyadan tiklangan mijozni ro'yxatda topmasa POST /customers/{id} bilan so'raydi:
javobda `is_active` bo'lishi kerak, arxivlangan bo'lsa frontend uni tanlovdan va sozlamadan olib tashlaydi.
Sotuvning o'zi arxivlangan mijozga hamon 400 (T0.26).
"""
import os

from app.models.customer import Customer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def test_single_customer_reports_is_active(client, db, mk):
    c = mk.company()
    b = mk.branch(c, is_main=True)
    u = mk.user(c, branch=b)
    cust = Customer(name="Eski mijoz", phone="998901112233", company_id=c.id)
    db.add(cust)
    db.flush()
    cl = client.login(u)
    r = cl.post(f"/api/customers/{cust.id}")
    assert r.status_code == 200 and r.json()["is_active"] is True
    cust.is_active = False
    db.flush()
    r = cl.post(f"/api/customers/{cust.id}")
    assert r.status_code == 200 and r.json()["is_active"] is False
    # ro'yxatda ko'rinmaydi
    assert all(x["id"] != cust.id for x in cl.get("/api/customers", params={"limit": 500}).json())


def test_frontend_drops_archived_customer():
    sotuv = _read('frontend/src/pages/admin/UlgurjiSotuv.jsx')
    assert "dropArchivedCustomer" in sotuv and "is_active === false" in sotuv
    assert "localStorage.removeItem('ulgurji_defaultCustomer')" in sotuv
    assert "startsWith('Mijoz arxivlangan')" in sotuv
    kassa = _read('frontend/src/pages/admin/PosKassa.jsx')
    assert "dropArchivedCustomer" in kassa and "startsWith('Mijoz arxivlangan')" in kassa
    from app.services.customer_service import ARCHIVED_DETAIL
    assert ARCHIVED_DETAIL.startswith('Mijoz arxivlangan')
    for lang in ('uz', 'ru', 'en'):
        assert _read(f'frontend/src/i18n/{lang}.js').count("'wholesale.archivedCustomerCleared':") == 1
