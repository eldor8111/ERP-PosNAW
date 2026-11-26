"""R1 — Restoran menyusi: mahsulot turlari, texnologik kartalar (versiya, tannarx, food cost), sexlar.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R1.py -q -p no:cacheprovider
"""
import os
from decimal import Decimal

import pytest

from app.models.bom import BOM, BOMItem
from app.models.category import Category
from app.models.currency import Currency
from app.models.product import Product
from app.models.restaurant import KitchenStation
from app.models.user import UserRole
from app.services.restaurant import provision_restaurant, settings_for_format

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
URL = "/api/restaurant/menu/items"


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _rest(db, mk):
    c = mk.company(business_type="restaurant", restaurant_settings=settings_for_format("full_service"))
    b = mk.branch(c, is_main=True)
    u = mk.user(c, branch=b)
    provision_restaurant(db, c, b)
    return c, b, u


def _item(cl, **kw):
    r = cl.post(URL, json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def _card(cl, item_id, items, **kw):
    return cl.put(f"{URL}/{item_id}/card", json={"items": items, **kw})


# ───────────────────────── R1.1 turlar ─────────────────────────

def test_create_kinds_and_defaults(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    dish = _item(cl, name="Osh", kind="dish", sale_price=45000)
    meat = _item(cl, name="Mol go'shti", kind="ingredient", cost_price=120000)
    cola = _item(cl, name="Coca-Cola 0.5", kind="goods", sale_price=8000, barcode="4870001234567")
    assert dish["unit"] == "porsiya" and meat["unit"] == "kg" and cola["unit"] == "dona"
    assert cola["barcode"] == "4870001234567"
    pd = db.get(Product, dish["id"])
    assert pd.item_kind == "dish" and pd.product_type == "service" and pd.company_id == c.id
    assert pd.barcode and pd.sku.startswith("RM-")
    assert db.get(Product, meat["id"]).product_type == "simple"
    # takroriy shtrix-kod
    assert cl.post(URL, json={"name": "X", "kind": "goods", "barcode": "4870001234567"}).status_code == 409
    # noto'g'ri tur va birlik
    assert cl.post(URL, json={"name": "X", "kind": "pizza"}).status_code == 400
    assert cl.post(URL, json={"name": "X", "kind": "dish", "unit": "quti"}).status_code == 400
    assert cl.post(URL, json={"name": "  ", "kind": "dish"}).status_code == 400


def test_list_filters_by_kind_and_search(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    _item(cl, name="Osh", kind="dish")
    _item(cl, name="Lag'mon", kind="dish")
    _item(cl, name="Guruch", kind="ingredient")
    names = [x["name"] for x in cl.get(URL, params={"kind": "dish"}).json()]
    assert names == ["Lag'mon", "Osh"]
    assert [x["name"] for x in cl.get(URL, params={"kind": "dish,ingredient", "q": "gur"}).json()] == ["Guruch"]
    assert cl.get(URL, params={"kind": "bad"}).status_code == 400


def test_retail_company_gets_403(db, mk, client):
    _, _, _, u = mk.tenant()
    cl = client.login(u)
    assert cl.get(URL).status_code == 403
    assert cl.post(URL, json={"name": "Osh", "kind": "dish"}).status_code == 403
    assert cl.get("/api/restaurant/stations").status_code == 403


def test_warehouse_role_limits(db, mk, client):
    c, b, _ = _rest(db, mk)
    wh = mk.user(c, role=UserRole.warehouse, branch=b)
    cl = client.login(wh)
    assert cl.post(URL, json={"name": "Un", "kind": "ingredient"}).status_code == 201
    assert cl.post(URL, json={"name": "Osh", "kind": "dish"}).status_code == 403
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    assert client.login(cashier).post(URL, json={"name": "Un2", "kind": "ingredient"}).status_code == 403
    assert client.login(cashier).get(URL).status_code == 200


def test_company_isolation(db, mk, client):
    c1, b1, u1 = _rest(db, mk)
    c2, b2, u2 = _rest(db, mk)
    meat = _item(client.login(u1), name="Go'sht", kind="ingredient", cost_price=100000)
    cl2 = client.login(u2)
    dish2 = _item(cl2, name="Kabob", kind="dish")
    assert cl2.get(f"{URL}/{meat['id']}/card").status_code == 404
    assert cl2.put(f"{URL}/{meat['id']}", json={"name": "X"}).status_code == 404
    # boshqa korxona ingredienti kartaga qo'shilmaydi
    r = _card(cl2, dish2["id"], [{"component_product_id": meat["id"], "gross_qty": 0.2}])
    assert r.status_code == 400
    assert meat["id"] not in {x["id"] for x in cl2.get(URL).json()}


# ───────────────────────── R1.2 tex karta ─────────────────────────

def test_card_cost_food_cost_and_quantity_per_unit(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    dish = _item(cl, name="Osh", kind="dish", sale_price=50000)
    rice = _item(cl, name="Guruch", kind="ingredient", cost_price=20000)    # 1 kg
    meat = _item(cl, name="Go'sht", kind="ingredient", cost_price=120000)   # 1 kg
    r = _card(cl, dish["id"], [
        {"component_product_id": rice["id"], "gross_qty": 0.15, "net_qty": 0.15},
        {"component_product_id": meat["id"], "gross_qty": 0.1, "net_qty": 0.08, "loss_cold_pct": 20},
    ], output_weight_g=350, cooking_time_min=20)
    assert r.status_code == 200, r.text
    d = r.json()
    # 0.15*20000 + 0.1*120000 = 3000 + 12000 = 15000; food cost 15000/50000 = 30%
    assert d["total_cost"] == 15000 and d["unit_cost"] == 15000 and d["food_cost_pct"] == 30.0
    assert d["card"]["version"] == 1 and d["card"]["output_weight_g"] == 350 and d["card"]["cooking_time_min"] == 20
    lines = {x["name"]: x for x in d["card"]["items"]}
    assert lines["Go'sht"]["line_cost"] == 12000 and lines["Go'sht"]["net_qty"] == 0.08
    bom = db.query(BOM).filter(BOM.product_id == dish["id"], BOM.is_active == True).one()  # noqa: E712
    assert {i.component_product_id: i.quantity_per_unit for i in bom.items}[meat["id"]] == Decimal("0.1000")
    listed = {x["id"]: x for x in cl.get(URL, params={"kind": "dish"}).json()}
    assert listed[dish["id"]]["has_card"] is True and listed[dish["id"]]["food_cost_pct"] == 30.0


def test_semi_finished_nested_cost_and_output_qty(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    meat = _item(cl, name="Go'sht", kind="ingredient", cost_price=100000)
    onion = _item(cl, name="Piyoz", kind="ingredient", cost_price=5000)
    mince = _item(cl, name="Qiyma", kind="semi")
    # 5 kg qiyma: 4.5 kg go'sht + 1 kg piyoz = 450000 + 5000 = 455000 -> 91000 / kg
    r = _card(cl, mince["id"], [{"component_product_id": meat["id"], "gross_qty": 4.5},
                                {"component_product_id": onion["id"], "gross_qty": 1}], output_qty=5)
    assert r.status_code == 200, r.text
    assert r.json()["unit_cost"] == 91000 and r.json()["food_cost_pct"] is None
    bom = db.query(BOM).filter(BOM.product_id == mince["id"], BOM.is_active == True).one()  # noqa: E712
    assert {i.component_product_id: i.quantity_per_unit for i in bom.items}[meat["id"]] == Decimal("0.9000")
    dish = _item(cl, name="Manti", kind="dish", sale_price=36400)
    r = _card(cl, dish["id"], [{"component_product_id": mince["id"], "gross_qty": 0.2}])
    # 0.2 * 91000 = 18200 -> 50%
    assert r.json()["unit_cost"] == 18200 and r.json()["food_cost_pct"] == 50.0


def test_new_version_keeps_history(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    dish = _item(cl, name="Osh", kind="dish", sale_price=50000)
    rice = _item(cl, name="Guruch", kind="ingredient", cost_price=20000)
    assert _card(cl, dish["id"], [{"component_product_id": rice["id"], "gross_qty": 0.15}]).status_code == 200
    r = _card(cl, dish["id"], [{"component_product_id": rice["id"], "gross_qty": 0.2}])
    assert r.json()["card"]["version"] == 2
    boms = db.query(BOM).filter(BOM.product_id == dish["id"]).order_by(BOM.id).all()
    assert [x.is_active for x in boms] == [False, True]
    versions = cl.get(f"{URL}/{dish['id']}/card/versions").json()
    assert [(v["card"]["version"], v["is_active"]) for v in versions] == [(2, True), (1, False)]


@pytest.mark.parametrize("bad", [
    [],
    [{"component_product_id": "R", "gross_qty": 0}],
    [{"component_product_id": "R", "gross_qty": 0.1, "net_qty": 0.2}],
    [{"component_product_id": "R", "gross_qty": 0.1, "loss_hot_pct": 100}],
    [{"component_product_id": "R", "gross_qty": 0.1}, {"component_product_id": "R", "gross_qty": 0.2}],
    [{"component_product_id": "D", "gross_qty": 0.1}],
])
def test_card_validation(db, mk, client, bad):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    dish = _item(cl, name="Osh", kind="dish")
    other = _item(cl, name="Somsa", kind="dish")
    rice = _item(cl, name="Guruch", kind="ingredient")
    ids = {"R": rice["id"], "D": other["id"]}
    rows = [{**x, "component_product_id": ids[x["component_product_id"]]} for x in bad]
    assert _card(cl, dish["id"], rows).status_code == 400
    assert db.query(BOM).filter(BOM.product_id == dish["id"]).count() == 0


def test_card_cycle_rejected_and_card_only_for_dish_or_semi(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    a = _item(cl, name="Sous A", kind="semi")
    bb = _item(cl, name="Sous B", kind="semi")
    rice = _item(cl, name="Guruch", kind="ingredient")
    assert _card(cl, a["id"], [{"component_product_id": bb["id"], "gross_qty": 1}]).status_code == 200
    r = _card(cl, bb["id"], [{"component_product_id": a["id"], "gross_qty": 1}])
    assert r.status_code == 400 and "aylana" in r.json()["detail"]
    assert _card(cl, a["id"], [{"component_product_id": a["id"], "gross_qty": 1}]).status_code == 400
    assert _card(cl, rice["id"], [{"component_product_id": a["id"], "gross_qty": 1}]).status_code == 400


def test_foreign_currency_cost_converted(db, mk, client):
    c, b, u = _rest(db, mk)
    db.add(Currency(name="Dollar", code="USD", rate=12500, company_id=c.id, is_active=True))
    db.flush()
    cl = client.login(u)
    dish = _item(cl, name="Steyk", kind="dish", sale_price=250000)
    beef = _item(cl, name="Mramor go'sht", kind="ingredient")
    p = db.get(Product, beef["id"])
    p.cost_price, p.cost_currency = Decimal("20"), "USD"     # 20$ / kg = 250 000 so'm
    db.flush()
    r = _card(cl, dish["id"], [{"component_product_id": beef["id"], "gross_qty": 0.3}])
    assert r.json()["unit_cost"] == 75000 and r.json()["food_cost_pct"] == 30.0


def test_delete_blocked_when_used_and_kind_change_guard(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    dish = _item(cl, name="Osh", kind="dish")
    rice = _item(cl, name="Guruch", kind="ingredient")
    _card(cl, dish["id"], [{"component_product_id": rice["id"], "gross_qty": 0.15}])
    r = cl.delete(f"{URL}/{rice['id']}")
    assert r.status_code == 400 and "Osh" in r.json()["detail"]
    assert cl.put(f"{URL}/{dish['id']}", json={"kind": "ingredient"}).status_code == 400
    # taom o'chirilsa kartasi ham nofaol; keyin ingredient o'chadi
    assert cl.delete(f"{URL}/{dish['id']}").status_code == 200
    assert db.query(BOM).filter(BOM.product_id == dish["id"], BOM.is_active == True).count() == 0  # noqa: E712
    assert cl.delete(f"{URL}/{rice['id']}").status_code == 200
    assert db.get(Product, rice["id"]).is_deleted is True


def test_price_change_audited(db, mk, client):
    from app.models.audit_log import AuditLog
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    dish = _item(cl, name="Osh", kind="dish", sale_price=45000)
    assert cl.put(f"{URL}/{dish['id']}", json={"sale_price": 48000}).json()["sale_price"] == 48000
    assert db.query(AuditLog).filter(AuditLog.action == "MENU_PRICE_CHANGE", AuditLog.entity_id == dish["id"]).count() == 1


# ───────────────────────── R1.4 sexlar ─────────────────────────

def test_stations_crud_and_effective_station(db, mk, client):
    c, b, u = _rest(db, mk)
    cl = client.login(u)
    st = {s["name"]: s for s in cl.get("/api/restaurant/stations").json()}
    assert list(st) == ["Issiq sex", "Sovuq sex", "Bar"]
    r = cl.post("/api/restaurant/stations", json={"name": "Kalyan"})
    assert r.status_code == 201 and r.json()["sort_order"] == 3
    assert cl.post("/api/restaurant/stations", json={"name": "kalyan"}).status_code == 409
    assert cl.put(f"/api/restaurant/stations/{st['Bar']['id']}", json={"kds_enabled": True}).json()["kds_enabled"] is True

    salads = db.query(Category).filter(Category.company_id == c.id, Category.name == "Salatlar").one()
    r = cl.put(f"/api/restaurant/menu/categories/{salads.id}", json={"station_id": st["Sovuq sex"]["id"]})
    assert r.status_code == 200 and r.json()["station_id"] == st["Sovuq sex"]["id"]
    salad = _item(cl, name="Achchiq-chuchuk", kind="dish", category_id=salads.id)
    assert salad["effective_station_id"] == st["Sovuq sex"]["id"] and salad["station_id"] is None
    upd = cl.put(f"{URL}/{salad['id']}", json={"station_id": st["Issiq sex"]["id"]}).json()
    assert upd["effective_station_id"] == st["Issiq sex"]["id"]


def test_station_from_other_company_rejected(db, mk, client):
    c1, b1, u1 = _rest(db, mk)
    c2, b2, u2 = _rest(db, mk)
    foreign = db.query(KitchenStation).filter(KitchenStation.company_id == c2.id).first()
    cl = client.login(u1)
    assert cl.post(URL, json={"name": "Osh", "kind": "dish", "station_id": foreign.id}).status_code == 400
    assert cl.put(f"/api/restaurant/stations/{foreign.id}", json={"name": "X"}).status_code == 404


# ───────────────────────── Frontend ─────────────────────────

def test_frontend_menu_page_wired():
    app_jsx = _read('frontend/src/App.jsx')
    assert "RestaurantMenu" in app_jsx and 'path="restaurant/menu"' in app_jsx
    layout = _read('frontend/src/components/AdminLayout.jsx')
    assert "path: '/admin/restaurant/menu'" in layout and "feature: 'restaurant'" in layout
    page = _read('frontend/src/pages/admin/restaurant/RestaurantMenu.jsx')
    for token in ("/restaurant/menu/items", "/card", "/restaurant/stations", "/restaurant/menu/categories",
                  "gross_qty", "net_qty", "output_qty", "food_cost_pct"):
        assert token in page, token


def test_i18n_keys_in_all_languages():
    import re
    page = _read('frontend/src/pages/admin/restaurant/RestaurantMenu.jsx')
    keys = set(re.findall(r"'(restMenu\.[\w.]+)'", page))
    keys |= {f'restMenu.add.{k}' for k in ('dish', 'semi', 'ingredient', 'goods')}   # t(`restMenu.add.${tab}`)
    keys |= {'nav.restaurant', 'nav.restaurantMenu', 'features.restaurant.title'}
    assert len(keys) > 60
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
