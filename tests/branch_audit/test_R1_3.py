"""R1.3 — Taom qo'shimchalari: guruhlar (min/max), variant narxi va bog'langan mahsulot, taomga biriktirish,
buyurtmada tanlovni tekshirish, narx va oshxona tiketi, to'lovda bog'langan mahsulot ombordan yechilishi,
surat (variant o'zgarsa eski chek o'zgarmaydi), ruxsatlar.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R1_3.py -q -p no:cacheprovider
"""
import os
import re
from decimal import Decimal as D

import pytest

from app.models.product import Product
from app.models.restaurant_order import KitchenTicket
from app.models.sale import SaleItem
from app.services import restaurant_orders as svc
from app.services.restaurant_menu import create_item
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"
G = "/api/restaurant/modifier-groups"


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


@pytest.fixture
def rp(db, mk):
    r = RP(db, mk)
    r.cheese = create_item(db, r.c.id, {"name": "Pishloq", "kind": "ingredient", "cost_price": 100000, "unit": "kg"})
    r.stock(r.cheese, r.kitchen, 1)
    db.flush()
    return r


def _groups(cl, rp):
    """Pishirish darajasi (majburiy 1 ta) va Qo'shimchalar (0..2, pishloq ombordan yechiladi)."""
    done = cl.post(G, json={"name": "Pishirish darajasi", "min_select": 1, "max_select": 1, "modifiers": [
        {"name": "Kam pishgan"}, {"name": "O'rtacha"}, {"name": "Yaxshi pishgan"}]})
    assert done.status_code == 201, done.text
    extra = cl.post(G, json={"name": "Qo'shimchalar", "min_select": 0, "max_select": 2, "modifiers": [
        {"name": "Pishloq", "price": 5000, "product_id": rp.cheese.id, "quantity": 0.03},
        {"name": "Sous", "price": 2000}, {"name": "Piyozsiz"}]})
    assert extra.status_code == 201, extra.text
    return done.json(), extra.json()


def _mid(group, name):
    return next(m["id"] for m in group["modifiers"] if m["name"] == name)


def test_group_crud_and_validation(rp, client):
    cl = client.login(rp.admin)
    done, extra = _groups(cl, rp)
    assert done["required"] and done["min_select"] == 1 and [m["name"] for m in done["modifiers"]] == [
        "Kam pishgan", "O'rtacha", "Yaxshi pishgan"]
    ch = next(m for m in extra["modifiers"] if m["name"] == "Pishloq")
    assert ch["price"] == 5000 and ch["product_name"] == "Pishloq" and ch["quantity"] == 0.03
    bad = [
        {"name": "", "modifiers": [{"name": "x"}]},
        {"name": "A", "min_select": 2, "max_select": 1, "modifiers": [{"name": "x"}, {"name": "y"}]},
        {"name": "A", "min_select": 2, "max_select": 2, "modifiers": [{"name": "x"}]},     # majburiy > variantlar
        {"name": "A", "modifiers": [{"name": "x", "product_id": rp.cheese.id}]},            # miqdorsiz
        {"name": "A", "modifiers": [{"name": "x", "price": -1}]},
        {"name": "A", "modifiers": [{"name": " "}]},
    ]
    for body in bad:
        assert cl.post(G, json=body).status_code == 400, body
    # tahrir: variant id bo'yicha yangilanadi, ro'yxatda yo'qlari o'chadi
    rows = [{"id": _mid(extra, "Pishloq"), "name": "Pishloq (cheddar)", "price": 6000, "product_id": rp.cheese.id,
             "quantity": 0.03}, {"name": "Ketchup", "price": 1000}]
    upd = cl.put(f"{G}/{extra['id']}", json={"modifiers": rows}).json()
    assert [m["name"] for m in upd["modifiers"]] == ["Pishloq (cheddar)", "Ketchup"]
    assert upd["modifiers"][0]["id"] == _mid(extra, "Pishloq")
    assert cl.put(f"{G}/999999", json={"name": "x"}).status_code == 404
    lst = cl.get(G).json()
    assert {g["name"] for g in lst} == {"Pishirish darajasi", "Qo'shimchalar"}


def test_attach_only_to_dish_and_menu_shows_groups(rp, client):
    cl = client.login(rp.admin)
    done, extra = _groups(cl, rp)
    r = cl.put(f"/api/restaurant/menu/items/{rp.osh.id}/modifier-groups", json={"group_ids": [done["id"], extra["id"]]})
    assert r.status_code == 200 and r.json()["modifier_group_ids"] == [done["id"], extra["id"]]
    assert cl.put(f"/api/restaurant/menu/items/{rp.cola.id}/modifier-groups",
                  json={"group_ids": [extra["id"]]}).status_code == 400
    assert cl.put(f"/api/restaurant/menu/items/{rp.osh.id}/modifier-groups",
                  json={"group_ids": [999999]}).status_code == 404
    items = {i["name"]: i for i in cl.get("/api/restaurant/menu/items", params={"kind": "dish,goods"}).json()}
    assert items["Osh"]["modifier_group_ids"] == [done["id"], extra["id"]] and items["Cola"]["modifier_group_ids"] == []
    grp = next(g for g in cl.get(G).json() if g["id"] == extra["id"])
    assert grp["product_ids"] == [rp.osh.id]


