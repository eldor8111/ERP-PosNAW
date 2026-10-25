"""CD.1 — Dorixona tozalash: backend qoldiqlari.

Qamrov (har band: dorixona + oddiy korxona regressiyasi + ikki korxona izolyatsiyasi):
 1. Sotuv tafsiloti: qatorda `batches` (seriya, muddat, miqdor) va `unit_info` (quti/blister/dona), N+1 yo'q;
 2. `max_markup_pct` — mahsulot yaratish/tahrirlashda sotuv narxi ustama chegarasidan oshmasin;
 3. `/inventory/receive`: `manufacture_date` va qolgan muddat foizi ogohlantirishi;
 4. `SaleItemCreate` / `PartialReturnItem` da `lot_number`, `expiry_date` (asl partiya topilmasa);
 5. Qisman qaytarishda markirovka kodlari (sold -> in_stock);
 6. `GET /products/paginated`: `pharma` bloki va `substance_id`, `manufacturer`, `is_rx`, `control_class` filtrlari;
 7. Kutilayotgan sotuvni tasdiqlash: retsept tekshiruvi va markirovka kodlari (oddiy va to'liq tahrir yo'li);
 8. `POItemOut.requires_marking`;
 9. Markirovka va qutidan bo'lib sotish: butun quti = quti soni kod, dona = kodsiz yoki 1 ta (holati o'zgarmaydi);
10. Qo'lda kirimda (`/inventory/receive`) markirovka kodlari.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_CD_1.py -q -p no:cacheprovider
"""
import itertools
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D

import pytest
from sqlalchemy import event

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.marking_code import MarkingCode
from app.models.moliya import Wallet
from app.models.prescription import SalePrescription
from app.models.product import Product
from app.models.product_pharma import PharmaSubstance, ProductPharma, ProductSubstance
from app.models.product_units import ProductUnit, SaleItemUnit
from app.models.sale import Sale, SaleItem, SaleItemBatch
from app.models.supplier import Supplier
from app.models.user import UserRole, UserWallet
from app.services.batch_allocator import tashkent_today

_n = itertools.count(1)
GTIN = "04600000000017"


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


def _product(db, c, price=1000, cost=500, **kw):
    n = next(_n)
    p = Product(name=kw.pop("name", f"Dori CD{n}"), sku=f"CD1-{n}", barcode=kw.pop("barcode", f"BCD1{n:07d}"),
                company_id=c.id, cost_price=D(cost), sale_price=D(price), **kw)
    db.add(p)
    db.flush()
    return p


def _dt(days):
    return datetime.combine(tashkent_today() + timedelta(days=days), time.min)


def _stock(db, p, wh, qty, lot="L1", expiry_days=400):
    """Qoldiq va bitta partiya (FEFO uchun)."""
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(qty)))
    b = Batch(product_id=p.id, warehouse_id=wh.id, quantity=D(qty), initial_quantity=D(qty), purchase_price=D(100),
              company_id=p.company_id, lot_number=lot, expiry_date=_dt(expiry_days))
    db.add(b)
    db.flush()
    return b


def _unit(db, p, name, ratio):
    u = ProductUnit(product_id=p.id, company_id=p.company_id, name=name, ratio=D(ratio))
    db.add(u)
    db.flush()
    return u


def _code(serial, gtin=GTIN):
    return f"01{gtin}21{serial}"


def _mcode(db, c, p, serial, wh=None, batch=None, status="in_stock"):
    code = _code(serial)
    row = MarkingCode(company_id=c.id, code=code, gtin=GTIN, serial=serial, product_id=p.id, status=status,
                      warehouse_id=wh.id if wh else None, batch_id=batch.id if batch else None)
    db.add(row)
    db.flush()
    return row


def _mrow(db, c, code):
    return db.query(MarkingCode).filter_by(company_id=c.id, code=code).one()


def _sale_body(wh, items, total=10_000_000):
    return {"items": items, "payment_type": "cash", "paid_amount": total, "paid_cash": total,
            "payments": [{"type": "cash", "amount": total}], "warehouse_id": wh.id}


def _post_sale(client, user, wh, items, **kw):
    return client.login(user).post("/api/sales/", json=_sale_body(wh, items, **kw))


@pytest.fixture
def w(db, mk):
    """P — dorixona (sozlamalar bilan), Q — boshqa dorixona (izolyatsiya), N — oddiy korxona."""
    p_c, p_b, p_wh, p_admin = mk.tenant()
    q_c, q_b, q_wh, q_admin = mk.tenant()
    n_c, n_b, n_wh, n_admin = mk.tenant()
    for c, b, u in ((p_c, p_b, p_admin), (q_c, q_b, q_admin), (n_c, n_b, n_admin)):
        _wallet(db, c, b, u)
    _enable(db, p_c, max_markup_pct=50, min_shelf_life_pct=50, rx_mode="warn")
    _enable(db, q_c)
    return dict(pc=p_c, pb=p_b, pwh=p_wh, padmin=p_admin, qc=q_c, qwh=q_wh, qadmin=q_admin,
                nc=n_c, nwh=n_wh, nadmin=n_admin)


# ───────────────────────── 1. Sotuv tafsiloti: batches va unit_info ─────────────────────────

