"""R1.2 — Tex kartalar Excel eksport / import: eksport qatorlari, tekshirish rejimi hech narsa saqlamaydi, yo'q taom
va ingredient yaratish, o'zgarmagan karta yangi versiya ochmaydi, yarim tayyor taomdan oldin saqlanadi,
qator xatolari, bir xil nom, ruxsatlar va frontend.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R1_2_excel.py -q -p no:cacheprovider
"""
import os
import re

import pytest

from app.models.bom import BOM
from app.models.product import Product
from app.services.restaurant_menu import active_card, create_item, save_card
from tests.branch_audit.test_R3 import R

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
EXP = "/api/restaurant/menu/cards/export"
IMP = "/api/restaurant/menu/cards/import"


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture
def r(db, mk):
    return R(db, mk)


def _row(dish, ing, gross, **kw):
    return {"dish": dish, "ingredient": ing, "gross": gross, **kw}


def test_export_rows(r, client, db):
    save_card(db, r.c.id, r.osh, {"output_weight_g": 350, "cooking_time_min": 20, "items": [
        {"component_product_id": r.rice.id, "gross_qty": 0.15, "net_qty": 0.14}]}, None)
    rows = client.login(r.admin).get(EXP).json()["rows"]
    osh = [x for x in rows if x["dish"] == "Osh"]
    assert len(osh) == 1
    x = osh[0]
    assert x["kind"] == "dish" and x["ingredient"] == "Guruch" and x["gross"] == 0.15 and x["net"] == 0.14
    assert x["output_weight_g"] == 350 and x["cooking_time_min"] == 20 and x["dish_code"] == r.osh.sku
    assert x["price"] == 20000 and x["line_cost"] == 3000 and x["sale_price"] == 50000


def test_dry_run_then_apply_with_create_missing(r, client, db):
    cl = client.login(r.admin)
    rows = [
        _row("Manti", "Qiyma", 0.2, kind="taom", output_qty=1, cooking_time_min=25, row=2),
        _row("Manti", "Un", "0,1", row=3, unit="kg", price=8000),
        _row("Qiyma", "Go'sht", 1.1, kind="yarim tayyor", output_qty=1, row=4, price=100000),
    ]
    n_products = db.query(Product).count()
    res = cl.post(IMP, json={"rows": rows, "create_missing": True, "dry_run": True})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["applied"] is False and out["summary"]["created"] == 2 and out["row_errors"] == []
    assert sorted(out["created_dishes"]) == ["Manti", "Qiyma"] and sorted(out["created_ingredients"]) == ["Go'sht", "Un"]
    assert [c["name"] for c in out["cards"]] == ["Qiyma", "Manti"]           # yarim tayyor avval
    assert db.query(Product).count() == n_products                           # hech narsa saqlanmadi
    # topilmaganlarni yaratmasdan: xatolar
    out = cl.post(IMP, json={"rows": rows, "dry_run": True}).json()
    assert out["summary"]["error"] == 2 and all(c["status"] == "error" for c in out["cards"])
    # haqiqiy import
    out = cl.post(IMP, json={"rows": rows, "create_missing": True, "dry_run": False}).json()
    assert out["applied"] is True and out["summary"]["created"] == 2
    manti = db.query(Product).filter(Product.name == "Manti").one()
    qiyma = db.query(Product).filter(Product.name == "Qiyma").one()
    un = db.query(Product).filter(Product.name == "Un").one()
    assert manti.item_kind == "dish" and qiyma.item_kind == "semi" and un.item_kind == "ingredient"
    assert un.unit == "kg" and float(un.cost_price) == 8000
    card = active_card(db, r.c.id, manti.id)
    assert card.cooking_time_min == 25 and {it.component_product_id for it in card.items} == {qiyma.id, un.id}
    # qayta import: o'zgarmagan, yangi versiya yo'q
    v_before = db.query(BOM).filter(BOM.product_id == manti.id).count()
    out = cl.post(IMP, json={"rows": rows, "create_missing": True, "dry_run": False}).json()
    assert out["summary"] == {"created": 0, "updated": 0, "unchanged": 2, "error": 0}
    assert db.query(BOM).filter(BOM.product_id == manti.id).count() == v_before
    # brutto o'zgardi: yangi versiya
    rows[1]["gross"] = 0.12
    out = cl.post(IMP, json={"rows": rows, "dry_run": False}).json()
    m = next(c for c in out["cards"] if c["name"] == "Manti")
    assert m["status"] == "updated" and m["version"] == 2


