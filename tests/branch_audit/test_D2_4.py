"""D2.4 — Quti, blister va dona bitta kartochkada (product_units).

Qamrov: birliklar CRUD (faqat dorixona, korxona izolyatsiyasi, noyob shtrix-kod); sotuv `unit_id` (quti/blister/dona):
qoldiq asosiy birlikda, narx (unit.sale_price / quti narxidan yuqoriga yaxlitlangan / mahsulot narxi * nisbat),
SaleItemUnit; ochilgan quti avval; butun quti "yig'ma" emas va 400 xabari; kirimda `unit_id` (miqdor * nisbat,
narx / nisbat); POS qidiruvi (birlik shtrix-kodi, units, stock_display); oddiy korxona va ProductConversion regressiyasi.

Eslatma: `SaleItemCreate` / `POItemCreate` / `POReceiveItem` sxemalarida `unit_id` maydoni hali yo'q (sxema fayllari
D2.4 ruxsatida emas — natijada `blocked_files`). Servis `getattr(item, "unit_id", None)` o'qiydi, shuning uchun
testlar servisni `unit_id` li sxema nusxalari bilan chaqiradi; maydon sxemaga qo'shilgach `test_schemas_expose_unit_id`
xfail dan chiqadi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_D2_4.py -q -p no:cacheprovider
"""
import itertools
import json
import pathlib
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D
from typing import List, Optional

import pytest
from fastapi import HTTPException

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.moliya import Wallet
from app.models.product import Product, ProductConversion
from app.models.product_pharma import ProductPharma
from app.models.product_units import ProductUnit, SaleItemUnit
from app.models.sale import Sale, SaleItem, SaleItemBatch
from app.models.supplier import Supplier
from app.models.user import UserRole, UserWallet
from app.schemas.purchase_order import POCreate, POItemCreate, POReceiveItem, POReceiveRequest
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services.batch_allocator import tashkent_today
from app.services.purchase_order_service import create_purchase_order, receive_purchase_order
from app.services.sale_create import create_sale

ROOT = pathlib.Path(__file__).resolve().parents[2]
_n = itertools.count(1)


# ─── unit_id li sxema nusxalari (sxema fayllari ruxsatdan tashqarida) ───

class _Item(SaleItemCreate):
    unit_id: Optional[int] = None


class _Sale(SaleCreate):
    items: List[_Item]


class _POItem(POItemCreate):
    unit_id: Optional[int] = None


class _PO(POCreate):
    items: List[_POItem]


class _RecvItem(POReceiveItem):
    unit_id: Optional[int] = None


class _Recv(POReceiveRequest):
    items: List[_RecvItem]


# ─── yordamchilar ───

def _enable(db, c, **settings):
    c.pharmacy_enabled = True
    if settings:
        c.pharmacy_settings = settings
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=c.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _wallet(db, c, b, user):
    w = Wallet(name=f"Kassa {next(_n)}", type="cash", balance=D(0), company_id=c.id, branch_id=b.id,
               is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(UserWallet(user_id=user.id, wallet_id=w.id, is_default=True, company_id=c.id))
    db.flush()
    return w


def _product(db, c, price=1000, **kw):
    n = next(_n)
    p = Product(name=kw.pop("name", f"Dori D24-{n}"), sku=f"D24-{n}", barcode=f"BD24-{n:06d}", company_id=c.id,
                cost_price=D("500"), sale_price=D(price), **kw)
    db.add(p)
    db.flush()
    return p


def _dt(days):
    if days is None:
        return None
    return datetime.combine(tashkent_today() + timedelta(days=days), time.min)


def _batch(db, p, wh, qty, expiry_days=100, age_days=0, price=100):
    b = Batch(product_id=p.id, warehouse_id=wh.id, quantity=D(qty), initial_quantity=D(qty),
              purchase_price=D(price), company_id=p.company_id, expiry_date=_dt(expiry_days),
              created_at=datetime.utcnow() - timedelta(days=age_days))
    db.add(b)
    db.flush()
    return b


def _stock(db, p, wh, qty):
    sl = StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(qty))
    db.add(sl)
    db.flush()
    return sl


def _unit(db, p, name, ratio, price=None, barcode=None):
    u = ProductUnit(product_id=p.id, company_id=p.company_id, name=name, ratio=D(ratio),
                    sale_price=D(price) if price is not None else None, barcode=barcode)
    db.add(u)
    db.flush()
    return u


def _q(db, obj):
    db.refresh(obj)
    return D(str(obj.quantity))


def _body(items, wh, total=None):
    total = total if total is not None else sum(D(str(i.get("_t", 0))) for i in items)
    for i in items:
        i.pop("_t", None)
    return {"items": items, "payment_type": "cash", "paid_amount": total, "paid_cash": total,
            "payments": [{"type": "cash", "amount": total}] if total > 0 else [], "warehouse_id": wh.id}