def test_sale_detail_pharmacy_has_batches_and_unit(client, db, w):
    p = _product(db, w["pc"], price=1000)
    box = _unit(db, p, "quti", 30)
    _unit(db, p, "dona", 1)
    _stock(db, p, w["pwh"], 100, lot="SER-7")
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_id": box.id}])
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    detail = client.login(w["padmin"]).get(f"/api/sales/{sid}")
    assert detail.status_code == 200, detail.text
    item = detail.json()["items"][0]
    assert len(item["batches"]) == 1
    b = item["batches"][0]
    assert b["lot_number"] == "SER-7" and float(b["quantity"]) == 60 and b["batch_id"]
    assert b["expiry_date"] == (tashkent_today() + timedelta(days=400)).isoformat()
    u = item["unit_info"]
    assert u["unit_name"] == "quti" and float(u["unit_ratio"]) == 30 and float(u["unit_qty"]) == 2
    assert u["unit_id"] == box.id
    assert item["unit"]                      # eski `unit` (o'lchov birligi matni) avvalgidek


def test_sale_detail_regular_company_unchanged(client, db, w):
    p = _product(db, w["nc"])
    _stock(db, p, w["nwh"], 50)
    r = _post_sale(client, w["nadmin"], w["nwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000}])
    assert r.status_code == 200, r.text
    assert db.query(SaleItemBatch).count() >= 1         # partiya ajratmasi bor, lekin oddiy korxonada ko'rsatilmaydi
    item = client.login(w["nadmin"]).get(f"/api/sales/{r.json()['id']}").json()["items"][0]
    assert item["batches"] == [] and item["unit_info"] is None
    assert item["unit"] == "dona"


def test_sale_detail_isolation(client, db, w):
    p = _product(db, w["pc"])
    _stock(db, p, w["pwh"], 50)
    sid = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 1, "unit_price": 1000}]).json()["id"]
    assert client.login(w["qadmin"]).get(f"/api/sales/{sid}").status_code == 404
    assert client.login(w["nadmin"]).get(f"/api/sales/{sid}").status_code == 404
    assert client.login(w["padmin"]).get(f"/api/sales/{sid}").status_code == 200


def test_sale_detail_no_n_plus_one(client, db, w):
    items = []
    for _ in range(3):
        p = _product(db, w["pc"])
        _stock(db, p, w["pwh"], 50)
        items.append({"product_id": p.id, "quantity": 1, "unit_price": 1000})
    sid = _post_sale(client, w["padmin"], w["pwh"], items).json()["id"]
    seen = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    conn = db.get_bind()
    event.listen(conn, "before_cursor_execute", _count)
    try:
        r = client.login(w["padmin"]).get(f"/api/sales/{sid}")
    finally:
        event.remove(conn, "before_cursor_execute", _count)
    assert r.status_code == 200 and all(len(i["batches"]) == 1 for i in r.json()["items"])
    assert sum(1 for s in seen if "FROM sale_item_batches" in s) == 1     # qatorlar soniga bog'liq emas
    assert sum(1 for s in seen if "FROM sale_item_units" in s) == 1


# ───────────────────────── 2. Maksimal ustama ─────────────────────────

def _create_body(**kw):
    n = next(_n)
    base = {"name": f"Yangi dori {n}", "barcode": f"NEWBC{n:07d}", "sale_price": 1500, "cost_price": 1000,
            "mxik_code": "30049099"}
    base.update(kw)
    return base


def test_max_markup_create_pharmacy(client, db, w):
    cl = client.login(w["padmin"])
    r = cl.post("/api/products/", json=_create_body(sale_price=1600))
    assert r.status_code == 400 and "ustamadan (50%)" in r.json()["detail"]
    assert cl.post("/api/products/", json=_create_body(sale_price=1500)).status_code == 201     # aynan chegarada
    # tannarx 0 — tekshiruv o'tkazib yuboriladi
    assert cl.post("/api/products/", json=_create_body(sale_price=99999, cost_price=0)).status_code == 201


def test_max_markup_update_only_when_sale_price_changes(client, db, w):
    p = _product(db, w["pc"], price=2000, cost=1000)       # ustama 100% (chegaradan oshgan, lekin eski narx)
    ProductPharma(product_id=p.id, company_id=w["pc"].id)
    p.mxik_code = "30049099"
    db.flush()
    cl = client.login(w["padmin"])
    # sale_price o'zgarmadi — boshqa maydon tahriri o'tadi
    assert cl.put(f"/api/products/{p.id}", json={"name": "Yangi nom CD"}).status_code == 200
    assert cl.put(f"/api/products/{p.id}", json={"sale_price": 2000}).status_code == 200
    r = cl.put(f"/api/products/{p.id}", json={"sale_price": 1700})
    assert r.status_code == 400 and "50%" in r.json()["detail"]
    assert cl.put(f"/api/products/{p.id}", json={"sale_price": 1400}).status_code == 200
    # yangi tannarx bilan birga: 3000 * 1.5 = 4500 gacha
    assert cl.put(f"/api/products/{p.id}", json={"sale_price": 4400, "cost_price": 3000}).status_code == 200
    db.refresh(p)
    assert p.sale_price == D("4400")


def test_max_markup_regular_company_and_isolation(client, db, w):
    # oddiy korxonada cheklov yo'q
    assert client.login(w["nadmin"]).post("/api/products/", json=_create_body(sale_price=9999)).status_code == 201
    # boshqa dorixona (max_markup_pct yo'q) — cheklov yo'q
    assert client.login(w["qadmin"]).post("/api/products/", json=_create_body(sale_price=9999)).status_code == 201
    # P dorixona mahsuloti boshqa korxonadan o'zgartirilmaydi
    p = _product(db, w["pc"], mxik_code="30049099")
    assert client.login(w["qadmin"]).put(f"/api/products/{p.id}", json={"sale_price": 1200}).status_code == 404


# ───────────────────────── 3. Kirim: manufacture_date va qolgan muddat ─────────────────────────

def _receive(client, user, wh, item, **kw):
    return client.login(user).post("/api/inventory/receive", json={"warehouse_id": wh.id, "items": [item], **kw})