def test_order_validation_price_ticket_and_stock(rp, client, db):
    adm = client.login(rp.admin)
    done, extra = _groups(adm, rp)
    adm.put(f"/api/restaurant/menu/items/{rp.osh.id}/modifier-groups", json={"group_ids": [done["id"], extra["id"]]})
    cl = client.login(rp.cashier)
    oid = rp.open(cl)["id"]
    add = lambda mods, **kw: cl.post(f"{O}/{oid}/items", json={"items": [{"product_id": rp.osh.id, "modifiers": mods, **kw}]})
    assert add(None).status_code == 400                                            # majburiy tanlanmagan
    assert add([_mid(done, "Kam pishgan"), _mid(done, "O'rtacha")]).status_code == 400   # 1 tadan ko'p
    assert add([_mid(done, "O'rtacha"), _mid(extra, "Pishloq"), _mid(extra, "Sous"),
                _mid(extra, "Piyozsiz")]).status_code == 400                       # qo'shimchalar 2 tadan ko'p
    assert add([_mid(done, "O'rtacha"), _mid(done, "O'rtacha")]).status_code == 400  # takror
    assert cl.post(f"{O}/{oid}/items", json={"items": [{"product_id": rp.cola.id, "modifiers": [
        _mid(extra, "Sous")]}]}).status_code == 400                                 # biriktirilmagan
    r = add([_mid(done, "O'rtacha"), _mid(extra, "Pishloq")], quantity=2)
    assert r.status_code == 200, r.text
    it = r.json()["items"][0]
    assert it["modifiers_total"] == 5000 and it["amount"] == 110000
    assert [m["name"] for m in it["modifiers"]] == ["O'rtacha", "Pishloq"]
    assert r.json()["subtotal"] == 110000 and r.json()["total"] == 121000
    # qoralamada tanlovni o'zgartirish
    p = cl.patch(f"{O}/{oid}/items/{it['id']}", json={"modifiers": [_mid(done, "O'rtacha"), _mid(extra, "Pishloq"),
                                                                     _mid(extra, "Sous")]})
    assert p.status_code == 200, p.text
    assert p.json()["items"][0]["modifiers_total"] == 7000 and p.json()["subtotal"] == 114000
    assert cl.patch(f"{O}/{oid}/items/{it['id']}", json={"modifiers": []}).status_code == 400
    cl.patch(f"{O}/{oid}/items/{it['id']}", json={"modifiers": [_mid(done, "O'rtacha"), _mid(extra, "Pishloq")]})
    assert cl.post(f"{O}/{oid}/send", json={}).status_code == 200
    t = db.query(KitchenTicket).filter(KitchenTicket.order_id == oid).one()
    assert t.lines[0]["modifiers"] == ["O'rtacha", "Pishloq"]
    # variantni o'zgartirish yuborilgan chekka ta'sir qilmaydi
    adm = client.login(rp.admin)
    adm.put(f"{G}/{extra['id']}", json={"modifiers": [{"name": "Sous", "price": 2000}]})
    cl = client.login(rp.cashier)
    assert cl.get(f"{O}/{oid}").json()["items"][0]["modifiers_total"] == 5000
    res = cl.post(f"{O}/{oid}/pay", json={"payments": [{"type": "cash", "amount": 121000}]})
    assert res.status_code == 200, res.text
    sale_id = res.json()["sale"]["id"]
    osh = next(si for si in db.query(SaleItem).filter(SaleItem.sale_id == sale_id)
               if db.get(Product, si.product_id).name == "Osh")
    assert float(osh.unit_price) == 55000
    # guruch 2 x 0.15, pishloq 2 x 0.03 oshxona omboridan; tannarxga pishloq ham kiradi (3000 + 3000)
    assert rp.qty(rp.rice, rp.kitchen) == D("9.700") and rp.qty(rp.cheese, rp.kitchen) == D("0.940")
    assert osh.cost_price == D("6000.0000")
    fis = cl.get(f"{O}/{oid}/fiscal").json()
    assert fis["cart"][0]["unit_price"] == 55000


def test_delete_group_and_permissions(rp, client, mk):
    adm = client.login(rp.admin)
    done, extra = _groups(adm, rp)
    adm.put(f"/api/restaurant/menu/items/{rp.osh.id}/modifier-groups", json={"group_ids": [done["id"]]})
    assert adm.delete(f"{G}/{done['id']}").status_code == 200
    items = {i["name"]: i for i in adm.get("/api/restaurant/menu/items", params={"kind": "dish"}).json()}
    assert items["Osh"]["modifier_group_ids"] == []
    cl = client.login(rp.cashier)
    assert cl.get(G).status_code == 200
    assert cl.post(G, json={"name": "X", "modifiers": [{"name": "y"}]}).status_code == 403
    assert cl.delete(f"{G}/{extra['id']}").status_code == 403
    # boshqa korxona guruhini ko'rmaydi va o'zgartira olmaydi
    other = RP(rp.db, mk)
    oc = client.login(other.admin)
    assert oc.get(G).json() == []
    assert oc.put(f"{G}/{extra['id']}", json={"name": "x"}).status_code == 404
    assert oc.put(f"/api/restaurant/menu/items/{other.osh.id}/modifier-groups",
                  json={"group_ids": [extra["id"]]}).status_code == 404
    _, _, _, retail = mk.tenant()
    assert client.login(retail).get(G).status_code == 403


def test_frontend_modifiers_wired():
    menu = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantMenu.jsx'), encoding='utf-8').read()
    orders = open(os.path.join(ROOT, 'frontend/src/pages/admin/restaurant/RestaurantOrders.jsx'), encoding='utf-8').read()
    assert "/restaurant/modifier-groups" in menu and "/modifier-groups`" in menu
    assert "modifier_group_ids" in orders and "modifiers:" in orders
    keys = set()
    for page in (menu, orders):
        keys |= set(re.findall(r"'(restMod\.[\w.]+)'", page))
    assert keys
    for lang in ('uz', 'ru', 'en'):
        d = open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8').read()
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
