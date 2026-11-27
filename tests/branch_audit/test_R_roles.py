"""Restoran rollari: tayyor rollar (Ofitsiant, Oshpaz, Kassir, Zal menejeri) avtomatik va tugma bilan yaratiladi,
takroriy xavfsiz, rol ruxsatlari xodimga ta'sir qiladi (ofitsiant faqat o'z stoli, oshpaz faqat oshxona),
rollar sahifasida "Restoran" bo'limi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R_roles.py -q -p no:cacheprovider
"""
import os
import re

from app.models.role import Role
from app.models.user import UserRole
from app.services.restaurant import ROLE_TEMPLATES
from tests.branch_audit.test_R3 import R

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"


def _roles(db, company_id):
    return {r.name: r for r in db.query(Role).filter(Role.company_id == company_id)}


def test_provision_creates_roles_and_button_is_idempotent(db, mk, client):
    r = R(db, mk)
    roles = _roles(db, r.c.id)
    assert set(ROLE_TEMPLATES) <= set(roles)
    assert roles["Ofitsiant"].permissions["restaurant"]["waiter"] is True
    assert roles["Zal menejeri"].permissions["restaurant"]["discount_max"] == 20
    roles["Ofitsiant"].permissions = {"restaurant": {"orders": True, "waiter": True, "all_tables": True}}
    db.delete(roles["Oshpaz"])
    db.flush()
    cl = client.login(r.admin)
    res = cl.post("/api/restaurant/roles/defaults")
    assert res.status_code == 200 and res.json() == {"created": 1}
    again = _roles(db, r.c.id)
    assert again["Ofitsiant"].permissions["restaurant"]["all_tables"] is True      # mavjud rolga tegilmadi
    assert cl.post("/api/restaurant/roles/defaults").json() == {"created": 0}
    assert set(cl.get("/api/restaurant/roles/templates").json()) == set(ROLE_TEMPLATES)


def test_defaults_button_admin_only_and_restaurant_only(db, mk, client):
    r = R(db, mk)
    assert client.login(r.cashier).post("/api/restaurant/roles/defaults").status_code == 403
    _, _, _, retail = mk.tenant()
    assert client.login(retail).post("/api/restaurant/roles/defaults").status_code == 403


def test_role_permissions_apply_to_staff(db, mk, client):
    r = R(db, mk)
    roles = _roles(db, r.c.id)
    waiter = mk.user(r.c, role=UserRole.cashier, branch=r.b, role_id=roles["Ofitsiant"].id)
    cook = mk.user(r.c, role=UserRole.cashier, branch=r.b, role_id=roles["Oshpaz"].id)
    db.refresh(waiter)
    db.refresh(cook)
    other = r.open(client.login(r.cashier), 0)
    wcl = client.login(waiter)
    perms = wcl.get("/api/restaurant/me/perms").json()
    assert perms["waiter"] is True and perms["all_tables"] is False and perms["take_payment"] is False
    assert wcl.get(f"{O}/{other['id']}").status_code == 403                   # boshqa ofitsiant cheki
    mine = r.open(wcl, 1)["id"]
    r.add(wcl, mine, {"product_id": r.cola.id})
    wcl.post(f"{O}/{mine}/send", json={})
    assert wcl.post(f"{O}/{mine}/pay", json={"payments": [{"type": "cash", "amount": 11000}]}).status_code == 403
    ccl = client.login(cook)
    assert ccl.post(O, json={"table_id": r.tables[3].id}).status_code == 403      # oshpaz chek ochmaydi
    assert ccl.get("/api/restaurant/kds", params={"branch_id": r.b.id}).status_code == 200


def test_frontend_roles_section():
    page = open(os.path.join(ROOT, 'frontend/src/pages/admin/Settings/Roles.jsx'), encoding='utf-8').read()
    for token in ("/restaurant/roles/templates", "/restaurant/roles/defaults", "discount_max", "features?.restaurant"):
        assert token in page, token
    keys = set(re.findall(r"tf\('(roles\.rest[\w.]*)'", page))
    assert len(keys) >= 7
    flags = ('orders', 'waiter', 'all_tables', 'take_payment', 'move_table', 'kitchen', 'cancel_sent', 'unlock_precheck')
    keys |= {f'roles.rest.{f}' for f in flags} | {f'roles.restDesc.{f}' for f in flags}   # tf(`roles.rest.${key}`)
    for lang in ('uz', 'ru', 'en'):
        d = open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8').read()
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