def test_receive_manufacture_date_warns_on_short_shelf_life(client, db, w):
    p = _product(db, w["pc"])
    today = tashkent_today()
    r = _receive(client, w["padmin"], w["pwh"], {
        "product_id": p.id, "quantity": 5, "lot_number": "SH1",
        "manufacture_date": (today - timedelta(days=300)).isoformat(),
        "expiry_date": (today + timedelta(days=30)).isoformat()})
    assert r.status_code == 200, r.text
    warns = r.json()["warnings"]
    assert len(warns) == 1 and "qolgan yaroqlilik muddati" in warns[0] and "minimal 50%" in warns[0]
    b = db.query(Batch).filter_by(product_id=p.id, lot_number="SH1").one()
    assert b.manufacture_date is not None and b.manufacture_date.date() == today - timedelta(days=300)


def test_receive_manufacture_date_ok_and_missing(client, db, w):
    p = _product(db, w["pc"])
    today = tashkent_today()
    r = _receive(client, w["padmin"], w["pwh"], {
        "product_id": p.id, "quantity": 5, "lot_number": "OK1",
        "manufacture_date": (today - timedelta(days=30)).isoformat(),
        "expiry_date": (today + timedelta(days=300)).isoformat()})
    assert r.status_code == 200 and r.json()["warnings"] == []
    r = _receive(client, w["padmin"], w["pwh"], {          # sana berilmagan — foiz hisoblanmaydi
        "product_id": p.id, "quantity": 5, "lot_number": "OK2", "expiry_date": (today + timedelta(days=5)).isoformat()})
    assert r.status_code == 200 and r.json()["warnings"] == []
    r = _receive(client, w["padmin"], w["pwh"], {          # ishlab chiqarilgan sana muddatdan keyin — 400
        "product_id": p.id, "quantity": 1, "lot_number": "BAD", "manufacture_date": (today + timedelta(days=10)).isoformat(),
        "expiry_date": (today + timedelta(days=5)).isoformat()})
    assert r.status_code == 400


def test_receive_manufacture_date_regular_company_ignored(client, db, w):
    p = _product(db, w["nc"])
    today = tashkent_today()
    r = _receive(client, w["nadmin"], w["nwh"], {
        "product_id": p.id, "quantity": 5, "manufacture_date": (today - timedelta(days=300)).isoformat(),
        "expiry_date": (today + timedelta(days=30)).isoformat()})
    assert r.status_code == 200, r.text
    assert "warnings" not in r.json()
    assert db.query(Batch).filter_by(product_id=p.id).one().manufacture_date is None


def test_receive_isolation_foreign_product_404(client, db, w):
    p = _product(db, w["pc"])
    r = _receive(client, w["qadmin"], w["qwh"], {
        "product_id": p.id, "quantity": 1, "lot_number": "X", "expiry_date": (tashkent_today() + timedelta(days=90)).isoformat()})
    assert r.status_code == 404


# ───────────────────────── 4-5. Qaytarish: lot/expiry va markirovka ─────────────────────────

def test_schema_fields_exist():
    from app.schemas.sale import PartialReturnItem, SaleItemCreate
    it = SaleItemCreate(product_id=1, quantity=1, lot_number="A1", expiry_date="2030-01-31")
    assert it.lot_number == "A1" and it.expiry_date.isoformat() == "2030-01-31"
    pr = PartialReturnItem(sale_item_id=1, quantity=1, lot_number="A1", expiry_date="2030-01-31", marking_codes=["x"])
    assert pr.marking_codes == ["x"] and pr.lot_number == "A1"
    assert PartialReturnItem(sale_item_id=1, quantity=1).marking_codes is None


def _sold_item(client, db, user, wh, p, qty=2, **extra):
    r = _post_sale(client, user, wh, [{"product_id": p.id, "quantity": qty, "unit_price": 1000, **extra}])
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    return sid, db.query(SaleItem).filter(SaleItem.sale_id == sid).one()


def test_partial_return_without_original_batch_requires_lot_then_creates_batch(client, db, w):
    p = _product(db, w["pc"])
    _stock(db, p, w["pwh"], 20)
    sid, item = _sold_item(client, db, w["padmin"], w["pwh"], p)
    db.query(SaleItemBatch).filter_by(sale_item_id=item.id).delete()       # eski sotuv — asl ajratma yo'q
    db.flush()
    cl = client.login(w["padmin"])
    r = cl.post(f"/api/sales/{sid}/return-items", json={"items": [{"sale_item_id": item.id, "quantity": 1}]})
    assert r.status_code == 400 and "lot_number" in r.json()["detail"]
    exp = (tashkent_today() + timedelta(days=200)).isoformat()
    r = cl.post(f"/api/sales/{sid}/return-items", json={"items": [
        {"sale_item_id": item.id, "quantity": 1, "lot_number": "RET-9", "expiry_date": exp}]})
    assert r.status_code == 200, r.text
    nb = db.query(Batch).filter_by(product_id=p.id, lot_number="RET-9").one()
    assert D(str(nb.quantity)) == 1 and nb.expiry_date.date().isoformat() == exp


def test_partial_return_regular_company_ignores_lot_fields(client, db, w):
    p = _product(db, w["nc"])
    _stock(db, p, w["nwh"], 20)
    sid, item = _sold_item(client, db, w["nadmin"], w["nwh"], p)
    r = client.login(w["nadmin"]).post(f"/api/sales/{sid}/return-items", json={"items": [
        {"sale_item_id": item.id, "quantity": 1, "lot_number": "ZZ", "expiry_date": "2030-01-01"}]})
    assert r.status_code == 200, r.text
    assert db.query(Batch).filter_by(product_id=p.id, lot_number="ZZ").count() == 0