def _sell(db, user, wh, product, qty, unit=None, price=None, **item_extra):
    item = {"product_id": product.id, "quantity": qty}
    if unit is not None:
        item["unit_id"] = unit.id
    if price is not None:
        item["unit_price"] = price
    item.update(item_extra)
    return create_sale(db, _Sale(**_body([item], wh, total=D("10000000"))), user)


def _sale_item(db, sale):
    return db.query(SaleItem).filter(SaleItem.sale_id == sale.id).one()


@pytest.fixture
def ph(db, mk):
    """A — dorixona (kassa bilan), B — oddiy korxona (kassa bilan), C — boshqa dorixona (izolyatsiya)."""
    c, b, wh, admin = mk.tenant()
    _wallet(db, c, b, admin)
    _enable(db, c, price_round=100)
    c2, b2, wh2, admin2 = mk.tenant()
    _wallet(db, c2, b2, admin2)
    c3, b3, wh3, admin3 = mk.tenant()
    _wallet(db, c3, b3, admin3)
    _enable(db, c3)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    return dict(c=c, b=b, wh=wh, admin=admin, cashier=cashier, c2=c2, wh2=wh2, admin2=admin2,
                c3=c3, wh3=wh3, admin3=admin3)


@pytest.fixture
def med(db, ph):
    """Dorixona mahsuloti: 1 dona = 1000 so'm; quti = 30 dona, blister = 10 dona, dona = 1."""
    p = _product(db, ph["c"], price=1000)
    box = _unit(db, p, "quti", 30)
    blister = _unit(db, p, "blister", 10)
    piece = _unit(db, p, "dona", 1, barcode=f"U-DONA-{next(_n)}")
    return dict(p=p, box=box, blister=blister, piece=piece)


# ───────────────────────── 1. Birliklar CRUD ─────────────────────────

def test_units_crud_and_pack_flag(client, db, ph):
    p = _product(db, ph["c"], price=1000)
    cl = client.login(ph["admin"])
    r = cl.post(f"/api/pharmacy/products/{p.id}/units", json={"name": "quti", "ratio": 30, "sale_price": 28000})
    assert r.status_code == 201, r.text
    box = r.json()
    assert box["ratio"] == 30 and box["sale_price"] == 28000 and box["price"] == 28000 and box["is_pack"] is True
    r = cl.post(f"/api/pharmacy/products/{p.id}/units", json={"name": "dona", "ratio": 1, "barcode": "UB-1"})
    assert r.status_code == 201, r.text
    piece = r.json()
    # dona narxi: quti narxi / 30 = 933.33 -> 100 qadamiga yuqoriga yaxlitlanadi = 1000
    assert piece["price"] == 1000 and piece["is_pack"] is False
    units = cl.get(f"/api/pharmacy/products/{p.id}/units").json()
    assert [u["name"] for u in units] == ["quti", "dona"]            # katta nisbatdan kichigiga
    r = cl.put(f"/api/pharmacy/products/{p.id}/units/{piece['id']}",
               json={"name": "dona", "ratio": 1, "sale_price": 950, "barcode": "UB-1"})
    assert r.status_code == 200 and r.json()["price"] == 950
    assert cl.delete(f"/api/pharmacy/products/{p.id}/units/{piece['id']}").status_code == 204
    assert [u["name"] for u in cl.get(f"/api/pharmacy/products/{p.id}/units").json()] == ["quti"]


def test_units_validation_and_unique_barcode(client, db, ph):
    p = _product(db, ph["c"])
    p2 = _product(db, ph["c"])
    cl = client.login(ph["admin"])
    url = f"/api/pharmacy/products/{p.id}/units"
    assert cl.post(url, json={"name": "quti", "ratio": 0}).status_code == 422
    assert cl.post(url, json={"name": "quti", "ratio": -3}).status_code == 422
    assert cl.post(url, json={"name": "  ", "ratio": 2}).status_code == 422
    assert cl.post(url, json={"name": "quti", "ratio": 2, "sale_price": -1}).status_code == 422
    assert cl.post(url, json={"name": "quti", "ratio": 30, "barcode": "UB-77"}).status_code == 201
    assert cl.post(url, json={"name": "QUTI", "ratio": 20}).status_code == 400            # nom takrori (katta-kichik harf farqsiz)
    r = cl.post(f"/api/pharmacy/products/{p2.id}/units", json={"name": "quti", "ratio": 10, "barcode": "UB-77"})
    assert r.status_code == 400 and "UB-77" in r.json()["detail"]                        # shtrix-kod korxonada noyob
    r = cl.post(url, json={"name": "blister", "ratio": 10, "barcode": p2.barcode})
    assert r.status_code == 400                                                           # mahsulot shtrix-koduga to'g'ri kelmaydi