def test_row_errors_and_ambiguous_names(r, client, db):
    cl = client.login(r.admin)
    create_item(db, r.c.id, {"name": "Guruch", "kind": "ingredient"})     # ikkinchi "Guruch"
    rows = [
        _row("Osh", "Guruch", 0.15, row=2),
        _row("Osh", "Sabzi", "abc", row=3),
        _row("Salat", "Pomidor", 0.1, kind="ichimlik", row=4),
        _row("", "Piyoz", 0.1, row=5),
        _row("Cola", "Guruch", 0.1, row=6, ingredient_code=r.rice.sku),     # tovar: karta bo'lmaydi
    ]
    out = cl.post(IMP, json={"rows": rows, "dry_run": True, "create_missing": True}).json()
    msgs = {e["row"]: e["message"] for e in out["row_errors"]}
    assert "son emas" in msgs[3] and "Turi noto'g'ri" in msgs[4] and "Taom nomi bo'sh" in msgs[5]
    assert any("nomli 2 ta" in e["message"] for e in out["row_errors"])     # Guruch noaniq
    cards = {c["name"]: c for c in out["cards"]}
    assert cards["Osh"]["status"] == "error" and "taom yoki yarim tayyor emas" in cards["Cola"]["error"]
    # kod bilan aniq topiladi
    out = cl.post(IMP, json={"rows": [_row("Osh", "Guruch", 0.2, ingredient_code=r.rice.sku)],
                             "dry_run": False}).json()
    assert out["summary"]["updated"] == 1
    assert float(active_card(db, r.c.id, r.osh.id).items[0].gross_qty) == 0.2


def test_permissions_and_limits(r, client, mk):
    assert client.login(r.cashier).post(IMP, json={"rows": [_row("Osh", "Guruch", 1)]}).status_code == 403
    assert client.login(r.cashier).get(EXP).status_code == 403
    assert client.login(r.admin).post(IMP, json={"rows": []}).status_code == 400
    c = mk.company()
    b = mk.branch(c, is_main=True)
    assert client.login(mk.user(c, branch=b)).get(EXP).status_code == 403        # do'kon


def test_frontend_wired_and_i18n():
    page = _read('frontend/src/pages/admin/restaurant/RestaurantMenu.jsx')
    for token in ("/restaurant/menu/cards/export", "/restaurant/menu/cards/import", "dry_run", "create_missing",
                  "loadXLSX"):
        assert token in page, token
    keys = set(re.findall(r"'(restXl\.[\w.]+)'", page))
    assert len(keys) > 15
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)


def test_exported_headers_and_kinds_are_importable():
    """Eksport qilingan fayl (istalgan tilda) qayta import qilinadi: ustun va tur nomlari tanilishi shart."""
    from app.services.restaurant_card_io import KIND_ALIASES
    page = _read('frontend/src/pages/admin/restaurant/RestaurantMenu.jsx')
    block = page[page.index('const XL_COLS = ['):page.index('const XL_EXTRA')]
    aliases = {}
    for key, names in re.findall(r"\['(\w+)', \[([^\]]*)\]\]", block):
        found = re.findall(r"\"([^\"]*)\"|'([^']*)'", names)
        aliases[key] = {(a or b).lower() for a, b in found} | {key}
    assert len(aliases) == 14
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for key, names in aliases.items():
            m = re.search(r"'restXl\.col\.%s': '((?:[^'\\]|\\.)*)'" % key, d)
            label = m.group(1).replace("\\'", "'").lower()
            assert label in names, (lang, key, label)
        for kind in ('dish', 'semi'):
            m = re.search(r"'restXl\.kind\.%s': '((?:[^'\\]|\\.)*)'" % kind, d)
            assert KIND_ALIASES[m.group(1).replace("\\'", "'").lower()] == kind, (lang, kind)