def test_partial_return_marking_codes_back_to_stock(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    b = _stock(db, p, w["pwh"], 20)
    c1, c2, c3 = (_code(f"S{i}") for i in (1, 2, 3))
    for i in (1, 2, 3):
        _mcode(db, w["pc"], p, f"S{i}", w["pwh"], b)
    sid, item = _sold_item(client, db, w["padmin"], w["pwh"], p, qty=3, marking_codes=[c1, c2, c3])
    assert {_mrow(db, w["pc"], c).status for c in (c1, c2, c3)} == {"sold"}
    cl = client.login(w["padmin"])
    # kod yuborilgan: aynan shu kod qaytadi
    r = cl.post(f"/api/sales/{sid}/return-items", json={"items": [
        {"sale_item_id": item.id, "quantity": 1, "marking_codes": [c2]}]})
    assert r.status_code == 200, r.text
    assert _mrow(db, w["pc"], c2).status == "in_stock" and _mrow(db, w["pc"], c1).status == "sold"
    # kod yuborilmagan: qatorning hali qaytarilmagan sold kodlaridan miqdorcha
    r = cl.post(f"/api/sales/{sid}/return-items", json={"items": [{"sale_item_id": item.id, "quantity": 1}]})
    assert r.status_code == 200, r.text
    assert sorted(_mrow(db, w["pc"], c).status for c in (c1, c2, c3)) == ["in_stock", "in_stock", "sold"]
    # qaytish SaleItem ga yozilgan
    ret = db.query(SaleItem).filter(SaleItem.sale_id != sid, SaleItem.product_id == p.id).all()
    assert any(i.marking_codes for i in ret)
    # noto'g'ri kod (sotilmagan) — 400
    r = cl.post(f"/api/sales/{sid}/return-items", json={"items": [
        {"sale_item_id": item.id, "quantity": 1, "marking_codes": [c2]}]})
    assert r.status_code == 400


def test_partial_return_marking_isolation_and_regular(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    b = _stock(db, p, w["pwh"], 20)
    _mcode(db, w["pc"], p, "I1", w["pwh"], b)
    sid, item = _sold_item(client, db, w["padmin"], w["pwh"], p, qty=1, marking_codes=[_code("I1")])
    # boshqa korxona foydalanuvchisi bu sotuvni qaytara olmaydi
    r = client.login(w["qadmin"]).post(f"/api/sales/{sid}/return-items", json={"items": [
        {"sale_item_id": item.id, "quantity": 1, "marking_codes": [_code("I1")]}]})
    assert r.status_code == 404
    assert _mrow(db, w["pc"], _code("I1")).status == "sold"
    # oddiy korxona: markirovkali mahsulot, kodlar soni bo'yicha (MarkingCode jadvali ishlatilmaydi), qaytarish o'tadi
    np_ = _product(db, w["nc"], requires_marking=True)
    _stock(db, np_, w["nwh"], 10)
    nsid, nitem = _sold_item(client, db, w["nadmin"], w["nwh"], np_, qty=2, marking_codes=["a", "b"])
    r = client.login(w["nadmin"]).post(f"/api/sales/{nsid}/return-items", json={"items": [
        {"sale_item_id": nitem.id, "quantity": 1, "marking_codes": ["a"]}]})
    assert r.status_code == 200, r.text
    assert db.query(MarkingCode).filter_by(company_id=w["nc"].id).count() == 0


# ───────────────────────── 6. Qidiruv: pharma bloki va filtrlar ─────────────────────────

@pytest.fixture
def catalog(db, w):
    """P dorixonada 3 ta dori: A (retseptli, Pfizer, modda M1), B (retseptsiz, Sanofi), C (nazoratda, Pfizer)."""
    c = w["pc"]
    sub = PharmaSubstance(company_id=c.id, name_uz="Parasetamol-CD")
    db.add(sub)
    db.flush()
    a = _product(db, c, name="Aaa dori")
    b = _product(db, c, name="Bbb dori")
    cc = _product(db, c, name="Ccc dori")
    db.add_all([
        ProductPharma(product_id=a.id, company_id=c.id, manufacturer="Pfizer", is_rx=True, control_class="none"),
        ProductPharma(product_id=b.id, company_id=c.id, manufacturer="Sanofi", is_rx=False, control_class="none"),
        ProductPharma(product_id=cc.id, company_id=c.id, manufacturer="Pfizer Uz", is_rx=True, control_class="psychotropic"),
        ProductSubstance(product_id=a.id, substance_id=sub.id),
    ])
    # oddiy korxonada ham shunday mahsulot (filtrlar e'tiborsiz qolishini ko'rsatish uchun)
    n1 = _product(db, w["nc"], name="Nnn 1")
    n2 = _product(db, w["nc"], name="Nnn 2")
    db.flush()
    return dict(a=a, b=b, c=cc, sub=sub, n1=n1, n2=n2)


def _names(resp):
    assert resp.status_code == 200, resp.text
    return sorted(i["name"] for i in resp.json()["items"])


def test_paginated_pharma_block_and_filters(client, db, w, catalog):
    cl = client.login(w["padmin"])
    allr = cl.get("/api/products/paginated")
    assert _names(allr) == ["Aaa dori", "Bbb dori", "Ccc dori"]
    by_name = {i["name"]: i for i in allr.json()["items"]}
    pa = by_name["Aaa dori"]["pharma"]
    assert pa["manufacturer"] == "Pfizer" and pa["is_rx"] is True
    assert [s["name_uz"] for s in pa["substances"]] == ["Parasetamol-CD"]
    assert by_name["Bbb dori"]["pharma"]["manufacturer"] == "Sanofi"
    assert _names(cl.get("/api/products/paginated", params={"substance_id": catalog["sub"].id})) == ["Aaa dori"]
    assert _names(cl.get("/api/products/paginated", params={"manufacturer": "pfizer"})) == ["Aaa dori", "Ccc dori"]
    assert _names(cl.get("/api/products/paginated", params={"is_rx": "true"})) == ["Aaa dori", "Ccc dori"]
    assert _names(cl.get("/api/products/paginated", params={"is_rx": "false"})) == ["Bbb dori"]
    assert _names(cl.get("/api/products/paginated", params={"control_class": "psychotropic"})) == ["Ccc dori"]
    assert _names(cl.get("/api/products/paginated", params={"manufacturer": "pfizer", "is_rx": "true", "control_class": "none"})) == ["Aaa dori"]


def test_paginated_regular_company_filters_ignored_and_pharma_null(client, db, w, catalog):
    cl = client.login(w["nadmin"])
    r = cl.get("/api/products/paginated", params={"is_rx": "true", "manufacturer": "pfizer", "control_class": "x",
                                                  "substance_id": catalog["sub"].id})
    assert _names(r) == ["Nnn 1", "Nnn 2"]
    assert all(i["pharma"] is None for i in r.json()["items"])


def test_paginated_filters_isolation(client, db, w, catalog):
    # boshqa dorixona P ning dorilarini ko'rmaydi (modda ID si bilan ham)
    cl = client.login(w["qadmin"])
    assert _names(cl.get("/api/products/paginated", params={"substance_id": catalog["sub"].id})) == []
    assert _names(cl.get("/api/products/paginated", params={"manufacturer": "pfizer"})) == []
    assert _names(cl.get("/api/products/paginated")) == []


# ───────────────────────── 7. Kutilayotgan sotuvni tasdiqlash ─────────────────────────

def _pending(client, user, wh, items):
    r = client.login(user).post("/api/sales/pending", json={
        "items": items, "payment_type": "cash", "paid_amount": 0, "warehouse_id": wh.id})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_confirm_pending_rx_required_then_override(client, db, w):
    p = _product(db, w["pc"])
    db.add(ProductPharma(product_id=p.id, company_id=w["pc"].id, is_rx=True))
    _stock(db, p, w["pwh"], 20)
    sid = _pending(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000}])
    cl = client.login(w["padmin"])
    r = cl.put(f"/api/sales/{sid}", json={"status": "completed", "paid_amount": 2000})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "rx_required"
    assert db.get(Sale, sid).status.value == "pending"
    r = cl.put(f"/api/sales/{sid}", json={"status": "completed", "paid_amount": 2000,
                                          "rx_override_reason": "Mijoz retseptni unutgan"})
    assert r.status_code == 200, r.text
    rows = db.query(SalePrescription).filter_by(sale_id=sid).all()
    assert len(rows) == 1 and rows[0].reason_without_rx == "Mijoz retseptni unutgan"
    got = client.login(w["padmin"]).get(f"/api/sales/{sid}").json()
    assert len(got["prescriptions"]) == 1