def test_units_only_in_pharmacy_mode(client, db, ph):
    p = _product(db, ph["c2"])
    cl = client.login(ph["admin2"])
    assert cl.get(f"/api/pharmacy/products/{p.id}/units").status_code == 403
    assert cl.post(f"/api/pharmacy/products/{p.id}/units", json={"name": "quti", "ratio": 10}).status_code == 403
    assert db.query(ProductUnit).filter_by(company_id=ph["c2"].id).count() == 0


def test_units_company_isolation(client, db, ph):
    mine = _product(db, ph["c"])
    theirs = _product(db, ph["c3"])
    u_theirs = _unit(db, theirs, "quti", 20)
    cl = client.login(ph["admin"])
    assert cl.get(f"/api/pharmacy/products/{theirs.id}/units").status_code == 404
    assert cl.post(f"/api/pharmacy/products/{theirs.id}/units", json={"name": "x", "ratio": 2}).status_code == 404
    assert cl.put(f"/api/pharmacy/products/{theirs.id}/units/{u_theirs.id}",
                  json={"name": "x", "ratio": 2}).status_code == 404
    assert cl.delete(f"/api/pharmacy/products/{theirs.id}/units/{u_theirs.id}").status_code == 404
    # o'z mahsulotida birlik ID si begona bo'lsa ham 404
    assert cl.put(f"/api/pharmacy/products/{mine.id}/units/{u_theirs.id}",
                  json={"name": "x", "ratio": 2}).status_code == 404
    assert db.query(ProductUnit).filter_by(id=u_theirs.id).one().name == "quti"
    # ijobiy yo'l: o'z mahsuloti
    assert cl.post(f"/api/pharmacy/products/{mine.id}/units", json={"name": "quti", "ratio": 10}).status_code == 201


def test_cashier_can_list_but_not_edit_units(client, db, ph, med):
    cl = client.login(ph["cashier"])
    assert cl.get(f"/api/pharmacy/products/{med['p'].id}/units").status_code == 200
    assert cl.post(f"/api/pharmacy/products/{med['p'].id}/units", json={"name": "ampula", "ratio": 5}).status_code == 403


# ───────────────────────── 2. Sotuv: qoldiq va narx ─────────────────────────

def test_sell_pieces_from_box_keeps_stock_in_base_unit(client, db, ph, med):
    """Qabul: 1 quti (30 dona) kirim, 7 dona sotuv -> qoldiq 23, partiya 23."""
    p, wh = med["p"], ph["wh"]
    sl = _stock(db, p, wh, 30)
    b = _batch(db, p, wh, 30, price=D("3333.33"))
    sale = _sell(db, ph["admin"], wh, p, 7, unit=med["piece"])
    assert _q(db, sl) == 23 and _q(db, b) == 23
    it = _sale_item(db, sale)
    assert D(str(it.quantity)) == 7 and abs(D(str(it.subtotal)) - D(7000)) < 1
    assert abs(D(str(it.cost_price)) - D("3333.33")) < 1                       # tannarx dona uchun
    sib = db.query(SaleItemBatch).filter_by(sale_item_id=it.id).one()
    assert D(str(sib.quantity)) == 7


