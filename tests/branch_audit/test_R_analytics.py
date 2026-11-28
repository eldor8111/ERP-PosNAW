"""Restoran tahliliy hisobotlari (12-bo'lim 3, 5, 6, 7, 9; R7.4): menyu muhandisligi guruhlari, yuklama xaritasi
(Toshkent vaqti), stol aylanishi va o'tirish vaqti, oshxona tezligi va me'yordan kechikish, ombor: nazariy sarf,
chiqim, inventarizatsiya farqi, manfiy qoldiq; ruxsatlar.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R_analytics.py -q -p no:cacheprovider
"""
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal as D

import pytest

from app.models.inventory import MovementType, StockMovement
from app.models.restaurant_order import RestaurantOrder, RestaurantOrderItem
from app.services import restaurant_orders as svc
from app.services.document_numbers import tashkent_today
from app.services.restaurant_analytics import menu_engineering
from app.services.restaurant_menu import save_card
from tests.branch_audit.test_R5 import RP

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"
A = "/api/restaurant/reports/analytics"


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(autouse=True)
def _reset():
    svc._PIN_FAILS.clear()
    yield


def test_menu_engineering_classes():
    rows = [
        {"product_id": 1, "name": "Osh", "qty": 100, "revenue": 5000000, "cost": 1500000, "profit": 3500000},       # 35 000
        {"product_id": 2, "name": "Choy", "qty": 120, "revenue": 600000, "cost": 60000, "profit": 540000},          # 4 500
        {"product_id": 3, "name": "Steyk", "qty": 10, "revenue": 1500000, "cost": 600000, "profit": 900000},        # 90 000
        {"product_id": 4, "name": "Sho'rva", "qty": 8, "revenue": 200000, "cost": 120000, "profit": 80000},         # 10 000
    ]
    out = menu_engineering(rows)
    cls = {r["name"]: r["class"] for r in out["items"]}
    # mashhurlik chegarasi 0.7 / 4 = 17.5%; o'rtacha marja 5 020 000 / 238 = 21 092
    assert out["popularity_threshold"] == 17.5 and round(out["margin_threshold"]) == 21092
    assert cls == {"Osh": "star", "Choy": "plowhorse", "Steyk": "puzzle", "Sho'rva": "dog"}
    assert out["groups"] == {"star": 1, "plowhorse": 1, "puzzle": 1, "dog": 1}
    assert [r["class"] for r in out["items"]] == ["star", "plowhorse", "puzzle", "dog"]
    assert menu_engineering([])["items"] == []


@pytest.fixture
def rp(db, mk):
    return RP(db, mk)


def _pay(cl, oid, total):
    r = cl.post(f"{O}/{oid}/pay", json={"payments": [{"type": "cash", "amount": total}]})
    assert r.status_code == 200, r.text