def test_confirm_pending_with_prescription_saved(client, db, w):
    p = _product(db, w["pc"])
    db.add(ProductPharma(product_id=p.id, company_id=w["pc"].id, is_rx=True))
    _stock(db, p, w["pwh"], 20)
    sid = _pending(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 1, "unit_price": 1000}])
    r = client.login(w["padmin"]).put(f"/api/sales/{sid}", json={
        "status": "completed", "paid_amount": 1000,
        "prescriptions": [{"product_id": p.id, "number": "RX-1", "issued_at": tashkent_today().isoformat(),
                           "doctor": "Dr A", "clinic": "Klinika 1"}]})
    assert r.status_code == 200, r.text
    row = db.query(SalePrescription).filter_by(sale_id=sid).one()
    assert row.number == "RX-1" and row.sale_item_id is not None


def test_confirm_pending_regular_company_unchanged(client, db, w):
    p = _product(db, w["nc"])
    db.add(ProductPharma(product_id=p.id, company_id=w["nc"].id, is_rx=True))     # oddiy korxonada e'tiborsiz
    _stock(db, p, w["nwh"], 20)
    sid = _pending(client, w["nadmin"], w["nwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000}])
    r = client.login(w["nadmin"]).put(f"/api/sales/{sid}", json={"status": "completed", "paid_amount": 2000})
    assert r.status_code == 200, r.text
    assert db.query(SalePrescription).count() == 0


def test_confirm_pending_isolation(client, db, w):
    p = _product(db, w["pc"])
    _stock(db, p, w["pwh"], 20)
    sid = _pending(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 1, "unit_price": 1000}])
    r = client.login(w["qadmin"]).put(f"/api/sales/{sid}", json={"status": "completed", "paid_amount": 1000})
    assert r.status_code == 404
    assert db.get(Sale, sid).status.value == "pending"


def test_confirm_pending_marks_codes_sold_simple_path(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    b = _stock(db, p, w["pwh"], 20)
    for i in (1, 2):
        _mcode(db, w["pc"], p, f"P{i}", w["pwh"], b)
    c1, c2 = _code("P1"), _code("P2")
    sid = _pending(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000,
                                                    "marking_codes": [c1, c2]}])
    assert _mrow(db, w["pc"], c1).status == "in_stock"          # kutilayotgan sotuv kodni band qilmaydi
    cl = client.login(w["padmin"])
    r = cl.put(f"/api/sales/{sid}", json={"status": "completed", "paid_amount": 2000})
    assert r.status_code == 200, r.text
    item = db.query(SaleItem).filter_by(sale_id=sid).one()
    assert {_mrow(db, w["pc"], c).status for c in (c1, c2)} == {"sold"}
    assert _mrow(db, w["pc"], c1).sale_item_id == item.id