def test_sell_box_deducts_ratio_and_saves_unit_snapshot(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    sl = _stock(db, p, wh, 90)
    b = _batch(db, p, wh, 90)
    sale = _sell(db, ph["admin"], wh, p, 2, unit=med["box"])
    assert _q(db, sl) == 30 and _q(db, b) == 30
    it = _sale_item(db, sale)
    assert D(str(it.quantity)) == 60                                           # SaleItem.quantity — asosiy birlikda
    assert abs(D(str(it.subtotal)) - D(60000)) < 1                              # 2 quti * (1000 * 30)
    su = db.query(SaleItemUnit).filter_by(sale_item_id=it.id).one()
    assert (su.unit_name, D(str(su.unit_ratio)), D(str(su.unit_qty))) == ("quti", D(30), D(2))
    assert abs(D(str(su.unit_price)) - D(30000)) < D("0.01")
    # keyin birlik o'chirilsa ham o'tgan sotuvdagi nom va nisbat saqlanadi
    db.delete(med["box"])
    db.flush()
    db.expire_all()
    su = db.query(SaleItemUnit).filter_by(sale_item_id=it.id).one()
    assert su.unit_name == "quti" and su.unit_id is None


def test_unit_price_rules(client, db, ph):
    p = _product(db, ph["c"], price=1000)
    wh = ph["wh"]
    _stock(db, p, wh, 1000)
    _batch(db, p, wh, 1000)
    box = _unit(db, p, "quti", 30, price=31000)            # quti narxi 31000 (30 dona * 1000 dan arzonlashmagan)
    blister = _unit(db, p, "blister", 10)                  # narxi yo'q: 31000 / 30 * 10 = 10333.33 -> 10400
    piece = _unit(db, p, "dona", 1)                        # 1033.33 -> 1100
    own = _unit(db, p, "ampula", 5, price=4500)            # o'z narxi
    for unit, qty, expect in ((box, 1, 31000), (blister, 2, 20800), (piece, 3, 3300), (own, 2, 9000)):
        sale = _sell(db, ph["admin"], wh, p, qty, unit=unit)
        assert abs(D(str(_sale_item(db, sale).subtotal)) - D(expect)) < D("0.01"), (unit.name, expect)


def test_unit_price_without_box_price_is_product_price_times_ratio(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    _stock(db, p, wh, 100)
    _batch(db, p, wh, 100)
    sale = _sell(db, ph["admin"], wh, p, 1, unit=med["blister"])
    assert abs(D(str(_sale_item(db, sale).subtotal)) - D(10000)) < D("0.01")


def test_manual_unit_price_and_discount_in_units(client, db, ph, med):
    """Kassir quti narxini qo'lda bersa (price_manual) — shu narx, asosiy birlikka bo'lingan holda saqlanadi."""
    p, wh = med["p"], ph["wh"]
    _stock(db, p, wh, 100)
    _batch(db, p, wh, 100)
    sale = _sell(db, ph["admin"], wh, p, 2, unit=med["box"], price=25000, price_manual=True, discount=1000)
    it = _sale_item(db, sale)
    assert D(str(it.quantity)) == 60
    assert abs(D(str(it.subtotal)) - D(49000)) < D("0.01")                      # 2 * 25000 - 1000
    su = db.query(SaleItemUnit).filter_by(sale_item_id=it.id).one()
    assert abs(D(str(su.unit_price)) - D(25000)) < D("0.01")


@pytest.mark.parametrize("box_price,ratio", [(5000, 3), (7000, 6), (10000, 7)])
def test_box_price_not_divisible_by_ratio_gives_exact_total_and_exact_cash_payment(client, db, ph, box_price, ratio):
    """Quti narxi nisbatga qoldiqsiz bo'linmasa ham jami aniq (2 xona) bo'ladi: mijozsiz naqd aynan narxga to'lansa 200."""
    p = _product(db, ph["c"], price=1000)
    wh = ph["wh"]
    _stock(db, p, wh, 100)
    _batch(db, p, wh, 100)
    box = _unit(db, p, "quti", ratio, price=box_price)
    item = {"product_id": p.id, "quantity": 1, "unit_id": box.id}
    sale = create_sale(db, _Sale(**_body([item], wh, total=D(box_price))), ph["admin"])   # mijoz yo'q, aynan narx to'lanadi
    assert D(str(sale.total_amount)) == D(box_price)
    it = _sale_item(db, sale)
    assert D(str(it.quantity)) == ratio
    assert D(str(it.subtotal)) == D(box_price)
    su = db.query(SaleItemUnit).filter_by(sale_item_id=it.id).one()
    assert D(str(su.unit_price)) == D(box_price)                                # aniq quti narxi (qayta ko'paytirilmagan)


def test_exact_total_for_several_boxes_and_manual_unit_price(client, db, ph):
    p = _product(db, ph["c"], price=1000)
    wh = ph["wh"]
    _stock(db, p, wh, 100)
    _batch(db, p, wh, 100)
    box = _unit(db, p, "quti", 3, price=5000)
    sale = create_sale(db, _Sale(**_body([{"product_id": p.id, "quantity": 3, "unit_id": box.id}], wh, total=D(15000))),
                       ph["admin"])
    assert D(str(sale.total_amount)) == D(15000)
    # kassir narxni qo'lda bergan: 4999 / 3 bo'linmaydi, lekin jami aynan 4999
    sale2 = create_sale(db, _Sale(**_body([{"product_id": p.id, "quantity": 1, "unit_id": box.id,
                                            "unit_price": 4999, "price_manual": True}], wh, total=D(4999))), ph["admin"])
    assert D(str(sale2.total_amount)) == D(4999)
    su = db.query(SaleItemUnit).filter_by(sale_item_id=_sale_item(db, sale2).id).one()
    assert D(str(su.unit_price)) == D(4999)


def test_full_discount_on_non_divisible_box_price_is_not_rejected(client, db, ph):
    """Chegirma = butun quti narxi bo'lsa kasr xatosi tufayli 'chegirma narxdan oshdi' 400 chiqmasligi kerak."""
    p = _product(db, ph["c"], price=1000)
    wh = ph["wh"]
    _stock(db, p, wh, 100)
    _batch(db, p, wh, 100)
    box = _unit(db, p, "quti", 6, price=7000)
    sale = create_sale(db, _Sale(**_body([{"product_id": p.id, "quantity": 1, "unit_id": box.id, "discount": 7000}],
                                         wh, total=D(0))), ph["admin"])
    assert D(str(sale.total_amount)) == 0


def test_unknown_or_foreign_unit_is_404_and_writes_nothing(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    sl = _stock(db, p, wh, 50)
    _batch(db, p, wh, 50)
    foreign = _unit(db, _product(db, ph["c3"]), "quti", 10)
    for uid in (foreign.id, 999999):
        with pytest.raises(HTTPException) as e:
            create_sale(db, _Sale(**_body([{"product_id": p.id, "quantity": 1, "unit_id": uid}], wh, D(10000))), ph["admin"])
        assert e.value.status_code == 404
    assert db.query(Sale).filter(Sale.company_id == ph["c"].id).count() == 0
    assert _q(db, sl) == 50


# ───────────────────────── 3. Quti ochish qoidalari ─────────────────────────

def test_loose_sale_takes_opened_box_batch_first_even_if_expires_later(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    _stock(db, p, wh, 95)
    whole = _batch(db, p, wh, 60, expiry_days=50)       # butun qutilar, muddati yaqin
    opened = _batch(db, p, wh, 35, expiry_days=200)     # 1 quti + 5 dona (ochilgan), muddati uzoq
    _sell(db, ph["admin"], wh, p, 3, unit=med["piece"])
    assert _q(db, opened) == 32 and _q(db, whole) == 60  # ochilgan quti avval (FEFO emas)


def test_loose_sale_fefo_among_opened_then_new_box_in_fefo(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    _stock(db, p, wh, 100)
    opened_far = _batch(db, p, wh, 35, expiry_days=300)
    opened_near = _batch(db, p, wh, 32, expiry_days=100)   # 2 dona ochilgan, muddati yaqinroq
    whole_near = _batch(db, p, wh, 30, expiry_days=40)     # ochilmagan, eng yaqin muddat
    sale = _sell(db, ph["admin"], wh, p, 1, unit=med["piece"])
    assert _q(db, opened_near) == 31                       # ochilganlar ichida FEFO
    assert _q(db, opened_far) == 35 and _q(db, whole_near) == 30
    # ochilgan partiyalar tugagach — qolganlar FEFO bo'yicha (yangi quti ochiladi)
    _sell(db, ph["admin"], wh, p, 31 + 35 + 4, unit=med["piece"])
    assert _q(db, opened_near) == 0 and _q(db, opened_far) == 0 and _q(db, whole_near) == 26


def test_loose_sale_never_uses_expired_or_inactive_batch(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    _stock(db, p, wh, 100)
    expired_opened = _batch(db, p, wh, 35, expiry_days=-2)     # ochilgan, lekin muddati o'tgan
    quarantine = _batch(db, p, wh, 35, expiry_days=300)
    quarantine.status = "quarantine"
    good = _batch(db, p, wh, 30, expiry_days=100)
    db.flush()
    _sell(db, ph["admin"], wh, p, 4, unit=med["piece"])
    assert _q(db, expired_opened) == 35 and _q(db, quarantine) == 35 and _q(db, good) == 26


def test_whole_box_sale_takes_only_whole_boxes_and_is_not_assembled(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    sl = _stock(db, p, wh, 70)
    a = _batch(db, p, wh, 35, expiry_days=60)     # 1 quti + 5 dona
    b = _batch(db, p, wh, 35, expiry_days=90)     # 1 quti + 5 dona
    sale = _sell(db, ph["admin"], wh, p, 2, unit=med["box"])
    assert _q(db, a) == 5 and _q(db, b) == 5                 # har partiyadan 1 quti; 5+5 dona "yig'ma quti" bo'lmadi
    assert _q(db, sl) == 10
    sibs = db.query(SaleItemBatch).filter_by(sale_item_id=_sale_item(db, sale).id).order_by(SaleItemBatch.id).all()
    assert [(s.batch_id, D(str(s.quantity))) for s in sibs] == [(a.id, D(30)), (b.id, D(30))]


def test_whole_box_sale_400_message_and_nothing_written(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    sl = _stock(db, p, wh, 90)
    a = _batch(db, p, wh, 45)     # 1 quti + 15 dona
    b = _batch(db, p, wh, 45)     # 1 quti + 15 dona
    with pytest.raises(HTTPException) as e:
        _sell(db, ph["admin"], wh, p, 3, unit=med["box"])     # jami 90 dona bor, lekin butun quti atigi 2 ta
    assert e.value.status_code == 400
    assert e.value.detail == f"{p.name}: butun quti 2 ta, ochilgan qutida 30 dona bor"
    assert db.query(Sale).filter(Sale.company_id == ph["c"].id).count() == 0
    assert _q(db, sl) == 90 and _q(db, a) == 45 and _q(db, b) == 45
    # kassir dona qilib sotishi mumkin
    _sell(db, ph["admin"], wh, p, 30, unit=med["piece"])
    assert _q(db, sl) == 60


def test_whole_box_sale_ignores_expired_boxes(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    _stock(db, p, wh, 90)
    _batch(db, p, wh, 60, expiry_days=-1)               # muddati o'tgan 2 quti
    ok = _batch(db, p, wh, 30, expiry_days=100)
    with pytest.raises(HTTPException) as e:
        _sell(db, ph["admin"], wh, p, 2, unit=med["box"])
    assert e.value.status_code == 400
    _sell(db, ph["admin"], wh, p, 1, unit=med["box"])
    assert _q(db, ok) == 0


def test_pack_qty_from_pharma_card_defines_box(client, db, ph):
    """Birliklar ichida quti yo'q bo'lsa ham ProductPharma.pack_qty quti nisbatini belgilaydi."""
    p = _product(db, ph["c"])
    db.add(ProductPharma(product_id=p.id, company_id=ph["c"].id, pack_qty=20))
    piece = _unit(db, p, "dona", 1)
    _stock(db, p, ph["wh"], 25)
    opened = _batch(db, p, ph["wh"], 25, expiry_days=300)       # 1 quti + 5 ochilgan
    whole = _batch(db, p, ph["wh"], 20, expiry_days=10)
    _sell(db, ph["admin"], ph["wh"], p, 2, unit=piece)
    assert _q(db, opened) == 23 and _q(db, whole) == 20


# ───────────────────────── 4. Kirim ─────────────────────────

def _supplier(db, c):
    s = Supplier(name=f"Taminotchi {c.id}-{next(_n)}", company_id=c.id, is_active=True,
                 debt_balance=D(0), debt_balances={})
    db.add(s)
    db.flush()
    return s


def _po(db, user, wh, sup, p, qty, cost, unit=None, status="sent"):
    item = {"product_id": p.id, "qty_ordered": qty, "unit_cost": cost}
    if unit is not None:
        item["unit_id"] = unit.id
    data = _PO(supplier_id=sup.id, warehouse_id=wh.id, status=status, items=[item])
    return create_purchase_order(db, data, user)


def test_receive_one_box_then_sell_seven_pieces(client, db, ph, med):
    """Qabul: 1 quti (30 dona) kirim, 7 dona sotuv: qoldiq 23, partiya 23; tannarx farqi 1 so'mdan oshmaydi."""
    p, wh = med["p"], ph["wh"]
    sup = _supplier(db, ph["c"])
    po = _po(db, ph["admin"], wh, sup, p, qty=1, cost=100000, unit=med["box"])
    item = po.items[0]
    assert D(str(item.qty_ordered)) == 30
    assert abs(D(str(item.unit_cost)) * 30 - D(100000)) <= 1                   # 3333.33 * 30
    receive_purchase_order(db, po.id, _Recv(items=[{"po_item_id": item.id, "qty_received": 30, "lot_number": "L1",
                                                    "expiry_date": _dt(400).isoformat()}]), ph["admin"])
    b = db.query(Batch).filter_by(product_id=p.id).one()
    sl = db.query(StockLevel).filter_by(product_id=p.id, warehouse_id=wh.id).one()
    assert D(str(b.quantity)) == 30 and _q(db, sl) == 30
    assert abs(D(str(b.purchase_price)) * 30 - D(100000)) <= 1
    sale = _sell(db, ph["admin"], wh, p, 7, unit=med["piece"])
    assert _q(db, sl) == 23 and _q(db, b) == 23
    assert abs(D(str(_sale_item(db, sale).cost_price)) * 7 - D("23333.33")) <= 1


def test_receive_with_unit_converts_qty_and_lots(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    sup = _supplier(db, ph["c"])
    po = _po(db, ph["admin"], wh, sup, p, qty=3, cost=1000, unit=None)          # 3 dona buyurtma (asosiy birlikda)
    po2 = _po(db, ph["admin"], wh, sup, p, qty=100, cost=1000)
    exp = _dt(400).isoformat()
    # qabulda birlik: 2 quti (ikki seriyaga: 1 + 1 quti) = 60 dona
    receive_purchase_order(db, po2.id, _Recv(items=[{
        "po_item_id": po2.items[0].id, "unit_id": med["box"].id,
        "lots": [{"lot_number": "A", "expiry_date": exp, "qty": 1}, {"lot_number": "B", "expiry_date": exp, "qty": 1}],
    }]), ph["admin"])
    got = sorted(D(str(b.quantity)) for b in db.query(Batch).filter_by(product_id=p.id, po_id=po2.id))
    assert got == [D(30), D(30)]
    assert D(str(po2.items[0].qty_received)) == 60
    # buyurtmadan ortiq quti — qolgan miqdordan ko'p
    with pytest.raises(HTTPException) as e:
        receive_purchase_order(db, po2.id, _Recv(items=[{"po_item_id": po2.items[0].id, "unit_id": med["box"].id,
                                                         "qty_received": 2, "lot_number": "C", "expiry_date": exp}]), ph["admin"])
    assert e.value.status_code == 400


def test_receive_unit_rules_plain_company_and_foreign_unit(client, db, ph, med):
    sup2 = _supplier(db, ph["c2"])
    plain_p = _product(db, ph["c2"])
    with pytest.raises(HTTPException) as e:
        _po(db, ph["admin2"], ph["wh2"], sup2, plain_p, 1, 1000, unit=med["box"])
    assert e.value.status_code == 400                                          # oddiy korxona: birlik faqat dorixonada
    sup = _supplier(db, ph["c"])
    foreign = _unit(db, _product(db, ph["c3"]), "quti", 10)
    with pytest.raises(HTTPException) as e:
        _po(db, ph["admin"], ph["wh"], sup, med["p"], 1, 1000, unit=foreign)
    assert e.value.status_code == 404                                          # begona korxona birligi
    other_product_unit = _unit(db, _product(db, ph["c"]), "quti", 10)
    with pytest.raises(HTTPException) as e:
        _po(db, ph["admin"], ph["wh"], sup, med["p"], 1, 1000, unit=other_product_unit)
    assert e.value.status_code == 404                                          # boshqa mahsulot birligi


# ───────────────────────── 5. POS qidiruvi va qoldiq ko'rinishi ─────────────────────────

def test_pos_list_barcode_returns_product_and_unit_with_stock_display(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    box = med["box"]
    box.barcode = f"BOX-{next(_n)}"
    db.flush()
    _stock(db, p, wh, 65)
    _batch(db, p, wh, 35)        # 1 quti + 5 ochilgan
    _batch(db, p, wh, 30)
    r = client.login(ph["admin"]).get("/api/products/pos-list", params={"search": box.barcode, "warehouse_id": wh.id})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [x["id"] for x in rows] == [p.id]
    row = rows[0]
    assert row["scanned_unit_id"] == box.id
    assert {u["name"] for u in row["units"]} == {"quti", "blister", "dona"}
    assert next(u for u in row["units"] if u["name"] == "quti")["price"] == 30000
    assert row["stock_display"] == "2 quti 5 dona"
    assert row["full_boxes"] == 2 and row["loose_units"] == 5
    assert row["pack_ratio"] == 30
    # oddiy qidiruv — scanned_unit_id yo'q, lekin units/stock_display bor
    row2 = client.login(ph["admin"]).get("/api/products/pos-list", params={"warehouse_id": wh.id}).json()[0]
    assert row2["scanned_unit_id"] is None and row2["stock_display"] == "2 quti 5 dona"


def test_pos_list_foreign_unit_barcode_not_found(client, db, ph, med):
    other = _product(db, ph["c3"])
    _unit(db, other, "quti", 10, barcode="FOREIGN-UB")
    rows = client.login(ph["admin"]).get("/api/products/pos-list", params={"search": "FOREIGN-UB"}).json()
    assert rows == []


def test_paginated_list_has_stock_display_in_pharmacy_only(client, db, ph, med):
    p, wh = med["p"], ph["wh"]
    _stock(db, p, wh, 95)
    _batch(db, p, wh, 95)
    r = client.login(ph["admin"]).get("/api/products/paginated", params={"warehouse_id": wh.id})
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["items"] if x["id"] == p.id)
    assert row["stock_display"] == "3 quti 5 dona" and row["full_boxes"] == 3 and row["loose_units"] == 5
    plain = _product(db, ph["c2"])
    _stock(db, plain, ph["wh2"], 10)
    r2 = client.login(ph["admin2"]).get("/api/products/paginated")
    row2 = next(x for x in r2.json()["items"] if x["id"] == plain.id)
    assert "stock_display" not in row2 and "units" not in row2


def test_stock_display_without_pack_info_is_none(client, db, ph):
    p = _product(db, ph["c"])
    _stock(db, p, ph["wh"], 12)
    row = client.login(ph["admin"]).get("/api/products/pos-list", params={"warehouse_id": ph["wh"].id}).json()[0]
    assert row["stock_display"] is None and row["units"] == []


# ───────────────────────── 6. Oddiy korxona va ProductConversion regressiyasi ─────────────────────────

def test_plain_company_pos_list_and_sale_unchanged(client, db, ph):
    p = _product(db, ph["c2"], price=1000)
    sl = _stock(db, p, ph["wh2"], 20)
    b = _batch(db, p, ph["wh2"], 20, expiry_days=-5)           # oddiy do'konda muddati o'tgani ham FIFO bilan sotiladi
    row = client.login(ph["admin2"]).get("/api/products/pos-list", params={"warehouse_id": ph["wh2"].id}).json()[0]
    for k in ("units", "stock_display", "full_boxes", "loose_units", "scanned_unit_id", "pack_ratio"):
        assert k not in row
    sale = _sell(db, ph["admin2"], ph["wh2"], p, 5)
    assert _q(db, sl) == 15 and _q(db, b) == 15
    assert D(str(_sale_item(db, sale).subtotal)) == 5000
    assert db.query(SaleItemUnit).count() == 0


def test_plain_company_rejects_unit_id_instead_of_silently_ignoring(client, db, ph):
    p = _product(db, ph["c2"])
    sl = _stock(db, p, ph["wh2"], 20)
    _batch(db, p, ph["wh2"], 20)
    foreign_unit = _unit(db, _product(db, ph["c"]), "quti", 10)
    with pytest.raises(HTTPException) as e:
        create_sale(db, _Sale(**_body([{"product_id": p.id, "quantity": 1, "unit_id": foreign_unit.id}],
                                       ph["wh2"], D(1000))), ph["admin2"])
    assert e.value.status_code == 400
    assert _q(db, sl) == 20 and db.query(Sale).filter(Sale.company_id == ph["c2"].id).count() == 0


def test_pharmacy_sale_without_unit_id_is_as_before(client, db, ph, med):
    """unit_id berilmasa — qator hozirgidek (miqdor asosiy birlikda, FEFO, narx mahsulot narxidan)."""
    p, wh = med["p"], ph["wh"]
    _stock(db, p, wh, 95)
    whole = _batch(db, p, wh, 60, expiry_days=50)
    opened = _batch(db, p, wh, 35, expiry_days=200)
    sale = _sell(db, ph["admin"], wh, p, 3)
    assert _q(db, whole) == 57 and _q(db, opened) == 35                         # oddiy FEFO (ochilgan quti qoidasi yo'q)
    assert D(str(_sale_item(db, sale).subtotal)) == 3000
    assert db.query(SaleItemUnit).count() == 0


@pytest.mark.parametrize("pharmacy", [False, True])
def test_product_conversion_still_works(client, db, ph, pharmacy):
    """Virtual mahsulot (ProductConversion): sotilgan 1 birlik uchun manba mahsulotdan ratio yechiladi."""
    c, wh, admin = (ph["c"], ph["wh"], ph["admin"]) if pharmacy else (ph["c2"], ph["wh2"], ph["admin2"])
    source = _product(db, c, price=10000, name=f"Butun {next(_n)}")
    sell = _product(db, c, price=2500, name=f"Bo'lak {next(_n)}", product_type="sell")
    db.add(ProductConversion(sell_product_id=sell.id, source_product_id=source.id, ratio=D("0.25")))
    db.flush()
    sl = _stock(db, source, wh, 10)
    b = _batch(db, source, wh, 10)
    sale = _sell(db, admin, wh, sell, 4)
    assert _q(db, sl) == 9 and _q(db, b) == 9
    assert D(str(_sale_item(db, sale).subtotal)) == 10000
    assert db.query(SaleItemUnit).count() == 0


def test_virtual_product_rejects_unit_in_pharmacy(client, db, ph):
    source = _product(db, ph["c"], price=10000)
    sell = _product(db, ph["c"], price=2500, product_type="sell")
    db.add(ProductConversion(sell_product_id=sell.id, source_product_id=source.id, ratio=D("0.25")))
    unit = _unit(db, sell, "quti", 4)
    _stock(db, source, ph["wh"], 10)
    _batch(db, source, ph["wh"], 10)
    with pytest.raises(HTTPException) as e:
        _sell(db, ph["admin"], ph["wh"], sell, 1, unit=unit)
    assert e.value.status_code == 400


# ───────────────────────── 7. Statik tekshiruvlar ─────────────────────────

def test_schemas_expose_unit_id():
    assert "unit_id" in SaleItemCreate.model_fields
    assert "unit_id" in POItemCreate.model_fields
    assert "unit_id" in POReceiveItem.model_fields


def test_migration_is_additive_and_models_match():
    src = (ROOT / "alembic" / "versions" / "d2_4_product_units.py").read_text(encoding="utf-8")
    assert "revision: str = 'd2_4'" in src and "down_revision" in src and "= 'd2_1'" in src
    assert "DROP COLUMN" not in src.upper() and "ALTER TABLE" not in src.upper()
    for col in ("ratio NUMERIC", "sale_price NUMERIC", "barcode VARCHAR", "sort_order INTEGER",
                "unit_name VARCHAR", "unit_ratio NUMERIC", "unit_qty NUMERIC", "uq_product_units_company_barcode"):
        assert col in src, col
    cols = {c.name for c in ProductUnit.__table__.columns}
    assert {"product_id", "company_id", "name", "ratio", "sale_price", "barcode", "sort_order"} <= cols
    assert {"sale_item_id", "unit_id", "unit_name", "unit_ratio", "unit_qty"} <= {c.name for c in SaleItemUnit.__table__.columns}


def test_pending_i18n_keys_match_across_languages():
    f = pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D2.4.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"]) and data["uz"]
    jsx = (ROOT / "frontend" / "src" / "pages" / "admin" / "Purchases.jsx").read_text(encoding="utf-8")
    for key in data["uz"]:
        assert key in jsx, key