def test_analytics_end_to_end(rp, client, db):
    save_card(db, rp.c.id, rp.osh, {"cooking_time_min": 15, "items": [{"component_product_id": rp.rice.id,
                                                                        "gross_qty": 0.15}]}, None)
    cl = client.login(rp.cashier)
    o1 = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2}, table=0)          # 2 osh
    o2 = rp.ready_check(cl, {"product_id": rp.osh.id}, table=0)                          # 1 osh, shu stol
    _pay(cl, o1, 110000)
    _pay(cl, o2, 55000)
    # vaqtlar: bugun Toshkent 13:00 da ochilgan, 60 va 30 daqiqa o'tirgan
    today = tashkent_today()
    base = datetime(today.year, today.month, today.day, 13, 0) - timedelta(hours=5)   # UTC
    for oid, mins in ((o1, 60), (o2, 30)):
        o = db.get(RestaurantOrder, oid)
        o.opened_at, o.closed_at = base, base + timedelta(minutes=mins)
    # oshxona: 1-chek 20 daqiqada (me'yor 15: kechikdi), 2-chek 10 daqiqada
    for oid, mins in ((o1, 20), (o2, 10)):
        for it in db.query(RestaurantOrderItem).filter(RestaurantOrderItem.order_id == oid):
            it.sent_at = base
            it.cooking_at = base + timedelta(minutes=2)
            it.ready_at = base + timedelta(minutes=mins)
    # revizya: guruch kamomadi 0.2 kg
    db.add(StockMovement(product_id=rp.rice.id, warehouse_id=rp.kitchen.id, type=MovementType.ADJUST,
                         qty_before=D("9.55"), qty_after=D("9.35"), quantity=D("0.2"), reference_type="revision",
                         reference_id=1, user_id=rp.admin.id))
    db.flush()

    res = client.login(rp.admin).get(A, params={"date_from": today.isoformat(), "date_to": today.isoformat()})
    assert res.status_code == 200, res.text
    out = res.json()
    # 3. menyu: bitta taom — mashhur va foydali
    assert [(r["name"], r["class"]) for r in out["menu"]["items"]] == [("Osh", "star")]
    # 5. yuklama: bugungi hafta kuni, soat 13
    wd = today.weekday()
    assert out["load"]["checks"][wd][13] == 2 and out["load"]["by_hour"][13] == 2
    assert out["load"]["peak"] == {"weekday": wd, "hour": 13, "checks": 2}
    # 6. stol aylanishi: 1-stol 2 marta, o'rtacha 45 daqiqa
    t0 = next(r for r in out["tables"]["rows"] if r["table_id"] == rp.tables[0].id)
    assert t0["turns"] == 2 and t0["avg_minutes"] == 45.0 and t0["revenue"] == 165000
    assert out["tables"]["summary"]["avg_minutes"] == 45.0
    assert out["tables"]["summary"]["idle_tables"] == len(rp.tables) - 1
    # 7. oshxona: 2 qator, biri me'yordan kechikkan
    k = out["kitchen"]
    assert k["summary"]["items"] == 2 and k["summary"]["avg_minutes"] == 15.0 and k["summary"]["late"] == 1
    assert k["summary"]["avg_wait"] == 2.0
    assert k["dishes"][0]["name"] == "Osh" and k["dishes"][0]["norm"] == 15 and k["dishes"][0]["late_pct"] == 50.0
    assert k["stations"][0]["name"] == rp.hot.name
    # 9. ombor: guruch nazariy sarf 0.45 (3 x 0.15), kamomad 0.2, haqiqiy 0.65
    rice = next(r for r in out["stock"]["rows"] if r["product_id"] == rp.rice.id)
    assert rice["sales"] == 0.45 and rice["theoretical"] == 0.45
    assert rice["variance"] == pytest.approx(-0.2) and rice["actual"] == pytest.approx(0.65)
    assert rice["variance_pct"] == 44.4 and rice["stock"] == 9.55
    assert out["stock"]["summary"]["variance_cost"] == -4000.0 and out["stock"]["summary"]["negative"] == 0


def test_stock_negative_and_production(rp, client, db):
    from app.services.restaurant_menu import create_item
    mince = create_item(db, rp.c.id, {"name": "Qiyma", "kind": "semi"})
    save_card(db, rp.c.id, mince, {"output_qty": 1, "items": [{"component_product_id": rp.rice.id, "gross_qty": 2}]}, None)
    rp.stock(rp.rice, rp.kitchen, 1)
    kc = client.login(rp.admin)
    r = kc.post("/api/restaurant/production", json={"branch_id": rp.b.id, "product_id": mince.id, "quantity": 1,
                                                    "force": True})
    assert r.status_code == 201, r.text
    out = kc.get(A).json()["stock"]
    rice = next(x for x in out["rows"] if x["product_id"] == rp.rice.id)
    q = next(x for x in out["rows"] if x["product_id"] == mince.id)
    assert rice["production"] == 2 and rice["stock"] == -1 and rice["negative"] is True
    assert q["produced"] == 1 and q["stock"] == 1
    assert [x["name"] for x in out["negative"]] == [rp.rice.name]


def test_permissions_and_period(rp, client):
    assert client.login(rp.cashier).get(A).status_code == 403
    adm = client.login(rp.admin)
    assert adm.get(A, params={"date_from": "2026-01-10", "date_to": "2026-01-01"}).status_code == 400
    assert adm.get(A, params={"date_from": "2026-01-01", "date_to": "2026-06-01"}).status_code == 400
    out = adm.get(A).json()
    assert out["period"]["days"] == 30 and out["menu"]["items"] == [] and out["load"]["peak"] is None


def test_frontend_wired_and_i18n():
    page = _read('frontend/src/pages/admin/restaurant/RestaurantReports.jsx')
    for token in ("/restaurant/reports/analytics", "menu", "load", "kitchen", "stock", "turns_per_day", "variance_pct"):
        assert token in page, token
    keys = set(re.findall(r"'(restAn\.[\w.]+)'", page))
    keys |= {f'restAn.class.{c}' for c in ('star', 'plowhorse', 'puzzle', 'dog')}
    keys |= {f'restAn.advice.{c}' for c in ('star', 'plowhorse', 'puzzle', 'dog')}
    keys |= {f'restAn.tab.{c}' for c in ('summary', 'menu', 'load', 'tables', 'kitchen', 'stock')}
    keys |= {f'restAn.wd.{i}' for i in range(7)}
    assert len(keys) > 40
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in keys:
            assert d.count(f"'{k}':") == 1, (lang, k)