def test_confirm_pending_marking_wrong_count_and_unknown_code(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    b = _stock(db, p, w["pwh"], 20)
    _mcode(db, w["pc"], p, "Q1", w["pwh"], b)
    cl = client.login(w["padmin"])
    sid = _pending(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000,
                                                    "marking_codes": [_code("Q1")]}])
    r = cl.put(f"/api/sales/{sid}", json={"status": "completed", "paid_amount": 2000})
    assert r.status_code == 400 and "markirovka" in r.json()["detail"]
    sid2 = _pending(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 1, "unit_price": 1000,
                                                     "marking_codes": [_code("NOPE")]}])
    r = cl.put(f"/api/sales/{sid2}", json={"status": "completed", "paid_amount": 1000})
    assert r.status_code == 400 and "topilmadi" in r.json()["detail"]
    assert _mrow(db, w["pc"], _code("Q1")).status == "in_stock"


def test_confirm_pending_marking_regular_company_unchanged(client, db, w):
    p = _product(db, w["nc"], requires_marking=True)
    _stock(db, p, w["nwh"], 20)
    sid = _pending(client, w["nadmin"], w["nwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000,
                                                    "marking_codes": ["x"]}])
    r = client.login(w["nadmin"]).put(f"/api/sales/{sid}", json={"status": "completed", "paid_amount": 2000})
    assert r.status_code == 200, r.text         # oddiy korxona: avvalgidek, kod soni/ro'yxati tekshirilmaydi
    assert db.query(MarkingCode).count() == 0


def test_full_edit_swaps_marking_codes(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    b = _stock(db, p, w["pwh"], 20)
    for i in (1, 2, 3):
        _mcode(db, w["pc"], p, f"E{i}", w["pwh"], b)
    e1, e2, e3 = (_code(f"E{i}") for i in (1, 2, 3))
    cl = client.login(w["padmin"])
    sid = _pending(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 1, "unit_price": 1000,
                                                    "marking_codes": [e1]}])
    body = lambda codes: {"status": "completed", "paid_amount": 1000, "payment_type": "cash", "warehouse_id": w["pwh"].id,
                          "payments": [{"type": "cash", "amount": 1000}],
                          "items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000, "marking_codes": codes}]}
    r = cl.put(f"/api/sales/{sid}", json=body([e1]))
    assert r.status_code == 200, r.text
    assert _mrow(db, w["pc"], e1).status == "sold"
    # tahrir: eski kod in_stock ga qaytadi, yangisi sold
    r = cl.put(f"/api/sales/{sid}", json=body([e2]))
    assert r.status_code == 200, r.text
    assert _mrow(db, w["pc"], e1).status == "in_stock" and _mrow(db, w["pc"], e1).sale_item_id is None
    assert _mrow(db, w["pc"], e2).status == "sold"
    # boshqa sotuvda sotilgan kodni olib bo'lmaydi
    sid2 = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 1, "unit_price": 1000,
                                                        "marking_codes": [e3]}]).json()["id"]
    r = cl.put(f"/api/sales/{sid}", json=body([e3]))
    assert r.status_code == 400 and "sotilgan" in r.json()["detail"]
    assert sid2


def test_cancel_completed_releases_codes(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    b = _stock(db, p, w["pwh"], 20)
    _mcode(db, w["pc"], p, "K1", w["pwh"], b)
    sid = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 1, "unit_price": 1000,
                                                       "marking_codes": [_code("K1")]}]).json()["id"]
    assert _mrow(db, w["pc"], _code("K1")).status == "sold"
    r = client.login(w["padmin"]).put(f"/api/sales/{sid}", json={"status": "cancelled"})
    assert r.status_code == 200, r.text
    assert _mrow(db, w["pc"], _code("K1")).status == "in_stock"


def test_full_edit_with_unit_id_converts_to_base_and_writes_unit(client, db, w):
    p = _product(db, w["pc"], price=1000)
    box = _unit(db, p, "quti", 30)
    _unit(db, p, "dona", 1)
    _stock(db, p, w["pwh"], 200)
    sid = _pending(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 30, "unit_price": 1000}])
    r = client.login(w["padmin"]).put(f"/api/sales/{sid}", json={
        "status": "completed", "paid_amount": 60000, "payment_type": "cash", "warehouse_id": w["pwh"].id,
        "payments": [{"type": "cash", "amount": 60000}],
        "items": [{"product_id": p.id, "quantity": 2, "unit_id": box.id}]})
    assert r.status_code == 200, r.text
    item = db.query(SaleItem).filter_by(sale_id=sid).one()
    assert D(str(item.quantity)) == 60
    su = db.query(SaleItemUnit).filter_by(sale_item_id=item.id).one()
    assert su.unit_name == "quti" and D(str(su.unit_qty)) == 2
    # oddiy korxonada unit_id — 400
    np_ = _product(db, w["nc"])
    _stock(db, np_, w["nwh"], 50)
    nsid = _pending(client, w["nadmin"], w["nwh"], [{"product_id": np_.id, "quantity": 1, "unit_price": 1000}])
    r = client.login(w["nadmin"]).put(f"/api/sales/{nsid}", json={
        "status": "completed", "paid_amount": 1000, "payment_type": "cash", "warehouse_id": w["nwh"].id,
        "payments": [{"type": "cash", "amount": 1000}],
        "items": [{"product_id": np_.id, "quantity": 1, "unit_id": box.id}]})
    assert r.status_code in (400, 404)


# ───────────────────────── 8. POItemOut.requires_marking ─────────────────────────

def _po(client, user, wh, sup, product):
    r = client.login(user).post("/api/purchase-orders", json={
        "supplier_id": sup.id, "warehouse_id": wh.id, "status": "sent",
        "items": [{"product_id": product.id, "qty_ordered": 3, "unit_cost": 500}]})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _supplier(db, c):
    s = Supplier(name=f"Taminotchi {c.id}-{next(_n)}", company_id=c.id, is_active=True, debt_balance=D(0), debt_balances={})
    db.add(s)
    db.flush()
    return s


def test_po_item_requires_marking(client, db, w):
    pm = _product(db, w["pc"], requires_marking=True)
    pp = _product(db, w["pc"], requires_marking=False)
    sup = _supplier(db, w["pc"])
    po1 = _po(client, w["padmin"], w["pwh"], sup, pm)
    po2 = _po(client, w["padmin"], w["pwh"], sup, pp)
    cl = client.login(w["padmin"])
    assert cl.get(f"/api/purchase-orders/{po1['id']}").json()["items"][0]["requires_marking"] is True
    assert cl.get(f"/api/purchase-orders/{po2['id']}").json()["items"][0]["requires_marking"] is False
    # boshqa korxona ko'rmaydi
    assert client.login(w["qadmin"]).get(f"/api/purchase-orders/{po1['id']}").status_code == 404


def test_po_item_requires_marking_regular_company_false(client, db, w):
    pm = _product(db, w["nc"], requires_marking=True)
    sup = _supplier(db, w["nc"])
    po = _po(client, w["nadmin"], w["nwh"], sup, pm)
    assert client.login(w["nadmin"]).get(f"/api/purchase-orders/{po['id']}").json()["items"][0]["requires_marking"] is False


# ───────────────────────── 9. Markirovka va qutidan bo'lib sotish ─────────────────────────

@pytest.fixture
def boxed(db, w):
    """Markirovkali dori: quti = 30 dona; qoldiq 300 dona (10 quti), 4 ta quti kodi."""
    p = _product(db, w["pc"], price=1000, requires_marking=True)
    box = _unit(db, p, "quti", 30)
    piece = _unit(db, p, "dona", 1)
    b = _stock(db, p, w["pwh"], 300)
    for i in range(1, 5):
        _mcode(db, w["pc"], p, f"B{i}", w["pwh"], b)
    return dict(p=p, box=box, piece=piece, batch=b)


def test_whole_boxes_need_one_code_per_box(client, db, w, boxed):
    p, box = boxed["p"], boxed["box"]
    b1, b2 = _code("B1"), _code("B2")
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_id": box.id, "marking_codes": [b1]}])
    assert r.status_code == 400 and "2 ta kod" in r.json()["detail"]
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_id": box.id}])
    assert r.status_code == 400
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_id": box.id,
                                                    "marking_codes": [b1, b2]}])
    assert r.status_code == 200, r.text
    assert _mrow(db, w["pc"], b1).status == "sold" and _mrow(db, w["pc"], b2).status == "sold"
    item = db.query(SaleItem).filter_by(sale_id=r.json()["id"]).one()
    assert D(str(item.quantity)) == 60 and sorted(item.marking_codes) == sorted([b1, b2])


def test_pieces_from_box_need_no_code(client, db, w, boxed):
    p, piece = boxed["p"], boxed["piece"]
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 5, "unit_id": piece.id}])
    assert r.status_code == 200, r.text
    item = db.query(SaleItem).filter_by(sale_id=r.json()["id"]).one()
    assert D(str(item.quantity)) == 5 and not item.marking_codes
    assert db.query(MarkingCode).filter_by(company_id=w["pc"].id, status="sold").count() == 0


def test_pieces_with_opened_box_code_keep_status(client, db, w, boxed):
    p, piece = boxed["p"], boxed["piece"]
    code = _code("B3")
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 5, "unit_id": piece.id,
                                                    "marking_codes": [code]}])
    assert r.status_code == 200, r.text
    item = db.query(SaleItem).filter_by(sale_id=r.json()["id"]).one()
    assert item.marking_codes == [code]
    row = _mrow(db, w["pc"], code)
    assert row.status == "in_stock" and row.sale_item_id is None
    # 2 ta kod — rad etiladi
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 5, "unit_id": piece.id,
                                                    "marking_codes": [_code("B3"), _code("B4")]}])
    assert r.status_code == 400


def test_without_unit_id_old_rule_stays(client, db, w, boxed):
    p = boxed["p"]
    # P.11: qadoqli dorini dona qilib sotish — qutidan bo'lib sotish: ochilgan quti kodi (1 ta) ixtiyoriy, sotilmaydi
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000,
                                                    "marking_codes": [_code("B1")]}])
    assert r.status_code == 200, r.text
    assert _mrow(db, w["pc"], _code("B1")).status == "in_stock"
    # kodlar soni miqdorga teng — eski qoida (eski kassalar): kodlar sotiladi
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000,
                                                    "marking_codes": [_code("B1"), _code("B2")]}])
    assert r.status_code == 200, r.text
    assert {_mrow(db, w["pc"], _code("B1")).status, _mrow(db, w["pc"], _code("B2")).status} == {"sold"}


def test_partial_return_of_box_sale_returns_box_codes(client, db, w, boxed):
    p, box = boxed["p"], boxed["box"]
    b1, b2 = _code("B1"), _code("B2")
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_id": box.id,
                                                    "marking_codes": [b1, b2]}])
    sid = r.json()["id"]
    item = db.query(SaleItem).filter_by(sale_id=sid).one()
    r = client.login(w["padmin"]).post(f"/api/sales/{sid}/return-items", json={"items": [
        {"sale_item_id": item.id, "quantity": 30}]})          # 1 quti = 30 dona
    assert r.status_code == 200, r.text
    assert sorted([_mrow(db, w["pc"], b1).status, _mrow(db, w["pc"], b2).status]) == ["in_stock", "sold"]


def test_regular_company_marking_rule_unchanged(client, db, w):
    p = _product(db, w["nc"], requires_marking=True)
    _stock(db, p, w["nwh"], 50)
    r = _post_sale(client, w["nadmin"], w["nwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000, "marking_codes": ["a"]}])
    assert r.status_code == 400 and "2 ta kod" in r.json()["detail"]
    r = _post_sale(client, w["nadmin"], w["nwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000,
                                                    "marking_codes": ["a", "b"]}])
    assert r.status_code == 200, r.text
    assert db.query(MarkingCode).filter_by(company_id=w["nc"].id).count() == 0


# ───────────────────────── 10. Qo'lda kirimda markirovka ─────────────────────────

def _recv_item(p, codes, qty=2, lot="MK1", days=300):
    return {"product_id": p.id, "quantity": qty, "lot_number": lot,
            "expiry_date": (tashkent_today() + timedelta(days=days)).isoformat(), "marking_codes": codes}


def test_manual_receive_registers_codes_then_sale_passes(client, db, w):
    p = _product(db, w["pc"], requires_marking=True, barcode=GTIN[1:])        # GTIN shtrix-kodga mos
    codes = [_code("M1"), _code("M2")]
    r = _receive(client, w["padmin"], w["pwh"], _recv_item(p, codes))
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []
    rows = db.query(MarkingCode).filter_by(company_id=w["pc"].id).order_by(MarkingCode.id).all()
    batch = db.query(Batch).filter_by(product_id=p.id, lot_number="MK1").one()
    assert len(rows) == 2 and all(x.status == "in_stock" and x.received_po_id is None for x in rows)
    assert all(x.batch_id == batch.id and x.warehouse_id == w["pwh"].id and x.product_id == p.id for x in rows)
    # keyin sotuv shu kodlar bilan o'tadi
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 2, "unit_price": 1000, "marking_codes": codes}])
    assert r.status_code == 200, r.text
    assert {x.status for x in db.query(MarkingCode).filter_by(company_id=w["pc"].id).all()} == {"sold"}


def test_manual_receive_duplicate_codes_400(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    cl_codes = [_code("D1"), _code("D2")]
    assert _receive(client, w["padmin"], w["pwh"], _recv_item(p, cl_codes)).status_code == 200
    stock_before = db.query(StockLevel).filter_by(product_id=p.id).one().quantity
    # takror kod (qayta kirim)
    r = _receive(client, w["padmin"], w["pwh"], _recv_item(p, [_code("D1"), _code("D3")], lot="MK2"))
    assert r.status_code == 400 and "allaqachon" in r.json()["detail"]
    # so'rovning o'zida takror
    r = _receive(client, w["padmin"], w["pwh"], _recv_item(p, [_code("D5"), _code("D5")], lot="MK3"))
    assert r.status_code == 400 and "takrorlangan" in r.json()["detail"]
    assert db.query(MarkingCode).filter_by(company_id=w["pc"].id).count() == 2
    assert db.query(StockLevel).filter_by(product_id=p.id).one().quantity == stock_before


def test_manual_receive_warnings_gtin_and_count(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)               # shtrix-kod GTIN ga mos emas
    r = _receive(client, w["padmin"], w["pwh"], _recv_item(p, [_code("W1")], qty=3))
    assert r.status_code == 200, r.text
    warns = " ".join(r.json()["warnings"])
    assert "GTIN" in warns and "teng emas" in warns
    assert db.query(MarkingCode).filter_by(company_id=w["pc"].id).count() == 1


def test_manual_receive_non_marked_product_ignores_codes(client, db, w):
    p = _product(db, w["pc"], requires_marking=False)
    r = _receive(client, w["padmin"], w["pwh"], _recv_item(p, [_code("Z1")]))
    assert r.status_code == 200, r.text
    assert db.query(MarkingCode).filter_by(company_id=w["pc"].id).count() == 0


def test_manual_receive_regular_company_ignores_codes(client, db, w):
    p = _product(db, w["nc"], requires_marking=True)
    r = client.login(w["nadmin"]).post("/api/inventory/receive", json={
        "warehouse_id": w["nwh"].id, "items": [{"product_id": p.id, "quantity": 2, "marking_codes": [_code("N1"), _code("N2")]}]})
    assert r.status_code == 200, r.text
    assert db.query(MarkingCode).filter_by(company_id=w["nc"].id).count() == 0
    assert "warnings" not in r.json()


def test_manual_receive_codes_isolation_between_companies(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    q = _product(db, w["qc"], requires_marking=True)
    assert _receive(client, w["padmin"], w["pwh"], _recv_item(p, [_code("ISO")])).status_code == 200
    # boshqa korxona shu kodni o'zida ro'yxatga ola oladi (kod korxona ichida noyob)
    r = _receive(client, w["qadmin"], w["qwh"], _recv_item(q, [_code("ISO")], lot="Q1"))
    assert r.status_code == 200, r.text
    assert db.query(MarkingCode).filter_by(company_id=w["pc"].id).count() == 1
    assert db.query(MarkingCode).filter_by(company_id=w["qc"].id).count() == 1
    # boshqa korxona mahsulotiga kod yozib bo'lmaydi
    assert _receive(client, w["padmin"], w["pwh"], _recv_item(q, [_code("X9")], lot="Q2")).status_code == 404
